# Checkpoints do LangGraph: parar o vazamento e dar retenção

## Context

O banco de produção tem 2.884 MB, dos quais `checkpoints` são **1.885 MB (65%)**.
O dump diário dobrou em 11 dias (891 MB → 1,9 GB) e o dono vai passar a 20+
clientes. A pergunta é como isso escala.

A investigação (2026-09-15, produção, só leitura) mostrou que **não é o número
de checkpoints** — é o que está dentro deles:

| Medida | Valor |
|---|---|
| linhas em `checkpoints` | 9.445 (293 threads) |
| coluna `checkpoint` (estado do grafo) | **10 MB** no total |
| coluna `metadata` | **1.968 MB** no total — média 171 kB, **máximo 71 MB numa linha** |
| chave que pesa dentro do `metadata` | **`media_url`** (1.238 MB numa amostra de 30 linhas) |
| TOAST | 1.849 MB, 947 mil chunks vivos, zero mortos (não é inchaço) |

**Causa raiz:** `worker/processor.py:2978` põe `"media_url": message.media_url`
no `configurable` do invoke. O `AsyncPostgresSaver` do LangGraph **copia todo o
`configurable` para `checkpoints.metadata` em cada checkpoint do run**. Quando a
Evolution entrega mídia inline, `media_url` é um `data:...;base64,...` com o
áudio/imagem inteiro — e ele entra no banco uma vez por passo do agente.
O comentário no código diz que isso existe para "evitar alucinação de URL"; a
intenção é boa, o veículo é que está errado.

**Por que a estratégia de memória não resolve:** o `Window` já poda o estado
(`RemoveMessage`) — por isso a coluna `checkpoint` tem só 10 MB. O vazamento
está no `metadata`, que o trim não toca.

**Escala com 20 clientes, sem o conserto:** 293 threads em 26 dias deram
1,9 GB, dominado por mídia. Vinte clientes com o mesmo perfil → dezenas de GB
por mês, dump inviável, Drive impossível. **Com o conserto:** um checkpoint
volta a ~1-2 kB; 20 clientes × ~11 mil checkpoints ≈ 440 MB no pior caso, e
com retenção "só o último por thread" ≈ 12 MB. O problema some de vez.

Duas provas de que podar é seguro: o app **nunca usa** `get_state_history`
nem `checkpoint_id` (só `aget_state`, o mais recente) — confirmado em `src/`;
e guardar só o último checkpoint de cada thread deixaria **349 linhas, 90 MB**
(medido). O `trim` já garante que o estado mais recente é autossuficiente.

---

## Avaliação das boas práticas trazidas pelo dono

O material (state enxuto · nada de mídia no checkpointer · `thread_id` por
telefone ou por atendimento) foi cruzado com o que está medido em produção:

**1. State enxuto com trimming — já é assim.** O `Window` (trim) usa
`RemoveMessage`, então poda o estado de verdade. Prova: a coluna `checkpoint`
tem **10 MB** no total, 793 bytes por linha. Nada a fazer.

**2. Nada de mídia no checkpointer — é a Fase 1, com uma ressalva que o
material não cobre.** O conselho fala em "não salvar bytes no *State*". Aqui
o State está limpo; o base64 entrou pela **porta lateral do `configurable`**,
que o LangGraph copia para `metadata` sem que ninguém "salve no state". Quem
seguisse a regra à risca ainda teria este bug. A regra correta para este
repositório é mais forte: **nada pesado no `configurable`** — e isso vai para
o `CLAUDE.md`. O material sugere guardar "URL ou caminho no seu bucket"; a
Fase 1 guarda uma referência (`message_id`) e a tool resolve — satisfaz o
princípio sem criar bucket. Mover mídia para disco/S3 seria a versão completa,
mas ataca também `message_queue` (718 MB) e é decisão à parte.

