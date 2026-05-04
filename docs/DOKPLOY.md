# Dokploy — guia passo a passo

Este guia cobre o deploy da stack `whatsapp-langchain` no Dokploy
hospedado no mesmo host (`vps-docker03` / Oracle Cloud), com 4 serviços:
**db, api, worker, frontend**, expostos publicamente em
`https://chat.vsanexus.com` via Traefik (já incluso no Dokploy) com SSL
automático Let's Encrypt.

> **Decisão:** vamos subir como **1 serviço Compose único** (não 4 apps
> separadas). O motivo está em [Apêndice A](#apêndice-a--por-que-compose-e-não-4-apps-separadas).

---

## Pré-requisitos

- [ ] Painel Dokploy acessível (atualmente em `:3000` no host —
  verificar URL do painel no seu setup; geralmente algo como
  `http://10.0.0.118:3000` ou domínio público que o Dokploy esteja servindo)
- [ ] Conta admin no Dokploy
- [ ] Acesso ao repo `viniciusandradde/whatsapp-langchain-full`
  (público OU GitHub App instalada no Dokploy se privado)
- [ ] DNS de `chat.vsanexus.com` apontando pro **IP público** da Oracle
  Cloud (registro A). Sem isso, Let's Encrypt falha o desafio HTTP-01.
- [ ] Stack standalone atual (`/home/dev/projetos/whatsapp-langchain`)
  **derrubada antes do primeiro deploy** — senão conflito de
  `container_name` (`chat-nexus-*`) e do volume `whatsapp-langchain_postgres_data`.
  Comando: `sg docker -c "docker compose down"` na pasta do projeto.

---

## Visão geral

| Etapa | Ação | Onde |
|---|---|---|
| 1 | Preparar `docker-compose.dokploy.yml` (sem `ports:`) | Repo (commit) |
| 2 | Criar projeto + serviço Compose no Dokploy | Painel |
| 3 | Conectar repo Git + branch `master` + compose path | Painel → Source |
| 4 | Setar variáveis de ambiente | Painel → Environment |
| 5 | Configurar domínio `chat.vsanexus.com` + SSL | Painel → Domains |
| 6 | Deploy | Painel → Deploy |
| 7 | Validar | curl / browser |
| 8 | Apontar webhook Evolution pro novo URL | Evolution server |

---

## Passo 1 — Preparar compose pra Dokploy

O `docker-compose.yml` atual mapeia portas no host (`8000:8000`,
`5432:5432`, `3000:3000`). Em produção via Dokploy/Traefik, **não
queremos isso** — o roteamento é feito por labels Traefik e os
containers ficam só na rede interna.

Crie `docker-compose.dokploy.yml` na raiz do repo:

```yaml
# Compose dedicado pro Dokploy.
# Diferenças do docker-compose.yml local:
# - sem `ports:` (Traefik roteia)
# - frontend recebe labels Traefik
# - DATABASE_URL e BETTER_AUTH_URL vêm das envs do painel

services:
  db:
    build:
      context: .
      dockerfile: Dockerfile.db
    environment:
      POSTGRES_DB: whatsapp_langchain
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      retries: 5
    restart: unless-stopped

  api:
    build:
      context: .
      dockerfile: Dockerfile.api
    env_file: .env
    environment:
      DATABASE_URL: postgresql://postgres:${POSTGRES_PASSWORD}@db:5432/whatsapp_langchain
      LOG_JSON: "true"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 3s
      retries: 5
      start_period: 15s
    depends_on:
      db:
        condition: service_healthy
    restart: unless-stopped

  worker:
    build:
      context: .
      dockerfile: Dockerfile.worker
    env_file: .env
    environment:
      DATABASE_URL: postgresql://postgres:${POSTGRES_PASSWORD}@db:5432/whatsapp_langchain
      LOG_JSON: "true"
    depends_on:
      db:
        condition: service_healthy
    restart: unless-stopped

  frontend:
    build:
      context: .
      dockerfile: Dockerfile.frontend
    env_file: .env
    environment:
      INTERNAL_API_URL: http://api:8000
      DATABASE_URL: postgresql://postgres:${POSTGRES_PASSWORD}@db:5432/whatsapp_langchain
      PORT: "3000"
    depends_on:
      api:
        condition: service_healthy
    restart: unless-stopped

volumes:
  postgres_data:
```

**Commit + push:**
```bash
git add docker-compose.dokploy.yml
git commit -m "chore(docker): compose dedicado pro Dokploy (sem ports, Traefik routing)"
git push origin master
```

> **Por que ler `.env` via `env_file:` e ainda assim setar envs no
> painel?** O Dokploy pode injetar via `.env` no diretório de build, OU
> sobrescrever via UI. Se você marcar "Build & Runtime variables" no
> painel, ele cria `.env` no checkout antes do `docker compose up`.

---

## Passo 2 — Criar projeto + serviço Compose

1. Painel Dokploy → **Projects** → **+ Create Project**
2. Nome: `whatsapp-langchain` (ou `chat-vsanexus`)
3. Descrição opcional
4. Dentro do projeto criado: **+ Create Service** → **Compose**
5. Service Name: `chat-nexus`

---

## Passo 3 — Conectar repositório

Na aba **Source** (ou **General → Provider**) do serviço Compose:

| Campo | Valor |
|---|---|
| Provider | **GitHub** (instalar GitHub App se ainda não — segue o wizard do Dokploy) |
| Repository | `viniciusandradde/whatsapp-langchain-full` |
| Branch | `master` |
| Auto Deploy | ✅ habilitar (push em master = redeploy) |
| Compose Path | `docker-compose.dokploy.yml` |
| Compose Type | `docker compose` (não `docker stack`/Swarm — a stack atual usa healthcheck `depends_on`, que Swarm ignora) |

**Salvar.**

---

## Passo 4 — Variáveis de ambiente

Aba **Environment** do serviço.

Cole o conteúdo do `.env` atual (`/home/dev/projetos/whatsapp-langchain/.env`),
fazendo as seguintes substituições/adições:

```env
# === Adicionar no topo (não está no .env de dev) ===
POSTGRES_PASSWORD=<gere-uma-senha-forte-aqui>

# === Confirmar/ajustar ===
ENVIRONMENT=production
LOG_JSON=true
LOG_LEVEL=info

DATABASE_URL=postgresql://postgres:${POSTGRES_PASSWORD}@db:5432/whatsapp_langchain
INTERNAL_API_URL=http://api:8000

# === Domínio + auth (já corretos no .env atual) ===
BETTER_AUTH_URL=https://chat.vsanexus.com
BETTER_AUTH_TRUSTED_ORIGINS=https://chat.vsanexus.com
FRONTEND_ORIGINS=https://chat.vsanexus.com
GOOGLE_OAUTH_REDIRECT_URI=https://chat.vsanexus.com/api/google-calendar/oauth/callback

# === Hardening de produção ===
INTERNAL_SERVICE_TOKEN=<token-forte-min-32-chars-DIFERENTE-do-dev>
BETTER_AUTH_SECRET=<segredo-forte-min-32-chars-DIFERENTE-do-dev>
VALIDATE_TWILIO_SIGNATURE=true   # se for usar Twilio real
```

**Críticos pra trocar antes do primeiro deploy:**
- `POSTGRES_PASSWORD` — não pode ficar `postgres/postgres`
- `INTERNAL_SERVICE_TOKEN` — em prod, `Settings.validate_runtime_settings()`
  exige ≥32 chars; bypass é via mantém o token interno API↔Frontend
- `BETTER_AUTH_SECRET` — usado pra assinar sessões; trocar pra valor único
- `ADMIN_PASSWORD` — primeiro login bootstrap; trocar de `changeme`

**Manter como está:**
- Chaves OpenRouter, LangSmith, Evolution (são as credenciais válidas)
- `EVOLUTION_OUTBOUND_MODE=real`

**Salvar.**

---

## Passo 5 — Domínio + SSL

Aba **Domains** do serviço Compose.

1. **+ Add Domain**
2. Preencher:

| Campo | Valor |
|---|---|
| Host | `chat.vsanexus.com` |
| Path | `/` (default) |
| Container | `frontend` (selecionar do dropdown — Dokploy lista os services do compose) |
| Container Port | `3000` |
| HTTPS | ✅ ativar |
| Certificate Provider | **Let's Encrypt** |

3. **+ Add Domain** (segundo, pra webhooks da API):

| Campo | Valor |
|---|---|
| Host | `chat.vsanexus.com` |
| Path | `/webhook` |
| Container | `api` |
| Container Port | `8000` |
| HTTPS | ✅ |
| Certificate | **Let's Encrypt** (mesmo cert) |

4. (opcional, se quiser API admin externamente também):

| Host | Path | Container | Port |
|---|---|---|---|
| `chat.vsanexus.com` | `/api` | `api` | `8000` |
| `chat.vsanexus.com` | `/health` | `api` | `8000` |

> Frontend já chama `INTERNAL_API_URL=http://api:8000` server-side pela
> rede interna do compose, então `/api` externo só é necessário se
> alguma chamada client-side bater direto na API. Hoje, **não bate** —
> mas Twilio/Evolution sim, daí o `/webhook`.

**Salvar.**

---

## Passo 6 — Deploy

Aba **General** → botão **Deploy**.

O Dokploy vai:
1. Clonar `viniciusandradde/whatsapp-langchain-full` branch `master`
2. Renderizar `.env` com as variáveis do painel
3. `docker compose -f docker-compose.dokploy.yml build`
4. `docker compose -f docker-compose.dokploy.yml up -d`
5. Aguardar healthchecks (`db` healthy → `api` healthy → `frontend` start)
6. Configurar Traefik com os labels dos domains adicionados

**Logs em tempo real:** aba **Deployments** → seleciona o deploy
ativo → **Logs**.

Tempo esperado: ~5-10 min no primeiro build (sem cache); 1-3 min nos
deploys seguintes.

---

## Passo 7 — Validar

Do host:
```bash
# Health da API via domínio público
curl https://chat.vsanexus.com/health

# Esperado: {"status":"ok","database":"connected","version":"0.1.0"}

# Frontend
curl -I https://chat.vsanexus.com
# Esperado: HTTP 307 (redirect /login)

curl -I https://chat.vsanexus.com/login
# Esperado: HTTP 200
```

No browser:
1. `https://chat.vsanexus.com/login`
2. Login com `ADMIN_EMAIL` / `ADMIN_PASSWORD` definidos nas envs
3. Bootstrap automático cria o user no schema `auth` na primeira tentativa

Logs do worker (no painel Dokploy → service `worker` → Logs):
```
clients_ready twilio_mode=mock evolution_mode=real evolution_instance=vsa-tecnologia
worker_ready providers=[evolution, twilio_prod, twilio_sandbox, waba]
```

---

## Passo 8 — Apontar webhook Evolution

Na Evolution server externa (`https://evolutionapi.vsatecnologia.com.br`):

```bash
curl -X POST https://evolutionapi.vsatecnologia.com.br/webhook/set/vsa-tecnologia \
  -H "apikey: $EVOLUTION_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "webhook": {
      "enabled": true,
      "url": "https://chat.vsanexus.com/webhook/evolution",
      "events": ["MESSAGES_UPSERT"]
    }
  }'
```

**Smoke E2E:** envie mensagem WhatsApp pro número
`+5567984249725` (instância `vsa-tecnologia`). Logs do worker no
Dokploy devem mostrar `agent_loaded` + resposta enviada de volta.

---

## Caveats / pegadinhas

### Conflito com a stack standalone
Antes do primeiro deploy Dokploy, **derrubar** a stack manual:
```bash
cd /home/dev/projetos/whatsapp-langchain
sg docker -c "docker compose down"
```
Senão `container_name: chat-nexus-*` colide e o Dokploy falha o `up`.

### Volume Postgres
Dokploy nomeia o volume como `<projeto>_postgres_data` (ou similar
prefixado). **Não é o mesmo** volume da stack standalone
(`whatsapp-langchain_postgres_data`). Resultado: **DB começa vazio** no
Dokploy → migrations rodam do zero, bootstrap cria empresa "VSA Tech".

Se quiser **migrar dados**:
```bash
# 1. Antes de derrubar a standalone:
sg docker -c "docker compose exec -T db pg_dump -U postgres whatsapp_langchain > /tmp/wl-dump.sql"

# 2. Depois do deploy Dokploy + db healthy:
sg docker -c "docker exec -i <container-id-do-db-dokploy> psql -U postgres -d whatsapp_langchain < /tmp/wl-dump.sql"
```

### Auto Deploy + push em master
Se ✅ habilitado, qualquer `git push` rebuilds tudo. Pra hotfix sem
redeploy: trabalhe em branch `hotfix/*`, abra PR; só merge em `master`
quando quiser deploy. Pra desabilitar temporariamente: aba Source →
toggle off.

### Migrations
O worker roda migrations no boot via `_migrations` table (idempotente).
Não precisa rodar `make migrate` manual no Dokploy. A primeira deploy
aplica todas 001–020 do zero.

### LangSmith tracing
`LANGCHAIN_TRACING_V2=true` + `LANGCHAIN_API_KEY` no painel = traces
aparecem em smith.langchain.com no projeto `CHAT-NEXUS-AI`.

### Memory store
`MEMORY_ENABLED=false` no .env atual. Se ligar (`true`), o startup
cria as tabelas LangGraph store via `bootstrap_langgraph_schema()` —
idempotente, mas adiciona ~3 tabelas no DB.

---

## Troubleshooting

| Sintoma | Causa provável | Fix |
|---|---|---|
| Deploy falha em `db` healthcheck | senha postgres divergente entre `db` env e `DATABASE_URL` | Confirmar que `${POSTGRES_PASSWORD}` resolve nos dois lugares |
| Cert Let's Encrypt falha | DNS não aponta pro IP público OU porta 80 bloqueada | `dig chat.vsanexus.com` deve retornar IP público; security list Oracle Cloud com 80/443 abertos |
| `502 Bad Gateway` em `chat.vsanexus.com` | container `frontend` ainda não healthy | Aguardar ~30s; se persistir, ver logs do frontend |
| Frontend retorna 500 ao clicar Login | `BETTER_AUTH_URL` ou `INTERNAL_API_URL` errados | Confere envs no painel; recreate frontend |
| Worker nem inicia | `DATABASE_URL` errado OU env_file não populou | Logs do container worker no painel |
| Webhook Twilio rejeita 403 | `VALIDATE_TWILIO_SIGNATURE=true` mas `TWILIO_AUTH_TOKEN` errado | Reconferir token no painel Twilio Console |

---

## Apêndice A — Por que Compose e não 4 apps separadas

Dokploy permite criar 4 "Applications" individuais ao invés de 1
Compose. Vantagens da abordagem 4-apps:
- Deploy independente (atualizar só worker sem mexer no resto)
- Recursos/limites individuais por app

Desvantagens (que pesam mais no nosso caso):
- Cada app cria sua própria rede Docker → precisa **manualmente**
  conectá-las (`docker network connect` ou definir `external: true`
  em rede compartilhada)
- `depends_on: condition: service_healthy` não funciona cross-app —
  worker pode subir antes do db estar pronto
- Você multiplica o trabalho de env vars (4 vezes setando
  `DATABASE_URL`, `OPENROUTER_API_KEY`, etc.)
- O bootstrap do schema LangGraph usa advisory lock pra coordenar
  entre api+worker — assume rede comum
- Custos de UI: 4 telas pra abrir, 4 deploys pra disparar

Se um dia precisar deploy independente do worker (por ex. pra rollback
rápido sem mexer no frontend), divida em **2 composes**:
- `docker-compose.dokploy.yml` → db + api + frontend
- `docker-compose.worker.yml` → só worker (apontando pra DB externo do
  primeiro compose via DATABASE_URL com IP fixo)

Mas pra MVP, 1 Compose é o caminho.

---

## Apêndice B — Migrar de "stack standalone" pra "Dokploy" sem perder dados

Se você quer manter o histórico do banco atual:

```bash
# 1. Dump da stack standalone
cd /home/dev/projetos/whatsapp-langchain
sg docker -c "docker compose exec -T db pg_dump -U postgres -Fc whatsapp_langchain > /tmp/wl-pre-dokploy.dump"

# 2. Derrubar standalone
sg docker -c "docker compose down"

# 3. Subir via Dokploy (passos 1-6 deste guia)

# 4. Aguardar deploy concluir + db healthy

# 5. Restore (substituir <db_container_id> pelo container do db do Dokploy)
DB_ID=$(sg docker -c "docker ps --filter 'label=com.docker.compose.service=db' --format '{{.ID}}' | head -1")
sg docker -c "docker exec -i $DB_ID pg_restore -U postgres -d whatsapp_langchain --clean --if-exists < /tmp/wl-pre-dokploy.dump"

# 6. Rebootar api + worker pra reler schema
# (no painel Dokploy: Restart api e Restart worker)
```

---

## Referências

- `docker-compose.yml` — compose de dev (com bind ports)
- `docker-compose.override.yml` — overrides locais (gitignored)
- `docs/DEPLOY.md` — visão geral de deploy
- `docs/RAILWAY.md` — alternativa Railway (referência histórica)
- `docs/EVOLUTION.md` — webhook Evolution (passo 8 acima)
- `docs/TWILIO.md` — sandbox vs produção
