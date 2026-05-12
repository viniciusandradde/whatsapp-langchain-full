# Proposta v2: Workflows estilo state-machine com LangGraph (Hospital Mackenzie)

> **Branch alvo**: `proposta/menu-langgraph-workflows` — proposta técnica
> revisável, NÃO mergear em `master` sem PoC validado.
>
> **Versão 2.0** — Esta revisão corrige 10 falhas críticas identificadas
> na v1 após segunda leitura da doc LangGraph oficial e análise de side
> effects + resume semantics.

## TL;DR das correções vs v1

| # | Problema v1 | Correção v2 |
|---|---|---|
| 1 | Sub-workflows `wf:` resolvidos em runtime | Pré-compilados no boot via `add_node(subgraph)` + detecção topológica de ciclos |
| 2 | Outbox acumulado quebra com `interrupt()` (re-executa node 2x) | Runner detecta `__interrupt__` no result e envia prompt; nodes `send_message` só rodam APÓS o último interrupt do node |
| 3 | Anexos PDF/imagem não modelados | Node type `send_media` com `{url, content_type, caption}` |
| 4 | Vars não chegam ao drawer humano | Node `handover` faz UPSERT em `atendimento.metadata.vars_workflow` (JSONB) lido pelo frontend |
| 5 | Editar workflow rodando = crash | Snapshot imutável em `workflow_chatbot_version`; `WorkflowState.version_id` congela a definição usada |
| 6 | Workflow ↔ Agente IA conflito | Novo node `delegate_to_agent` finaliza workflow + ativa `atendimento.agente_atual`; worker prioriza agente quando setado |
| 7 | Estimativa 17h subestimada | Realista: **PoC 6h → MVP 18h → Completo +14h = ~38h** em 3 fases |
| 8 | Observabilidade só audit-log | Logging structlog por step + endpoint `GET /api/admin/atendimentos/{id}/workflow-state` lendo checkpoint LangGraph |
| 9 | Validação só `min_len` | Node `validate` reusa `shared/validators_br.py` (`is_valid_cpf`, `is_valid_cep`, `is_valid_uf`, etc) |
| 10 | Race multi-worker no mesmo thread_id | `pg_advisory_xact_lock(hash("wf:"+atendimento_id))` no início do runner |

---

## Pesquisa LangGraph — fato crítico descoberto