**3. `thread_id` por telefone vs. por atendimento — decisão de produto,
não deste plano.** Hoje é `{telefone}:{agente}` = "suporte contínuo". O
modelo de dados do sistema, porém, é de **ticket** (`atendimento` com
aguardando → em_andamento → resolvido/abandonado), o que o material associa
ao `thread_id` por atendimento. Trocar para `{telefone}:{agente}:{atendimento_id}`
daria retenção trivial (thread morre com o ticket) e conversa limpa a cada
atendimento — mas: são **7 pontos** que montam o `thread_id` (`queue.py`,
`processor.py`, `outbound.py`, `nota_interna.py`, `webhook_sync.py`,
`traces.py`, `atendimento.py`), a tabela `conversations` chaveia por
`(telefone, agente)`, todas as threads atuais ficariam órfãs (a mig 157 já
registra que renomear agente tem esse efeito), e o agente **perderia a memória
entre tickets** — a memória semântica (`store`, por telefone) sobreviveria,
o histórico não. **Recomendação: manter o `thread_id` como está nesta rodada.**
A Fase 1 resolve 95%+ do volume sem tocar nisso; a Fase 2 já usa
`atendimento.closed_at` como sinal de fim, então o ganho de retenção da troca é
pequeno. Se o dono preferir o modelo de ticket, vira plano próprio.

## Fase 1 — Parar o vazamento (root cause, worker)

**`src/whatsapp_langchain/worker/processor.py` ~2968-2988:** o `configurable`
deixa de carregar base64. Regra: `media_url` só entra se for `http(s)://`;
`data:` vira `None`. Entra `"message_id": message.id` no lugar, como referência.

**`src/whatsapp_langchain/agents/tools/midia.py` ~65 (helper que lê
`configurable["media_url"]`):** se `media_url` vier `None` e houver
`message_id`, buscar `media_url` em `message_queue` pelo id (via `get_pool()`,
como as outras tools já fazem). Mantém a propriedade que o comentário original
queria — a tool nunca recebe URL do agente — sem passar o conteúdo pelo
checkpoint. `atendimento_router/agent.py:21` tem o mesmo `configurable`; aplicar
a mesma regra.

Teste: unit que monta o `invoke_config` com `media_url="data:audio/ogg;base64,AAAA"`
e afirma que `configurable["media_url"] is None` e `message_id` está presente;
e que com `https://...` passa intacto. Um segundo teste no helper de `midia.py`
provando o fallback por `message_id`.

## Fase 2 — Retenção (loop no worker)

Novo `_checkpoint_prune_loop(pool)` em `src/whatsapp_langchain/worker/main.py`,
no molde de `_cleanup_zumbis_loop` (`main.py:331-353`: delay inicial, `try` que
nunca mata o loop, intervalo de 6 h) **mais o claim atômico 1×/dia** de
`shared/resumo_diario.py:116-137` (`UPDATE ... WHERE last_run < hoje`,
`rowcount > 0` = ganhou), porque produção roda dois workers e o
`_cleanup_zumbis_loop` roda nos dois por não ter esse claim.

Lógica em módulo novo `shared/checkpoint_retencao.py`, duas políticas:

1. **Só o último por thread.** Apaga de `checkpoints` e `checkpoint_writes`
   tudo que não seja o `checkpoint_id` mais alto de cada
   `(thread_id, checkpoint_ns)`. **Não toca em `checkpoint_blobs`**: são 22 MB,
   e podar blobs exige cruzar `channel_versions` do checkpoint sobrevivente —
   risco sem ganho. 95% do volume está no `metadata` de `checkpoints`.
2. **Thread encerrada some.** Para threads cujo `atendimento.closed_at` é mais
   velho que `CHECKPOINT_RETENCAO_DIAS` (default 90; `settings`), chamar
   `checkpointer.adelete_thread(thread_id)` (existe em
   `langgraph-checkpoint-postgres 3.0.4`, `aio.py:329`; o repo já faz o mesmo
   delete cru em `shared/queue.py:819` e `routes/agente.py:771`). Mapeamento
   thread → atendimento vem de `message_queue.thread_id`/`atendimento_id`.
   Cliente que volta depois de 90 dias começa conversa nova — a memória
   semântica (`store`) é separada e fica.

