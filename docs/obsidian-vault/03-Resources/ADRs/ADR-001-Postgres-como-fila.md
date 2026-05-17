---
title: ADR-001 — Postgres como fila (sem Redis/RabbitMQ)
type: adr
status: aceito
priority: alta
created: 2026-04-15
updated: 2026-05-17
tags: [adr, arquitetura, fila, postgres]
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

# ADR-001 — Postgres como fila (sem Redis/RabbitMQ)

## Status

Aceito (em produção desde início do projeto).

## Contexto

Toda mensagem WhatsApp inbound precisa ser processada async (typing indicator, LLM call, outbound send). Webhook tem que retornar TwiML em <100ms pra Twilio não considerar timeout. Logo, precisa de fila.

Opções típicas: Redis (BRPOP), RabbitMQ, AWS SQS, Postgres LISTEN/NOTIFY ou polling com `FOR UPDATE SKIP LOCKED`.

## Decisão

Usar Postgres como fila via tabela `message_queue` + polling com `FOR UPDATE SKIP LOCKED` + lease (60s).

## Consequências

### Positivas
- **Zero infra adicional** — DB já tá lá pro app
- **Transações atômicas** — claim + state change na mesma TX
- **Inspeção trivial** — SELECT mostra fila em tempo real
- **Retry com backoff** — `process_after = NOW() + attempts*5s` em UPDATE
- **Idempotência via lease expiry** — worker travado libera row em 60s
- **Compatível com auto-scale de workers** — `SKIP LOCKED` previne contention

### Negativas
- **Latency de polling** (~500ms-1s) — pior que push Redis (<10ms). Aceitável pra WhatsApp (usuário não percebe)
- **Carga no DB** — N workers fazendo N pollings. Mitigado com SKIP LOCKED + index em `(status, process_after)`
- **Não escala bilhão de msg/dia** — pra esse caso voltaria Kafka/Redis

## Alternativas consideradas

| Opção | Por que não |
|---|---|
| Redis BRPOP | Mais infra, mais um failure mode, perde TX atômica |
| RabbitMQ | Idem, overkill pro volume |
| AWS SQS | Vendor lock, custo, latency cross-region |
| Postgres LISTEN/NOTIFY | NOTIFY não persiste — se worker tá down quando webhook chega, mensagem se perde. Polling com tabela é durable |

## Métricas/limites observados

- ~5-10K msg/dia em prod (Mackenzie + outras empresas), DB confortável
- 4 workers polling a cada 100ms — CPU <2%

## Relacionados

- [[03-Resources/Stack-Tecnico]]
- `src/whatsapp_langchain/shared/queue.py` — implementação
