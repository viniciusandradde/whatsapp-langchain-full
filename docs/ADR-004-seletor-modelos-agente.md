# ADR-004 — Seletor de modelos do agente com catálogo completo, créditos estimados e tamanho de contexto

- **Status:** aceito pelo dono em 20/09/2026 · **implementado — PR A (#162) e PR B (#163) em produção em 20/09/2026**
- **Plano operacional (ordem, PRs, checklist):** `.planning/design/seletor-modelos-chatvolt/PLANO.md`
- **Referência visual:** 5 capturas do Chatvolt ("Modelos Disponíveis") em `~/.claude/uploads/15ae8448-1576-44ed-90c9-aa875ea3474b/{245b39a5,1cf206ae,0fc57d99,c452f1c5,b62f40b9}-image.jpg`
- **Público deste documento:** quem for codar (inclusive um modelo menor). Tudo o que precisa de decisão já está decidido aqui; o que não está escrito aqui **não** deve ser inventado — perguntar.

---

## 1. Contexto

A aba **"Modelo & Estilo"** do editor do agente (`frontend/src/app/agents/db/[slug]/agente-editor.tsx`, função `TabModelo`) escolhe o modelo por dois `<select>` (Provedor → Modelo) sobre o catálogo **curado** (`modelo_llm`, ~20 modelos globais). O superadmin tem um `PickerCatalogoCompleto` que busca nos 470 modelos sincronizados do OpenRouter (mig 178) e injeta a escolha como hidden inputs. O custo aparece só como US$/Mtok no bloco "Valores efetivos".

O dono quer a experiência do Chatvolt: todos os modelos em cards com **custo por tamanho de contexto em créditos**, filtros por capacidade, abas por fabricante, e uma seção **"Tamanho do Contexto"** (Lite → Extended) que governa quanto o agente lembra.

**Achado durante o levantamento (importante):** `agente_ia.tipo_memoria` e `janela_memoria` (mig 043) são salvos e exibidos, mas **nunca chegam ao worker** — `agents/loader.py` não os passa ao `build_graph`, e `agents/catalog/agente/agent.py` chama `get_context_middleware()` só com os defaults globais (`CONTEXT_STRATEGY=trim`, `TRIM_KEEP_TURNS`). É o gotcha "UI promete o que o backend ignora". O tamanho do contexto desta ADR tem de ser ligado de verdade.

## 2. Decisões

| # | Decisão | Alternativa rejeitada |
|---|---|---|
| D1 | A tela lista o **catálogo completo** (`openrouter_modelo`, ativo=true). Os curados (`modelo_llm`) ganham selo **Recomendado** e vêm primeiro em "Relevância". | Só o curado (visual novo, mas não "todos os LLMs"). |
| D2 | Custo exibido em **créditos estimados por mensagem**: `1 crédito = US$ 0,001`. Fórmula na §4.3. US$ real no tooltip. | Mostrar US$ direto (menos parecido com a referência). |
| D3 | "Premium"/"BLOQUEADO" foi só visual na PR B; **desde a mig 188 é gate real por plano** (`plano.features.contexto_max` e `modelos_premium`): 402 no PUT, trava na tela e o worker aplica o menor tier. Downgrade rebaixa, nunca derruba o agente. | Deixar só visual — o dono decidiu (20/09) que o tier liberado depende do plano contratado. |
| D4 | **"Tamanho do Contexto" substitui "Janela de memória (msgs)"** na UI e vira `agente_ia.contexto_tamanho` (`lite|regular|medium|large|extended`, NULL = legado). O worker passa a **honrar** o tier (corte por caracteres). | Só tabela de custo sem mexer na memória. |
| D5 | Fonte única dos tiers e da fórmula no backend (`shared/contexto.py`) **e** um espelho puro no front (`creditos.ts`) com o mesmo teste de valores. | Calcular só no front (o app Android e relatórios não teriam a mesma conta). |
| D6 | Endpoint novo `GET /api/v1/modelos-llm/catalogo` com a permissão **`agente.config`** (a mesma do editor). As rotas `/api/openrouter/*` continuam superadmin. | Reusar `/api/openrouter/modelos` (superadmin-only; o operador comum não veria a tela). |
| D7 | Estado da tela (busca, filtros, ordenação, aba de provedor) é **local do componente**; só o que vai no form é persistido (`modelo_provedor`, `modelo_nome`, `contexto_tamanho`). | Persistir filtros em localStorage — ruído sem pedido. |

## 3. Tiers (fonte única)

| tier | rótulo | caracteres | tokens (chars/4) | Premium (visual) |
|---|---|---|---|---|
| `lite` | Lite | 6.000 | 1.500 | não |
| `regular` | Regular | 15.000 | 3.750 | não |
| `medium` | Medium | 25.000 | 6.250 | sim |
| `large` | Large | 35.000 | 8.750 | sim |
| `extended` | Extended | 300.000 | 75.000 | sim |

Default de agente novo: `lite`. Agente existente: `NULL` até ser salvo pela tela nova (o worker mantém o comportamento atual até lá).

## 4. Backend

### 4.1 Migration `db/migrations/187_agente_contexto_tamanho.sql`
```sql
-- Tamanho do contexto do agente (ADR-004): Lite 6k … Extended 300k caracteres.
-- Substitui, na UI, a "janela de memória (msgs)" da mig 043 — que nunca chegou
-- ao worker. NULL = legado (TRIM_KEEP_TURNS global), até o agente ser salvo
-- pela tela nova.
ALTER TABLE agente_ia
    ADD COLUMN IF NOT EXISTS contexto_tamanho TEXT
    CHECK (contexto_tamanho IS NULL OR contexto_tamanho IN ('lite','regular','medium','large','extended'));
COMMENT ON COLUMN agente_ia.contexto_tamanho IS
    'Tier de contexto (ADR-004). Limita o histórico relido pelo agente em caracteres. NULL = legado.';
```
Atualizar em `CLAUDE.md` a linha "Currently N migration files numbered up to `186`" → `187`.

### 4.2 `src/whatsapp_langchain/shared/contexto.py` (novo, puro)
```python
"""Tiers de contexto do agente (ADR-004) — fonte única de chars, tokens e créditos."""
from __future__ import annotations

import math
from typing import Literal

TierContexto = Literal["lite", "regular", "medium", "large", "extended"]
TIERS: dict[str, int] = {"lite": 6_000, "regular": 15_000, "medium": 25_000, "large": 35_000, "extended": 300_000}
ORDEM: tuple[str, ...] = ("lite", "regular", "medium", "large", "extended")
PREMIUM: frozenset[str] = frozenset({"medium", "large", "extended"})
TIER_PADRAO: TierContexto = "lite"
CHARS_POR_TOKEN = 4
TOKENS_SAIDA_ESTIMADOS = 300
USD_POR_CREDITO = 0.001

def chars_para_tokens(chars: int) -> int:
    return max(1, chars // CHARS_POR_TOKEN)

def creditos_por_mensagem(*, preco_prompt: float | None, preco_completion: float | None, tier: str) -> int | None:
    """Créditos estimados de UMA resposta com o histórico cheio no tier.
    preco_* em US$ por token (como vem no `pricing` do OpenRouter). None quando o preço é desconhecido."""
    if preco_prompt is None or preco_completion is None:
        return None
    usd = chars_para_tokens(TIERS[tier]) * preco_prompt + TOKENS_SAIDA_ESTIMADOS * preco_completion
    return max(1, math.ceil(usd / USD_POR_CREDITO))
```
Teste `tests/unit/test_contexto.py`: Gemini 2.5 Flash (`3e-7`, `2.5e-6`) em `lite` = **2**; em `extended` = ceil((75000×3e-7 + 300×2.5e-6)/0.001) = ceil(23.25) = **24**; preço `0`/`0` = 1 (mínimo); `None` → `None`; `chars_para_tokens(6000) == 1500`.

### 4.3 Fórmula (a mesma no front, `creditos.ts`)
```
tokens_in  = TIERS[tier] // 4
usd        = tokens_in * preco_prompt + 300 * preco_completion
creditos   = max(1, ceil(usd / 0.001))
```
`preco_prompt`/`preco_completion` vêm de `openrouter_modelo.pricing->>'prompt'` / `->>'completion'` (strings decimais em US$/token — converter com `float`). Tier com mais tokens que `context_length` do modelo → o card mostra `—` (não cabe).

### 4.4 `shared/agente.py`
- `_COLS`: acrescentar `", contexto_tamanho"` **no fim** da string (a linha é desempacotada por posição em `_row_to_agente`).
- `class AgenteIA`: `contexto_tamanho: str | None = None` **no fim** dos campos; `to_dict()` inclui.
- `class AgenteRuntime`: `contexto_tamanho: str | None = None`; `from_agente` copia.
- `create_agente`/`update_agente`: aceitam `contexto_tamanho` (o update já é por nome; o create precisa da coluna no INSERT se ele lista colunas explicitamente — conferir).
- Regra de salvamento: se `contexto_tamanho` vier preenchido, gravar `janela_memoria = NULL` no mesmo UPDATE (um só manda). Documentar no docstring.

### 4.5 Rota `server/routes/agente.py`
- Pydantic de create/update: `contexto_tamanho: Literal["lite","regular","medium","large","extended"] | None = None`.
- Nenhuma validação contra o catálogo curado ao salvar `modelo_provedor`/`modelo_nome` (já é assim — o caminho `escolhaLivre` prova). Manter.

### 4.6 Worker — honrar o tier
1. `agents/middleware/trim.py::create_trim_middleware(keep_turns: int = 5, max_chars: int | None = None)`:
   - Mantém o corte por turnos existente.
   - Se `max_chars` não é None: depois do corte por turnos, percorre os turnos do **mais recente ao mais antigo** somando `len(str(m.content))` de cada mensagem; para ao exceder `max_chars`; **o turno mais recente entra sempre** (mesmo que sozinho exceda); todas as mensagens antes do primeiro turno mantido viram `RemoveMessage`.
   - Turno = do `HumanMessage` até antes do próximo `HumanMessage` (mesma regra dos `boundaries` já existentes).
   - Testes `tests/unit/test_trim_middleware.py` (ou o arquivo existente do trim): (a) `max_chars=None` → resultado idêntico ao atual; (b) 3 turnos de 3.000 chars com `max_chars=6_000` → ficam os 2 últimos; (c) 1 turno de 10.000 chars com `max_chars=6_000` → nada removido; (d) `keep_turns=1` + `max_chars` alto → 1 turno (o menor dos dois limites vence).
2. `agents/middleware/context.py::get_context_middleware(..., trim_max_chars: int | None = None)` → repassa `max_chars=trim_max_chars` a `create_trim_middleware`. Só afeta `strategy == "trim"`.
3. `agents/catalog/agente/agent.py::build_graph(..., contexto_chars: int | None = None, trim_keep_turns: int | None = None)` → `get_context_middleware(trim_keep_turns=trim_keep_turns, trim_max_chars=contexto_chars)`.
4. `agents/loader.py`: ao chamar `module.build_graph(...)` acrescentar
   `contexto_chars=TIERS[agente_runtime.contexto_tamanho] if agente_runtime and agente_runtime.contexto_tamanho else None` e `trim_keep_turns=agente_runtime.janela_memoria if agente_runtime and agente_runtime.janela_memoria else None`; log `agent_loaded` ganha `contexto_tamanho`.
5. Outros templates do catálogo (`agents/catalog/*/agent.py`) que não aceitam os kwargs novos: o loader já passa kwargs específicos hoje; conferir que todos os `build_graph` aceitam `**kwargs` ou adicionar os dois parâmetros com default None em cada um (não quebrar `langgraph dev`).

### 4.7 Endpoint `GET /api/v1/modelos-llm/catalogo` (`server/routes/catalogo.py`, `router_modelo_llm`)
- Dependências: as do router (`verify_service_token`) + `Depends(require_permission("agente.config"))` + `get_empresa_context`.
- Query (uma só, sem paginação):
```sql
SELECT m.slug, m.nome, m.descricao, m.context_length,
       ('image' = ANY(m.input_modalities))                               AS visao,
       ('reasoning' = ANY(m.supported_parameters)
        OR 'include_reasoning' = ANY(m.supported_parameters))            AS pensamento,
       ('tools' = ANY(m.supported_parameters))                           AS tools,
       NULLIF(m.pricing->>'prompt','')::float8                            AS preco_prompt,
       NULLIF(m.pricing->>'completion','')::float8                        AS preco_completion,
       m.criado_no_or,
       EXISTS (SELECT 1 FROM modelo_llm c
                WHERE c.ativo AND c.tipo = 'chat'
                  AND c.provedor || '/' || c.nome = m.slug)              AS curado
  FROM openrouter_modelo m
 WHERE m.ativo
 ORDER BY m.slug
```
- Campos derivados em Python: `provedor` = `slug.split("/")[0]`; `provedor_nome` = `PROVEDORES_NOME.get(provedor, provedor.capitalize())` com o mapa `{"google":"Google","openai":"OpenAI","anthropic":"Anthropic","qwen":"Qwen","deepseek":"Deepseek","moonshotai":"Moonshot AI","amazon":"Amazon","meta-llama":"Meta","mistralai":"Mistral","x-ai":"xAI","z-ai":"Z.ai","microsoft":"Microsoft","cohere":"Cohere","perplexity":"Perplexity","nvidia":"NVIDIA","minimax":"MiniMax","tencent":"Tencent","baidu":"Baidu"}`; `novo` = `criado_no_or >= now() - 30 dias`; `promo` = `slug.endswith(":free") or preco_prompt == 0`; `tendencia` = slug está entre os 20 primeiros do ranking diário mais recente (mig 179; se a tabela estiver vazia, `False` para todos — não falhar).
- Resposta: `{"itens": [...], "gerado_em": iso}`; cache em memória por processo de 10 min (dict módulo + timestamp; o sync do catálogo roda a cada 10 min no worker).
- Testes: `tests/integration/test_catalogo_modelos_endpoints.py` no molde de `test_aba_endpoints.py` — **TestSmoke** (401 sem service token); **TestE2E** `docker_demo`: 200, `len(itens) >= 1`, todo item tem as 13 chaves, pelo menos um `curado == True` (o dev tem `google/gemini-2.5-flash` no curado), `visao` é bool.

### 4.8 `frontend/src/lib/api.ts`
- `AgenteIA` += `contexto_tamanho: "lite" | "regular" | "medium" | "large" | "extended" | null;`
- Novo tipo + fetch:
```ts
export interface ModeloCatalogo { slug: string; provedor: string; provedor_nome: string; nome: string; descricao: string | null;
  context_length: number | null; visao: boolean; pensamento: boolean; tools: boolean;
  preco_prompt: number | null; preco_completion: number | null; novo: boolean; tendencia: boolean; promo: boolean; curado: boolean; }
export async function getCatalogoModelos(): Promise<{ itens: ModeloCatalogo[]; gerado_em: string }> {
  return apiFetch(`/api/v1/modelos-llm/catalogo`); }
```
- Server Action em `frontend/src/app/agents/db/[slug]/actions.ts`: `carregarCatalogoModelosAction()` no padrão das existentes (`{ ok: true, data } | { ok: false, error }`), sem `revalidatePath`.

## 5. Frontend — componente `seletor-modelo.tsx`

Arquivo: `frontend/src/app/agents/db/[slug]/seletor-modelo.tsx` (`"use client"`). Arquivos auxiliares: `creditos.ts` (puro: `TIERS`, `ORDEM`, `PREMIUM`, `creditosPorMensagem`, `rotuloTier`, `cabeNoModelo`), `logos-provedor.tsx` (ícone por provedor: SVG inline simples ou inicial em círculo — **sem** baixar logos de terceiros).

### 5.1 Props e contrato com o form
```ts
interface Props {
  agente: AgenteIA;                 // modelo atual, contexto_tamanho, prompt_override (para o aviso)
  curados: ModeloLLM[];             // fallback se o catálogo falhar
  superadmin?: boolean;
}
```
- Renderiza **hidden inputs** `name="modelo_provedor"`, `name="modelo_nome"`, `name="contexto_tamanho"` — os names não podem duplicar com o restante do form (remover os `FieldSelect` Provedor/Modelo, o `PickerCatalogoCompleto` e o `Field janela_memoria` de `TabModelo`; manter o resto).
- O save existente do editor (`patch.modelo_provedor`/`modelo_nome` a partir do FormData) continua; acrescentar `contexto_tamanho` ao patch em `agente-editor.tsx` (bloco `if (tab === "modelo")`).
- Estado: `slugSelecionado` (inicial = `agente.modelo_provedor + "/" + agente.modelo_nome` ou `agente.modelo`), `tier` (inicial = `agente.contexto_tamanho ?? "lite"`), `busca`, `filtros: {promo, visao, pensamento, tools}`, `ordem: "relevancia"|"nome"|"preco"|"contexto"|"novos"`, `desc: boolean`, `provedor: "todos" | string`.
- Dados: `useQuery({ queryKey: ["catalogo-modelos"], queryFn: carregarCatalogoModelosAction (lança em erro), staleTime: 10*60_000 })`. Enquanto carrega: skeleton de 3 cards. Erro: `ApiError` do kit + fallback para os dois `FieldSelect` do curado (o componente antigo pode ser mantido como `SeletorCurado` para isso).

### 5.2 Estrutura visual (tokens do tema; mobile-first; claro e escuro)
1. **Card-resumo** — `rounded-xl bg-brand-primary/5 p-3 grid grid-cols-3 divide-x`: `MODELO SELECIONADO` (logo + nome truncado) · `TAMANHO DO CONTEXTO` (ponto colorido + rótulo) · `CRÉDITOS` (ícone `BadgeDollarSign` + número). Rótulos `font-mono text-[10px] uppercase tracking-[.14em] text-muted-foreground`.
2. **Busca** — `InputGroup` + `InputGroupAddon` (`Search`) + `InputGroupInput` placeholder "Buscar por modelo, fabricante ou provedor…" (`aria-label="Buscar modelo"`). Filtro client-side por `nome`, `slug`, `provedor_nome` (lower, sem acento).
3. **Chips** — 4 `Button variant="outline" size="sm"` com `aria-pressed`, ativo = `bg-brand-primary/10 border-brand-primary text-brand-primary`: `Promoção` (`BadgeDollarSign`), `Visão` (`Eye`), `Pensamento` (`Brain`), `HTTP Tools` (`Code`).
4. **Contagem** — `Badge variant="secondary"`: "N modelos encontrados" + `Button variant="ghost" size="icon-sm"` `FilterX` (`aria-label="Limpar filtros"`), visível só com algum filtro/busca/provedor ativo.
5. **Ordenação** — `Select` do kit (`Relevância`, `Nome`, `Preço`, `Contexto`, `Mais novos`) + `Button variant="outline" size="icon"` com `ArrowDown`/`ArrowUp` (`aria-label="Inverter ordem"`). Relevância = `curado desc, tendencia desc, novo desc, preco_prompt asc, nome asc`.
6. **Abas de provedor** — `ScrollArea` horizontal com botões `rounded-full`: `Todos · N` + um por provedor com contagem **após** busca+chips (não após a própria aba). Ativa = `bg-brand-primary text-brand-primary-foreground` (ou `text-white` se o token não existir — conferir `globals.css`). Ordenar por contagem desc.
7. **Cards** — `<ul>` grid `grid-cols-1 lg:grid-cols-2 gap-3`; cada `<li>` é um `<button type="button" aria-pressed>` de largura cheia (card inteiro clicável; sem botão aninhado):
   - Linha 1: logo (`size-9 rounded-lg bg-muted`), nome (`font-semibold truncate`) + `provedor_nome` (`text-muted-foreground text-sm`), badges: `NEW` (`bg-brand-primary text-white text-[10px]`), `↗` (`TrendingUp`, title "Em alta no OpenRouter"), `$` (`title="Promoção"`, quando `promo`), `Recomendado` (`Badge variant="secondary"`, quando `curado`), `🔒 BLOQUEADO →` (`Lock`, `bg-brand-primary/10 text-brand-primary`, **só visual**: quando `preco_prompt > 5e-6` ou tier atual é premium; `title="Recurso Premium — em breve por plano"`).
   - Ícones de capacidade à direita: `Eye`, `Brain`, `Code` — `text-foreground` quando presente, `text-muted-foreground/30` quando ausente, cada um com `title`.
   - Grade: 5 colunas (`grid-cols-5` ≥ sm; no mobile `grid-cols-4` + Extended embaixo, como na referência) com `LITE · REGULAR · MEDIUM · LARGE · EXTENDED` (`font-mono text-[10px] uppercase`, ponto colorido: lite `bg-success`, regular `bg-brand-primary`, medium `bg-brand-secondary` (ou `bg-warning`), large `bg-warning`, extended `bg-destructive`) e o número de créditos (`text-lg font-semibold`; `—` quando não cabe no `context_length`; `?` quando preço desconhecido). A coluna do tier atual: `bg-brand-primary/10 rounded-md`.
   - Selecionado: `border-l-4 border-success bg-success/5`; hover: `bg-muted/40`.
8. **Tamanho do Contexto** — título + 5 cards empilhados (`<button type="button" aria-pressed>`): `Lite` / `6.000 caracteres` à esquerda, badge `N C` (`bg-warning text-warning-foreground` no selecionado, `outline` nos demais) à direita; Medium+ com `Badge` `Premium` (`bg-warning/10 text-warning`, só visual). Selecionado = `border-2 border-brand-primary bg-brand-primary/5`. Texto de ajuda: "Define quantos caracteres o agente consegue "lembrar" da conversa atual. Note que o custo em créditos varia conforme o tamanho do contexto selecionado."
9. **Aviso do prompt** — se `(agente.prompt_override ?? "").length > TIERS[tier]`: banner `rounded-lg border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive`: "O prompt do agente excede o número de caracteres suportado neste tamanho de contexto. Reduza o prompt ou aumente o Tamanho do Contexto."
10. **Salvar flutuante** — no editor, tornar o botão salvar existente `sticky bottom-4 ml-auto` dentro da aba (não `fixed`); rótulo "Salvar" com `Save`.
11. Modelo atual fora do catálogo (legado/slug antigo): card sintético no topo com `Badge` "atual (fora do catálogo)", selecionável, sem grade de créditos.

### 5.3 Regras que não podem quebrar (portões do repo)
- `scripts/ui_metrics.sh --check` não pode subir: **sem** `<input>`/`<select>`/`<textarea>` crus (usar kit), **sem** paleta crua (`red-500`, `amber-400`…), **sem** `fixed inset-0`, **sem** `confirm()/alert()`, **sem** hex literal.
- React Compiler (lint): nada de `setState` dentro de `useEffect`, nada de `Date.now()` no render, nada de ref lido no render. Derivar tudo com `useMemo`/render puro.
- Base UI: composição por `render={<Button …/>}` (não existe `asChild`).
- Todo `<Link>` com `prefetch={false}`.
- Dados só via Server Action/proxy (ADR-003), nunca `fetch` direto do cliente à API.
- pt-BR em UI, comentários e commits.

### 5.4 `creditos.ts` (puro) — testes
Sem runner de testes no front: validar com um script `node --experimental-strip-types` ad hoc (como feito em `timeline.ts`) com os mesmos casos da §4.2 e registrar o resultado na PR.

## 6. Validação e entrega (contrato dev-first)
- **PR A (backend)** `feat/contexto-tamanho-backend`: itens §4.1-4.7. `make check`; `uv run pytest tests/unit/test_contexto.py tests/unit/test_trim_middleware.py tests/unit/test_atendimento_helpers.py -q`; E2E do catálogo contra a API do dev (`DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain INTERNAL_SERVICE_TOKEN=dev-token-change-in-production uv run pytest tests/integration/test_catalogo_modelos_endpoints.py -m docker_demo`). Rebuild dev `up -d --build api worker`; conferir `_migrations`/coluna e um `docker exec … grep contexto_chars`. Fumaça de verdade: salvar um agente com `extended`, mandar 3 mensagens longas pelo webhook mock e ver no log `agent_loaded contexto_tamanho=extended` e nenhum `RemoveMessage` indevido.
- **PR B (frontend)** `feat/seletor-modelos-chatvolt` (branch de `origin/master` **depois** da A mergeada): §4.8, §5. `npm run lint`, `npm run typecheck`, `bash scripts/ui_metrics.sh --check`. Rebuild dev `up -d --build frontend` (**lembrar: reconstrói a api do checkout atual**). Capturas 390×844 e 1440×900, claro e escuro: lista com filtros, aba de provedor, card selecionado, seção de contexto com Premium, aviso do prompt, salvar e reabrir (persistiu `contexto_tamanho` e o modelo). Mostrar ao dono **antes** do merge.
- Merge sequencial (A → esperar `deploy` verde e container novo → B), conferir por conteúdo em produção e a migration aplicada.
- Docs na PR B: parágrafo "Seletor de modelos (ADR-004)" no `CLAUDE.md` (módulos) + link nesta ADR na lista de "Reference docs".

## 7. Consequências
- **Positivas:** operador escolhe entre todos os modelos com custo comparável de relance; o tamanho do contexto passa a ser real (hoje a UI mente); base pronta para o gate por plano (Premium já sinalizado).
- **Negativas/limites:** créditos são **estimativa** (não faturamento); custo real continua em `ia_execucao`. Trim por caracteres é aproximação de tokens (÷4). `tipo_memoria` buffer/summary/none seguem sem efeito no worker (fora desta leva — registrar como pendência).
- **Fora desta leva:** créditos como moeda de cobrança; tela no app Android (campo é aditivo, não quebra). O gate por plano entrou na mig 188 (ver CLAUDE.md).
