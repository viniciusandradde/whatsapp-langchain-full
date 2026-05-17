---
title: ADR-002 — Worker separado do API (dois processos)
type: adr
status: aceito
priority: alta
created: 2026-04-15
updated: 2026-05-17
tags: [adr, arquitetura, worker, processos]
empresa: VSA-Tech
responsavel: Vinicius-Andrade
categoria: decisao
area: Infra-Producao
projeto_pai:
relacionados: [ADR-001-Postgres-como-fila]
stakeholders: [Vinicius-Andrade]
deadline:
progresso:
---

# ADR-002 — Worker separado do API (dois processos)

## Status

Aceito.

## Contexto

LangGraph + LLM calls são potencialmente lentos (3-30s por turn). Se rodassem inline no handler do webhook (`/webhook/twilio`), Twilio iria considerar timeout (>15s) e retentar — dobrando processamento e ferrando idempotência.

## Decisão

Dois processos independentes compartilhando Postgres:
- **API** (FastAPI): só HTTP edge. Valida HMAC, normaliza, enfileira em `message_queue`. Responde <100ms.
- **Worker**: loop async polling `message_queue`. Faz preprocess, invoca agente, envia outbound, `mark_done`.

Comunicação: **só via Postgres** (sem RPC, sem Redis pub/sub).

## Consequências

### Positivas
- **API permanece leve** — handler de webhook bate <100ms
- **Workers escalam horizontalmente** — N réplicas, claim via `SKIP LOCKED`
- **Boundary claro** — API valida, Worker processa. Agentes nunca importam de `server/`/`worker/` (ver CLAUDE.md)
- **At-least-once delivery** — `mark_done` só APÓS outbound success. Twilio fail → mark_failed → retry

### Negativas
- **Latency entre enqueue e processing** (~500ms polling)
- **Dois processos pra deployar/monitorar** — operação dobra
- **LangGraph schema bootstrap exige cooperação** — advisory lock `8_642_001` no boot pra API e Worker não rodarem DDL ao mesmo tempo

## Implementação concreta

- `src/whatsapp_langchain/server/main.py` — boot API
- `src/whatsapp_langchain/worker/main.py` — boot worker
- Compose: 1 réplica API + 4 réplicas worker em produção

## Relacionados

- [[ADR-001-Postgres-como-fila]]
- [[02-Areas/Infra-Producao]]
