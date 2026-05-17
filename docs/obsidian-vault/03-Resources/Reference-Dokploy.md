---
title: Dokploy — comandos e IDs do deploy Nexus
type: resource
status: ativo
priority: alta
created: 2026-05-04
updated: 2026-05-17
tags: [dokploy, deploy, infra, referencia, ops]
empresa: VSA-Tech
responsavel: Vinicius-Andrade
categoria: referencia-tecnica
area: Infra-Producao
projeto_pai:
relacionados: [Infra-Producao]
stakeholders: [Vinicius-Andrade]
deadline:
progresso:
---

# Dokploy — comandos e IDs do deploy Nexus

## Base

- **Painel**: `https://dockploy.vsatecnologia.com.br`
- **Token** (chmod 600): `~/.config/dokploy/token`
- **Auth**: header `x-api-key: $TOKEN`

## IDs do Compose Nexus

| Recurso | ID |
|---|---|
| Project | (lookup via `/api/project.all`) |
| Compose service | `yP8q8tXHmGGiKhusSK-h8` |
| Title | `chat-vsanexus` |
| Compose file | `docker-compose.yml` (repo root) |
| Source | GitHub `viniciusandradde/whatsapp-langchain` branch `master` |
| Auto-deploy | ON (webhook GitHub) |

## Comandos frequentes

```bash
TOKEN=$(cat ~/.config/dokploy/token)
DOKPLOY=https://dockploy.vsatecnologia.com.br
COMPOSE_ID=yP8q8tXHmGGiKhusSK-h8

# Detail compose
curl -sS -H "x-api-key: $TOKEN" \
  "$DOKPLOY/api/compose.one?composeId=$COMPOSE_ID" | jq

# Listar deploys
curl -sS -H "x-api-key: $TOKEN" \
  "$DOKPLOY/api/compose.one?composeId=$COMPOSE_ID" | jq '.deployments[:5]'

# Deploy manual
curl -X POST -H "x-api-key: $TOKEN" -H "Content-Type: application/json" \
  -d "{\"composeId\":\"$COMPOSE_ID\",\"title\":\"manual\"}" \
  "$DOKPLOY/api/compose.deploy"

# Get/set env vars
curl -sS -H "x-api-key: $TOKEN" \
  "$DOKPLOY/api/compose.one?composeId=$COMPOSE_ID" | jq -r '.env'

curl -X POST -H "x-api-key: $TOKEN" -H "Content-Type: application/json" \
  -d "{\"composeId\":\"$COMPOSE_ID\",\"env\":\"KEY=val\\nOUTRA=val2\"}" \
  "$DOKPLOY/api/compose.update"

# Domains
curl -sS -H "x-api-key: $TOKEN" \
  "$DOKPLOY/api/domain.byComposeId?composeId=$COMPOSE_ID" | jq
```

## Gotchas críticos

### 1. Container name conflict no autoDeploy
Erro recorrente: `Error response from daemon: container name "/X" is already in use`.

**Causa**: Dokploy não espera container antigo morrer antes de criar novo.

**Fix manual** (via SSH no Oracle):
```bash
sg docker -c '
docker ps -a --filter name=projetos-chatvsanexus-er02mp-api --format "{{.Names}} {{.Status}}"
docker rm projetos-chatvsanexus-er02mp-api-1
docker rename <hash_da_imagem_nova> projetos-chatvsanexus-er02mp-api-1
docker start projetos-chatvsanexus-er02mp-api-1
'
```

### 2. Bug do `addPrefix` quando path != "/"
Domain com `path != "/"` (ex: `/api`) + addPrefix true → Traefik dropa requests. Memória [[reference_dokploy]] tem detalhe. Workaround: usar `path: "/"` em domínios separados.

### 3. Reset de env não restarta containers
Mudar env via API NÃO restarta. Precisa `compose.deploy` manual ou push novo.

### 4. Auto-deploy gargalo no build ARM
Build no ARM (Oracle A1) demora ~3-5min. Push pequeno = espera. Skip via flag `[skip ci]` no commit não funciona (Dokploy não respeita).

## Estrutura compose (referência)

```yaml
services:
  db:
    image: postgres:15
    volumes: [postgres_data:/var/lib/postgresql/data]
  api:
    build: { context: . }
    command: uvicorn whatsapp_langchain.server.main:app --host 0.0.0.0 --port 8000
    depends_on: [db]
  worker-1: # ... worker-4
    build: { context: . }
    command: python -m whatsapp_langchain.worker.main
    depends_on: [db]
  frontend:
    build: { context: ./frontend }
    command: npm start
```

## Relacionados

- [[02-Areas/Infra-Producao]]
- [[03-Resources/Stack-Tecnico]]