A doc oficial (<https://docs.langchain.com/oss/python/langgraph/interrupts>)
explicita:

> **Non-Idempotent Record Creation Before Interrupt**:
> Avoid creating new records before an `interrupt`. This can lead to
> duplicate records if the node is re-executed upon resumption.

**Implicação direta**: ao chamar `Command(resume=msg)` num thread pausado,
LangGraph reexecuta o **node inteiro do início**. `interrupt()` retorna
o valor; mas tudo ANTES dele roda 2x.

Isso invalida o padrão "v1" de acumular `outbox` no node antes do interrupt.
O **padrão correto** é:

```python
# ❌ ERRADO (v1) — send_message duplica em resume:
def ask_nome_node(state):
    state["outbox"].append("Qual seu nome?")
    answer = interrupt("waiting")
    return {"vars": {"nome": answer}}

# ✅ CORRETO (v2) — interrupt() na PRIMEIRA linha:
def ask_nome_node(state):
    answer = interrupt({  # payload é o que o runner envia ao cliente
        "kind": "ask_text",
        "prompt": "Qual seu nome?",
        "save_as": "nome",
    })
    # tudo abaixo só roda APÓS resume — side effects seguros aqui:
    return {"vars": {"nome": answer}}
```

O **runner** é responsável por:
1. `graph.ainvoke()` → pegar `result["__interrupt__"]`
2. Ler `payload.prompt` e enviar ao cliente via outbound
3. Marcar atendimento como `aguardando_workflow_input_at = NOW()`
4. Próxima mensagem do cliente: `graph.ainvoke(Command(resume=msg), config=...)`

Nodes do tipo `send_messages` (mensagens sem espera de resposta) ficam
em nodes separados — eles SÓ executam após o último interrupt no edge.

---

## Arquitetura v2 (4 camadas)

```
┌─────────────────────────────────────────────────────────────┐
│  Camada 1: DEFINIÇÃO IMUTÁVEL                               │
│  workflow_chatbot (mutável) ──[fork]──> workflow_chatbot_version│
│  ─ Admin edita definicao_json → versao+1, nova row version  │
│  ─ Atendimento em curso usa versao "congelada" no state     │
└──────────────┬──────────────────────────────────────────────┘
               │ compile_workflow(version_id)
               ▼
┌─────────────────────────────────────────────────────────────┐
│  Camada 2: COMPILE-TIME (boot ou hot reload)                │
│  workflows/compiler.py                                      │
│  ─ Resolve refs `wf:xxx` lendo todas versions ativas        │
│  ─ Detecta ciclos via DFS topológico (warn, não falha)      │
│  ─ Constrói parent StateGraph + adiciona subgraphs como nodes│
│  ─ Cache LRU por (empresa_id, version_id)                   │
└──────────────┬──────────────────────────────────────────────┘
               ▼
┌─────────────────────────────────────────────────────────────┐
│  Camada 3: RUNTIME                                          │
│  workflows/runner.py                                        │
│  ┌────────────────────────────────────────────┐             │
│  │ async def process(atend_id, msg):          │             │
│  │   async with pg_advisory_lock(thread_id):  │ ← #10       │
│  │     graph = cache.get_or_compile(emp, ver) │             │
│  │     state = await graph.aget_state(config) │             │
│  │     if not state.values:                   │             │
│  │         result = await graph.ainvoke(...)  │             │
│  │     else:                                  │             │
│  │         result = await graph.ainvoke(      │             │
│  │             Command(resume=msg), config    │             │
│  │         )                                  │             │
│  │     for itrp in result.get("__interrupt__",[]):│         │
│  │         await outbound.send(itrp.prompt)   │ ← #2        │
│  │     for msg in result.get("outbox", []):   │             │
│  │         await outbound.send(msg)           │             │
│  │     return                                 │             │
│  └────────────────────────────────────────────┘             │
└──────────────┬──────────────────────────────────────────────┘
               ▼
┌─────────────────────────────────────────────────────────────┐
│  Camada 4: INTEGRAÇÃO WORKER                                │
│  worker/processor.py::process_message                       │
│  ─ if atendimento.agente_atual: agente IA (skip workflow)   │ ← #6
│  ─ elif workflow_ativo_da_empresa: workflows.runner.process │
│  ─ else: _try_handle_menu (legacy)                          │
└─────────────────────────────────────────────────────────────┘
```

---

## Correções detalhadas (10 pontos)

### #1 — Sub-workflows pré-compilados, ciclos detectados

**Solução**: compilação resolve refs `wf:xxx` substituindo pelos compiled
subgraphs antes de `builder.compile()`. Detecção de ciclo é feita por
topological sort sobre o grafo dirigido de refs:

```python
async def compile_workflow_root(empresa_id, root_slug, checkpointer):
    # 1. BFS coletando todos workflows referenciados
    seen, queue = set(), [root_slug]
    definicoes = {}
    while queue:
        slug = queue.pop()
        if slug in seen:
            continue
        seen.add(slug)
        defin = await load_active_version(empresa_id, slug)
        definicoes[slug] = defin
        for node_spec in defin["nodes"].values():
            for nxt in _refs_de(node_spec):
                if nxt.startswith("wf:") and nxt[3:] not in seen:
                    queue.append(nxt[3:])

    # 2. Detecção ciclo (DAG of subgraph refs — não execução)
    cycle = _detect_subgraph_ref_cycle(definicoes)
    if cycle:
        logger.warning("workflow_subgraph_cycle", path=cycle)
        # NÃO falha: ciclo aqui é "menu_principal → menu_atendimento →
        # voltar pra menu_principal", que é navegação válida em runtime.
        # Compile só evita inline expansion infinita.

    # 3. Compile bottom-up (folhas primeiro)
    compiled: dict[str, CompiledGraph] = {}
    for slug in _topo_order(definicoes):
        builder = _build_state_graph(definicoes[slug], subgraphs=compiled)
        compiled[slug] = builder.compile(checkpointer=checkpointer)
    return compiled[root_slug]
```

**Navegação "voltar ao menu"**: usa `Command(goto="__return_to_parent__")`
em vez de `wf:menu_principal`. O parent graph captura via edge especial.

### #2 — Outbox + interrupt corrigido

Conforme pesquisa LangGraph: **nodes que pedem input** ficam só com
`interrupt()` na primeira linha. Nodes "send" são separados.

```python
# Node "send messages" — executa side effect APÓS interrupt anterior:
def make_send_messages_node(spec):
    def node(state):
        # ✅ chega aqui apenas após resume do interrupt anterior
        # — pode duplicar SÓ se o checkpoint falhar entre send e save,
        #   mitigado por message_id idempotente no provider (Twilio)
        return {"outbox": [render(m, state["vars"]) for m in spec["messages"]]}
    return node

# Node "ask text" — só interrupt, sem side effects antes:
def make_ask_text_node(spec):
    def node(state):
        answer = interrupt({
            "kind": "ask_text",
            "prompt": render(spec["prompt"], state["vars"]),
            "save_as": spec["save_as"],
            "validate": spec.get("validate"),
        })
        # validação pós-resume (se inválido, interrupt de novo)
        ok, err = _validate(answer, spec.get("validate"))
        if not ok:
            return Command(
                update={"outbox": [err]},
                goto="__self__",  # re-entra no mesmo node
            )
        return {"vars": {spec["save_as"]: answer}}
    return node
```

Runner monta sequência: result.outbox → result.\_\_interrupt\_\_.prompt
(se houver) em **uma única chamada de send**. Cliente recebe tudo
encadeado.

### #3 — Anexos modelados

Novo node type `send_media`:

```json
{
  "type": "send_media",
  "url": "https://hospital.com.br/guia-maternidade.pdf",
  "content_type": "application/pdf",
  "caption": "Seu Guia Maternidade. Boa leitura!",
  "next": "fim"
}
```

Runner usa `outbound.send_media(phone, url, caption=...)` que já existe
no `TwilioClient`/`EvolutionClient` (suportam media URLs).

Admin valida no INSERT que URL é HTTPS público (Twilio precisa pull do
arquivo). Não cobre upload — assume admin já tem URL.

### #4 — Vars sincronizadas para metadata do atendimento

Cada vez que o engine grava em `state.vars`, o runner faz **side-table
sync** opcional pra `atendimento.metadata.vars_workflow` (JSONB):

```python
# Em runner.process() após cada ainvoke:
new_vars = result.get("vars", {})
if new_vars:
    await pool.execute("""
        UPDATE atendimento
           SET metadata = jsonb_set(
                 COALESCE(metadata, '{}'::jsonb),
                 '{vars_workflow}',
                 COALESCE(metadata->'vars_workflow', '{}'::jsonb) || %s::jsonb
               )
         WHERE id = %s
    """, (json.dumps(new_vars), atendimento_id))
```

Frontend `/atendimento` drawer ganha card "Dados coletados pelo bot"
que lê `atendimento.metadata.vars_workflow`. Já existe pattern de
`metadata` JSONB no `atendimento` (vi em outros lugares).

### #5 — Versionamento congelado

Nova tabela imutável:

```sql
CREATE TABLE workflow_chatbot_version (
    id BIGSERIAL PRIMARY KEY,
    workflow_id BIGINT NOT NULL REFERENCES workflow_chatbot(id) ON DELETE CASCADE,
    versao INT NOT NULL,
    definicao JSONB NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    created_by_user_id TEXT,
    UNIQUE (workflow_id, versao)
);
```

Fluxo de update:
1. Admin edita `workflow_chatbot.definicao` na UI
2. Trigger BEFORE UPDATE clona linha atual pra `workflow_chatbot_version`
   com novo `versao` incrementado
3. `workflow_chatbot.versao` apontando pra versão atual ativa

`WorkflowState` carrega `version_id` quando inicia (não dinâmico). Engine
sempre lê de `workflow_chatbot_version` pelo `id`, não da `workflow_chatbot`
mutável. Atendimentos em curso continuam na versão antiga até terminar.

### #6 — Workflow ↔ Agente IA hand-off

Novo node type `delegate_to_agent`:

```json
{
  "type": "delegate_to_agent",
  "agent_slug": "ouvidoria",
  "context_message": "Cliente quer falar com ouvidoria. Vars: {{vars}}",
  "next": "__end__"
}
```

Implementação:
```python
def make_delegate_to_agent_node(spec):
    async def node(state, config):
        atend_id = state["atendimento_id"]
        # 1. Marca agente atual no atendimento
        await pool.execute(
            "UPDATE atendimento SET agente_atual = %s WHERE id = %s",
            (spec["agent_slug"], atend_id),
        )
        # 2. Adiciona msg ao histórico do agente (pré-contexto)
        # ... insert na message_queue ou direto no checkpoint do agente
        return {"outbox": []}  # workflow termina silenciosamente
    return node
```

Worker (camada 4) **checa primeiro `atendimento.agente_atual`**:
- Se setado: roda agente IA, ignora workflow
- Senão: roda workflow se `workflow_chatbot.ativo`
- Senão: legacy menu_item

Pra "voltar do agente pro workflow", atendente humano (ou tool) faz
`UPDATE atendimento SET agente_atual = NULL`. Aí workflow assume.

### #7 — Estimativa realista 3 fases

| Fase | Goal | Tempo |
|---|---|---|
| **PoC** | Validar #1, #2, #5 com workflow mínimo (boas-vindas → LGPD → nome → 2 escolhas) | **6h** |
| **MVP** | Engine completa (12 node types), runner, advisory lock, vars sync, observabilidade, testes E2E | **18h** |
| **Completo** | Importer 9 MDs (2 perfeitos + 7 esqueleto), UI editor JSON básico, doc, deploy | **14h** |
| **Total** | | **~38h** |

PoC gate: se LangGraph não suportar UM dos 10 itens em PoC, refaz proposta antes de gastar resto.

### #8 — Observabilidade explícita

3 camadas:

1. **structlog por step**:
   ```python
   logger.info("workflow_node_entered",
       workflow_id=..., atendimento_id=..., node=..., vars_keys=list(vars.keys()))
   ```

2. **`workflow_evento` table** (já no v1) com eventos:
   `entered`, `exited`, `interrupt_emitted`, `var_saved`, `validation_failed`, `handover`, `delegate_agent`

3. **Endpoint admin** `GET /api/admin/atendimentos/{id}/workflow-state`:
   ```python
   # Retorna:
   {
     "current_node": "ask_cpf",
     "version_id": 42,
     "vars": {"nome_cliente": "João"},
     "events": [...],
     "interrupt_pending": "Digite seu CPF:",
     "started_at": "...",
     "last_input_at": "..."
   }
   ```
   Frontend admin tem botão "Ver estado do workflow" no drawer
   `/atendimento`. Útil pra suporte L2.

### #9 — Validação BR conectada

Node type `ask_text` com `validate_with`:

```json
{
  "type": "ask_text",
  "prompt": "Digite seu CPF:",
  "save_as": "cpf_paciente",
  "validate_with": "cpf",
  "retry_message": "CPF inválido. Tente novamente."
}
```

Mapeamento interno:
```python
VALIDATORS = {
    "cpf": validators_br.is_valid_cpf,
    "cnpj": validators_br.is_valid_cnpj,
    "cep": validators_br.is_valid_cep,
    "uf": validators_br.is_valid_uf,
    "data_br": _validate_data_br,  # dd/mm/aaaa
    "telefone_br": _validate_phone_br,
    "min_len": lambda v, n: len(str(v).strip()) >= int(n),
    "regex": lambda v, pat: bool(re.fullmatch(pat, str(v))),
}
```

`min_len` e `regex` aceitam parâmetro via `validate_with: "min_len:3"`.

### #10 — Advisory lock multi-worker

`runner.process` usa `pg_advisory_xact_lock` keyed em hash do thread_id:

```python
import hashlib

async def process(pool, ...):
    thread_id = f"wf:{atendimento_id}"
    lock_key = int.from_bytes(
        hashlib.sha256(thread_id.encode()).digest()[:8],
        "big", signed=True,
    )
    async with pool.connection() as conn:
        async with conn.transaction():
            # Outros workers no mesmo thread esperam aqui
            await conn.execute("SELECT pg_advisory_xact_lock(%s)", (lock_key,))
            # ... resto do process (ainvoke + outbound + sync vars)
            # lock libera no commit
```

Reusa pattern de `shared/queue.py::enqueue_or_buffer` (advisory lock por
phone:agent).

---

## Schema completo (v2)

### Migration 076 — `workflow_chatbot.sql`

```sql
CREATE TABLE workflow_chatbot (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    slug TEXT NOT NULL,
    nome TEXT NOT NULL,
    descricao TEXT,
    definicao JSONB NOT NULL,         -- versão "draft" mutável
    versao INT NOT NULL DEFAULT 1,    -- versão ativa publicada
    versao_ativa_id BIGINT,           -- FK pra workflow_chatbot_version
    ativo BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (empresa_id, slug)
);

-- Apenas um workflow "principal" ativo por empresa (entry point).
-- Subworkflows referenciados por wf: podem coexistir.
CREATE UNIQUE INDEX uq_workflow_principal_ativo
    ON workflow_chatbot (empresa_id) WHERE ativo AND slug = 'menu_principal';
```

### Migration 077 — `workflow_chatbot_version.sql`

```sql
CREATE TABLE workflow_chatbot_version (
    id BIGSERIAL PRIMARY KEY,
    workflow_id BIGINT NOT NULL REFERENCES workflow_chatbot(id) ON DELETE CASCADE,
    versao INT NOT NULL,
    definicao JSONB NOT NULL,
    published_at TIMESTAMPTZ DEFAULT NOW(),
    published_by_user_id TEXT,
    UNIQUE (workflow_id, versao)
);
ALTER TABLE workflow_chatbot
    ADD CONSTRAINT fk_versao_ativa
    FOREIGN KEY (versao_ativa_id) REFERENCES workflow_chatbot_version(id);
```

### Migration 078 — `workflow_evento.sql`

```sql
CREATE TABLE workflow_evento (
    id BIGSERIAL PRIMARY KEY,
    workflow_version_id BIGINT NOT NULL REFERENCES workflow_chatbot_version(id),
    atendimento_id BIGINT NOT NULL,
    empresa_id BIGINT NOT NULL,
    node_id TEXT NOT NULL,
    evento TEXT NOT NULL CHECK (evento IN (
        'entered', 'exited', 'interrupt_emitted', 'resumed',
        'var_saved', 'validation_failed', 'handover',
        'delegate_agent', 'lgpd_consented', 'error'
    )),
    payload JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_wf_evento_atend ON workflow_evento (atendimento_id, created_at);
CREATE INDEX idx_wf_evento_lgpd ON workflow_evento (workflow_version_id, evento)
    WHERE evento = 'lgpd_consented';
```

### Migration 079 — `atendimento.metadata vars_workflow` (sem schema change)

Uso direto de `atendimento.metadata` JSONB já existente, com convenção:

```json
{
  "vars_workflow": {
    "nome_cliente": "João",
    "cpf_paciente": "...",
    "lgpd_consent_at": "2026-05-11T..."
  }
}
```

---

## Node types completos (15)

| Node | Função | Side effects |
|---|---|---|
| `send_messages` | Manda 1+ msgs estáticas | Append outbox (POST-interrupt safe) |
| `send_media` | Envia URL+content_type | outbox c/ tipo media |
| `send_link` | Envia link clicável c/ preview | outbox |
| `ask_text` | Pergunta + valida + save | `interrupt()` FIRST, side effect AFTER |
| `ask_choice` | Múltipla escolha (1-N) | `interrupt()` FIRST, Command(goto=choice.next) |
| `validate` | Roda validator BR num campo já em vars | side-only após interrupt |
| `audit_event` | Grava em `workflow_evento` | INSERT POST-interrupt |
| `branch` | Edge condicional baseado em vars | Command(goto=...) |
| `set_var` | Set var calculada (ex: timestamp now) | update state |
| `transfer_departamento` | UPDATE atendimento + dispatch_event | side effect |
| `transfer_atendente` | UPDATE assigned_to_user_id | side effect |
| `delegate_to_agent` | Passa pro agente IA (#6) | UPDATE agente_atual |
| `handover` | Resumo + transbordo final | UPDATE metadata + msg pro humano |
| `subflow` | Chama sub-workflow compiled (#1) | usa subgraph as node |
| `end` | Encerra workflow (cliente fica "sem bot") | UPDATE status atendimento |

---

## Padrão `WorkflowState`

```python
class WorkflowState(TypedDict):
    atendimento_id: int
    empresa_id: int
    workflow_version_id: int       # #5 — versão congelada
    vars: Annotated[dict, dict_merge]
    outbox: Annotated[list, list_append]   # mensagens pra enviar
    history: Annotated[list, list_append]  # node_id ordem (debug)
    retry_count: dict[str, int]    # retry per-node
```

---

## Estrutura de arquivos final (branch `proposta/menu-langgraph-workflows`)

```
db/migrations/
  076_workflow_chatbot.sql
  077_workflow_chatbot_version.sql
  078_workflow_evento.sql

src/whatsapp_langchain/workflows/
  __init__.py
  state.py              # WorkflowState TypedDict + reducers
  schema.py             # Pydantic models pra validar definicao_json
  validators.py         # VALIDATORS dict (CPF, CNPJ, regex, etc) — #9
  nodes/
    __init__.py
    send.py             # send_messages, send_media, send_link
    ask.py              # ask_text, ask_choice (interrupt-first)
    branch.py           # branch, set_var, validate
    transfer.py         # transfer_departamento, transfer_atendente
    handover.py         # handover (com vars→metadata sync) — #4
    audit.py            # audit_event
    delegate.py         # delegate_to_agent — #6
  compiler.py           # compile_workflow_root + cycle detection — #1
  runner.py             # process(atend_id, msg) c/ advisory lock — #10
  observability.py      # endpoint /workflow-state — #8

scripts/
  import_workflow_mackenzie.py    # parser 9 MDs (2 perfeitos + 7 esqueleto)

docs/mackenzie/
  1_menu_principal.md
  2_menu_atendimento_cliente.md
  3_menu_agendamento.md
  ... (cópia dos uploads)

docs/
  WORKFLOWS.md          # doc viva (não confundir com esta proposta)

tests/workflows/
  __init__.py
  test_poc_lgpd_gate.py            # FASE PoC — valida #1, #2, #5
  test_compiler_cycle_detection.py # #1
  test_interrupt_resume_semantics.py # #2 (crítico — duplicação após resume)
  test_send_media.py               # #3
  test_vars_sync_metadata.py       # #4
  test_versioning_isolation.py     # #5
  test_delegate_to_agent_handoff.py # #6
  test_validators_br_nodes.py      # #9
  test_concurrent_workers_lock.py  # #10
  fixtures/
    poc_minimal.json
    mackenzie_principal.json
    mackenzie_atendimento.json

frontend/src/app/atendimento/atendimento-drawer.tsx
  # MODIFICA pra mostrar card "Dados coletados pelo bot" — #4

frontend/src/app/workflows/ (BACKLOG — não nessa proposta)
  page.tsx
  editor-json.tsx
```

---

## Fases de execução

### **FASE 0 — PoC (6h, gate de continuidade)**

Goal: validar premissas #1, #2, #5 com workflow mínimo.

1. Mig 076 + 077 mínimas
2. `WorkflowState` + 4 node types: `send_messages`, `ask_text`, `ask_choice`, `end`
3. `compiler.py` SEM subgraph (single workflow)
4. `runner.py` sem advisory lock
5. Workflow fixture: boas_vindas → LGPD ask_choice → ask_nome → menu 2 opções → end
6. Test E2E manual: rodar via REPL invocando ainvoke + Command(resume), inspecionar `__interrupt__` + outbox

**Decisão**: se outbox+interrupt funcionam como esperado, prossegue MVP. Senão, refaz.

### **FASE 1 — MVP (18h)**

1. Migrations completas (076, 077, 078)
2. 15 node types
3. `compiler.py` com subgraphs + cycle detection
4. `runner.py` com advisory lock + vars sync
5. `observability.py` endpoint + structlog
6. Worker integration (feature flag opt-in)
7. Tests covering #1-#10 (8 arquivos)
8. Importer básico: parser dos MDs com regex (80% accuracy)

### **FASE 2 — Completo (14h)**

1. Importer refinado pra 2 MDs (menu_principal + atendimento) perfeitos
2. 7 outros MDs ficam como esqueleto (admin manual)
3. Frontend drawer card "Dados coletados pelo bot"
4. `docs/WORKFLOWS.md` doc viva (guia admin + node reference)
5. CLAUDE.md update
6. PR draft no GitHub pra revisão antes de merge

---

## Cortes de escopo (não nessa proposta, próximos sprints)

- **UI editor visual** (drag/drop nodes) — JSON editor textarea no MVP
- **Migration automática menu_item → workflow** — admin recria manual
- **Anexo upload + storage** — só URL pública externa
- **Workflow analytics** (taxa de conclusão, drop-off por node) — depois
- **A/B testing entre versions** — sprint futuro

---

## Reuso (não reimplementar)

| Componente | Path | Uso |
|---|---|---|
| `AsyncPostgresSaver` checkpointer | `shared/db.py::open_checkpointer` | `compile_workflow(checkpointer=)` |
| `render_template` | `shared/variavel.py` | `{{vars.nome_cliente}}` |
| `dispatch_event` | `shared/hook_dispatcher.py` | nodes transfer/handover |
| `transfer_atendimento_to_departamento` | `shared/atendimento.py` | node transfer |
| `send_outbound_manual` / `send_system_outbound` | `shared/outbound.py` | runner envia outbox |
| `validators_br.*` | `shared/validators_br.py` | node validate (#9) |
| `LangGraph interrupt/Command/StateGraph` | `langgraph.types/.graph` | engine |
| `pg_advisory_xact_lock` pattern | `shared/queue.py::enqueue_or_buffer` | runner lock (#10) |
| `atendimento.metadata` JSONB | já existe | vars sync (#4) |

---

## Verification (consolidada)

### FASE 0 (PoC):
```bash
pytest tests/workflows/test_poc_lgpd_gate.py -v
```
Cenário:
- `ainvoke({...inicial...})` → `result["__interrupt__"]` contém LGPD prompt
- `ainvoke(Command(resume="1"))` → `result["__interrupt__"]` contém ask_nome
- `ainvoke(Command(resume="João"))` → `state.vars["nome"]` == "João"
- Confirma que `send_messages` antes do interrupt **não duplica** mensagem

### FASE 1 (MVP):
```bash
pytest tests/workflows/ -v
```
Cobre os 10 pontos com 1 test cada.

### FASE 2 (Completo):
- Manual: `/atendimento/123` mostra "Dados coletados pelo bot"
- WhatsApp real: cliente recebe pergunta LGPD → responde → recebe agradecimento + ask_nome → responde → recebe menu

---

## Riscos remanescentes (mesmo na v2)

| Risco | Mitigação |
|---|---|
| `interrupt()` reexecuta node 2x em resume — algum efeito colateral escapando | PoC test_interrupt_resume_semantics.py captura isso |
| Definição JSON livre + sem editor visual → admin escreve JSON quebrado | Pydantic schema valida no INSERT, 422 retorna erros legíveis |
| Cliente avança pra menu_global, depois admin desativa workflow | Workflow já compilado segue até cliente terminar (graceful drain) |
| Multi-language (workflow só pt-BR) | Fora de escopo nesta proposta |
| Checkpoint LangGraph cresce indefinido | Cron de cleanup `checkpoint_writes WHERE checkpoint_id IS NULL` — sprint futuro |

---

## Veredicto

A v2 endereça as 10 falhas críticas da v1 e respeita o padrão LangGraph
de **interrupt-first + side-effects-after**. PoC de 6h é gate
obrigatório: se a semântica de interrupt+outbox não bater conforme
desenhado, a proposta refaz antes de mais 32h de investimento.

Estrutura de 3 fases (PoC → MVP → Completo) permite cancelar com baixo
custo se descobrirmos novo problema durante PoC.
