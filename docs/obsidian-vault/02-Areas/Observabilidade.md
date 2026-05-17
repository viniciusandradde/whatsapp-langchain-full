---
title: Observabilidade — logs, traces, métricas
type: area
status: ativo
priority: media
created: 2026-05-04
updated: 2026-05-17
tags: [observabilidade, logs, traces, langsmith, metricas]
empresa: VSA-Tech
responsavel: Vinicius-Andrade
categoria: infraestrutura
area:
projeto_pai:
relacionados: [Infra-Producao, Compliance-LGPD]
stakeholders: [Vinicius-Andrade]
deadline:
progresso:
---

# Observabilidade

## Stack

- **Logs**: `structlog` (JSON em prod, key=value em dev). Correlation ID via middleware (`request_id` em cada linha)
- **Traces LLM**: LangSmith (`LANGSMITH_TRACING=true` + `LANGSMITH_API_KEY`). Cada agent invocation = run com inputs/outputs/tools/cost
- **Métricas DB**: queries diretas (sem Prometheus)
- **Eventos negócio**:
  - `workflow_evento` (mig 078) — node-by-node de workflow LangGraph
  - `hook_log` + `hook_dead_letter` — webhooks fire-and-forget com retry
  - `audit_governanca` (mig 084) — admin changes
  - `auth_login_event` (mig 026) — login audit

## Telas no painel

### `/observabilidade/traces`
- Lista runs LangSmith com filtro empresa+agente
- Drill-down em uma execução: inputs, intermediate steps, tool calls, latency, cost
- Linka pra `https://smith.langchain.com/...` (UI nativa do LangSmith)

### `/observabilidade/queue`
- Visão de `message_queue`: queued/processing/failed por agente
- Lease expirado → highlight vermelho
- Botão "Retry" + "Mark done" manual

### `/dashboard/qualidade`
- NPS (NPS clássico = %promotores − %detratores)
- Por departamento + ranking de operadores
- Lista de comentários

### `/relatorios-e2e`
- Sandbox 999 + LLM-as-judge
- Datasets: `mackenzie_3m_fewshots` (9055 amostras)

## Comandos úteis

```bash
# Logs de um worker (Docker via Dokploy)
sg docker -c "docker logs --tail 200 -f projetos-chatvsanexus-er02mp-worker-1-1"

# Query backlog
sg docker -c "docker exec projetos-chatvsanexus-er02mp-db-1 \
  psql -U postgres -d whatsapp_langchain \
  -c \"SELECT status, COUNT(*) FROM message_queue GROUP BY status;\""

# DLQ
psql ... -c "SELECT hook_id, event, attempts, last_error FROM hook_dead_letter WHERE archived_at IS NULL;"
```

## Gaps abertos

- ⚠ Sem dashboard de **erros do worker** (apenas logs raw)
- ⚠ Sem alerta automático em failures
- ⚠ Custo LLM rastreado por trace (LangSmith) mas sem ANL agregado em UI Nexus — só `/agents/[id]/runs` cost por run
- ⚠ Sem SLO/SLI formal (uptime, latency p95)

## Relacionados

- [[02-Areas/Infra-Producao]]
- [[02-Areas/Compliance-LGPD]]
- [[03-Resources/Stack-Tecnico]]
