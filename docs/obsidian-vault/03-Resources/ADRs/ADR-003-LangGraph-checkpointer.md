---
title: ADR-003 — LangGraph com AsyncPostgresSaver (checkpointer durável)
type: adr
status: aceito
priority: alta
created: 2026-04-20
updated: 2026-05-17
tags: [adr, langgraph, checkpointer, memoria]
empresa: VSA-Tech
responsavel: Vinicius-Andrade
categoria: decisao
area: Infra-Producao
projeto_pai:
relacionados: [Stack-Tecnico]
stakeholders: [Vinicius-Andrade]
deadline:
progresso:
---

# ADR-003 — LangGraph com AsyncPostgresSaver (checkpointer durável)

## Status

Aceito.

## Contexto

LangGraph oferece 3 backends pra state persistence:
1. **MemorySaver** — in-memory, perde tudo no restart
2. **SqliteSaver** — single file, não escala multi-worker
3. **AsyncPostgresSaver** — DB-backed, multi-worker safe

Nexus tem N workers em paralelo. Estado por thread (conversa) precisa sobreviver a restart de worker e ser visível por qualquer worker que pegar próxima mensagem da mesma thread.

## Decisão

Usar `AsyncPostgresSaver` (LangGraph postgres). Schema (`checkpoints*`, `checkpoint_writes`) é criado em-code via `bootstrap_langgraph_schema()` no boot, **não em SQL migration manual** (pra ficar sincronizado com versão da lib LangGraph).

Pareado com `AsyncPostgresStore` pra memória semântica cross-thread (`namespace = (user_id, "memories")`).

Lifecycle explícito: `open_checkpointer()` + `open_store()` via `AsyncExitStack` no boot do worker, **não lazy per-request**.

## Consequências

### Positivas
- **Multi-worker** — qualquer worker reabre thread por `thread_id`
- **Restart-safe** — state em DB sobrevive a crash
- **LangGraph faz heavy lifting** — não precisa serializar manualmente

### Negativas
- **Tabelas LangGraph fora do `_migrations`** — esquema "mágico"; bootstrap pode falhar se DDL incompatível com versão lib
- **Storage cresce indefinidamente** — sem TTL automático pra checkpoints antigos. TODO: cron de limpeza
- **Schema mutation entre versões LangGraph** — upgrade pode requerer migration manual (raro mas aconteceu uma vez)

## Convenções runtime (load-bearing)

- `thread_id = f"{phone_number}:{agent_id}"` — escopo de checkpointer (uma conversa por agente)
- `user_id = phone_number` — escopo de store (memória cross-thread)
- Os dois SEMPRE setados juntos no `RunnableConfig`

## Relacionados

- [[03-Resources/Stack-Tecnico]]
- `src/whatsapp_langchain/shared/db.py::open_checkpointer/open_store`
- `src/whatsapp_langchain/shared/db.py::bootstrap_langgraph_schema`