Roda por empresa dentro de `empresa_scope` só para o mapeamento; as tabelas do
LangGraph não têm RLS (mig 101 as exclui de propósito), e o pool do
checkpointer é o de `_open_langgraph_pool`.

## Fase 3 — Limpeza única do que já existe

Depois que a Fase 1 estiver em produção (senão o vazamento reenche):

1. Primeira rodada do loop da Fase 2 faz a poda: ~9.100 linhas somem.
2. Os 349 checkpoints sobreviventes ainda têm base64 no `metadata`:
   `UPDATE checkpoints SET metadata = metadata - 'media_url'` — seguro, o
   `metadata` é informativo; tools leem do `config` em tempo de execução, nunca
   do que está gravado. Backup do dia antes (o timer 03:15 já faz).
3. `VACUUM ANALYZE checkpoints`. O **dump encolhe na hora** (pg_dump só leva
   linha viva). O arquivo em disco só encolhe com `VACUUM FULL` (lock exclusivo
   de ~1 min numa tabela desse tamanho) — opcional, fora de horário.

Mesma raiz em `message_queue` (718 MB, coluna `media_url` com base64):
**fora deste plano**, é retenção de fila/histórico e merece decisão própria.

## Fase 4 — Ver antes de doer

`scripts/analise_producao.py`: coletar `pg_total_relation_size` de
`checkpoints` e `message_queue` (hoje só coleta `df` do host).
`scripts/producao_checks.py`: `checar_tamanho_checkpoints` — ATENÇÃO acima de
500 MB, CRÍTICO acima de 2 GB. Mesma família das checagens de saldo e backup:
o crescimento era invisível até alguém abrir o `pg_stat`.

## Arquivos

| Arquivo | Ação |
|---|---|
| `src/whatsapp_langchain/worker/processor.py` | `configurable` sem base64 + `message_id` |
| `src/whatsapp_langchain/agents/tools/midia.py` | fallback por `message_id` |
| `src/whatsapp_langchain/agents/catalog/atendimento_router/agent.py` | mesma regra |
| `src/whatsapp_langchain/shared/checkpoint_retencao.py` | **novo** — as duas políticas |
| `src/whatsapp_langchain/worker/main.py` | `_checkpoint_prune_loop` + task no `main()` e no `finally` |
| `src/whatsapp_langchain/shared/config.py` | `checkpoint_retencao_dias: int = 90` |
| `scripts/analise_producao.py`, `scripts/producao_checks.py` | tamanho das tabelas |
| `tests/unit/test_checkpoint_retencao.py`, `tests/unit/test_producao_checks.py` | novos |
| `CLAUDE.md` | 4 linhas: o `configurable` vira `metadata` persistido; nunca passar conteúdo por ele |

## Verificação

1. Unit: `configurable` com `data:` → `None` + `message_id`; helper de mídia resolve por id.
2. Dev (`EVOLUTION_OUTBOUND_MODE=mock`): mandar um áudio pelo webhook, deixar o
   agente responder, e provar com `SELECT length(metadata::text) FROM checkpoints
   WHERE thread_id=...` que o checkpoint novo tem **kB, não MB**.
3. Dev: popular 3 threads com 20 checkpoints cada, rodar a poda uma vez, afirmar
   que sobra 1 por thread e que `aget_state` ainda devolve o estado correto.
4. Dev: dois workers sobem → só um executa a poda no dia (claim atômico).
5. Produção, após deploy da Fase 1: um dia de `ia_execucao` com mídia sem o
   `metadata` crescer; então Fase 3, e o dump de 03:15 do dia seguinte medido
   contra 1,9 GB.

## Armadilhas já conhecidas

- Mergear é deployar: Fase 1 primeiro, sozinha, validada no dev.
- Nunca `VACUUM FULL` em horário comercial (lock exclusivo).
- `checkpoint_blobs` fica intocado nesta rodada — dizer isso no código.
- Base de dev é cópia antiga: popular threads de teste, não confiar no que há.
