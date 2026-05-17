---
title: Infra Produção — Dokploy + Oracle Cloud
type: area
status: ativo
priority: alta
created: 2026-05-04
updated: 2026-05-17
tags: [infra, producao, dokploy, oracle, devops]
empresa: VSA-Tech
responsavel: Vinicius-Andrade
categoria: infraestrutura
area:
projeto_pai:
relacionados: [Observabilidade]
stakeholders: [Vinicius-Andrade]
deadline:
progresso:
---

# Infra Produção

## Stack

- **Host**: Oracle Cloud ARM (Ampere A1, gratuito tier)
- **Orquestração**: Dokploy (Compose service `chat-vsanexus`)
- **Domínios**:
  - `chat.vsanexus.com` → frontend Next.js (port 3000)
  - `api.vsanexus.com` → API FastAPI (port 8000)
- **Containers**: db (Postgres), api, frontend, worker-{1..4}, tests
- **Auto-deploy**: ON (push em master via webhook GitHub)

## Operação

### Comandos via API Dokploy

```bash
TOKEN=$(cat ~/.config/dokploy/token)
DOKPLOY=https://dockploy.vsatecnologia.com.br

# Detail compose
curl -sS -H "x-api-key: $TOKEN" "$DOKPLOY/api/compose.one?composeId=yP8q8tXHmGGiKhusSK-h8" | jq

# Deploy manual (clona + build + recreate)
curl -X POST -H "x-api-key: $TOKEN" -H "Content-Type: application/json" \
  -d '{"composeId":"yP8q8tXHmGGiKhusSK-h8","title":"manual"}' \
  "$DOKPLOY/api/compose.deploy"
```

### Acesso direto aos containers (via SSH no Oracle)

```bash
sg docker -c "docker ps --filter name=projetos-chatvsanexus"
sg docker -c "docker logs projetos-chatvsanexus-er02mp-api-1 --tail 50"
sg docker -c "docker exec projetos-chatvsanexus-er02mp-db-1 psql -U postgres -d whatsapp_langchain -c '...'"
```

## Gotchas operacionais

### 1. Container conflict no autoDeploy
Erro recorrente: `Error response from daemon: container name "/X" is already in use`.
**Causa**: Dokploy não espera container antigo morrer antes de criar novo.
**Fix**:
```bash
# Identificar container "Created" sem nome final
docker ps -a --filter name=X --format "{{.Names}} {{.Status}}"
# Renomear + start
docker rm <antigo-name>
docker rename <hash_X> X
docker start X
```

### 2. Migrations rodam no boot do API
Se migration tem erro de SQL, **API entra em crashloop**. Fix:
- Aplicar migration manualmente via psql
- `INSERT INTO _migrations (name) VALUES (...)` pra marcar como aplicada
- `docker restart api`

### 3. Frontend usa Turbopack
`lib/api.ts` é **server-only** (importa `next/headers` + `auth` + `pg`). Client Components NÃO podem importar dele. Pattern correto: Server Actions wrappers.

### 4. SSH/exec via `sg docker`
Memória: opc no grupo docker mas precisa `sg docker -c "..."` em sessões não-relogadas (memória [[02-Areas/Observabilidade]]).

## ADRs relacionados

- [[03-Resources/ADRs/ADR-008-Dokploy-vs-Kubernetes]] — por que Dokploy

## Relacionados

- [[03-Resources/Reference-Dokploy]] — comandos + IDs detalhados
- [[02-Areas/Observabilidade]]
