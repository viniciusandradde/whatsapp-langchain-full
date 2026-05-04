# WhatsApp LangChain

Harness educacional e production-ready para agentes de WhatsApp com LangGraph.

## O que é?

Um harness completo e production-ready que conecta agentes de IA ao WhatsApp. Você define o comportamento do agente com LangChain/LangGraph, e a infraestrutura do projeto cuida do resto: recebimento de mensagens, processamento assíncrono, memória e operação.

O objetivo deste repositório é ensinar arquitetura de harness em volta do agente:
- entrada confiável de mensagens
- processamento assíncrono
- persistência de contexto e memória
- observabilidade, retries e limites

## O que o projeto inclui

- API FastAPI com webhook Twilio assíncrono (`/webhook/twilio`)
- fila em PostgreSQL com debounce e retry
- worker assíncrono para processamento LangGraph
- bootstrap de schema LangGraph no startup (sem criação lazy no primeiro request)
- ciclo de vida explícito no worker para `checkpointer`/`store` (abertos no boot e reutilizados)
- checkpointer PostgreSQL (`thread_id`) para contexto por conversa
- memória semântica com `AsyncPostgresStore` + embeddings (`user_id`)
- middleware de contexto (`trim`, `summarize`, `none`)
- tools de memória semântica (`save_memory` e `read_memory`)
- processamento de mídia (imagem e áudio) via OpenRouter multimodal
- rate limit por telefone (in-memory)
- rotas administrativas (`/api/agents`, `/api/chats`, `/api/metrics`)
- endpoint síncrono educacional (`/webhook/sync`)
- validação criptográfica de `X-Twilio-Signature`
- envio real de resposta via Twilio Messages API
- typing indicator via Twilio antes do processamento
- documentação de sandbox/webhook/túnel com cloudflared
- frontend/admin panel integrado neste repositório
- autenticação via Better Auth no mesmo PostgreSQL
- proteção das rotas administrativas com `INTERNAL_SERVICE_TOKEN`
- deploy documentado para Railway
- documentação e artefatos de stress testing
- documentação de integração Twilio reescrita (sandbox vs produção separados)
- checklist de cutover sandbox → produção
- rollback documentado (deploy e Twilio)
- branding mínimo da VSA Tech no painel (favicon, cores, metadados)
- **CORS estrito** via `FRONTEND_ORIGINS` (lista CSV de origens permitidas)
- **cabeçalhos de segurança** automáticos: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` + `Strict-Transport-Security` em produção
- **fail-fast no startup em produção**: levanta `ValueError` se faltar token forte (≥32 chars), `VALIDATE_TWILIO_SIGNATURE=true` ou `FRONTEND_ORIGINS` não-vazio
- **rate limit distribuído opcional** via Postgres (sliding window por hora) — habilite com `RATE_LIMIT_DISTRIBUTED=true` para multi-instância
- **suporte a múltiplas mídias** num único webhook (`NumMedia > 1`) — N rows independentes com mesmo `message_id`, processadas em ordem como turns separados pelo agente
- **smoke test e2e com Twilio real** (opt-in, custa crédito): `make test-twilio-smoke` valida webhook → worker → outbound REAL → `mark_done`
- **multi-provider WhatsApp** (M2.b): além de Twilio sandbox/prod/WABA, suporta [Evolution API](docs/EVOLUTION.md) (não-oficial, baseada em Baileys) — webhook `/webhook/evolution`, cliente outbound dedicado, multi-instância via `payload_json.instance_name`. Worker resolve cliente por `conexao.provider` via `OutboundClient` Protocol; suporta WhatsApp LID (Linked Identity) automaticamente
- **rate limit em endpoints admin** (60 req/min/user) e login Better Auth (5 tentativas/15 min por IP) — sliding window distribuído via tabela `rate_limit_bucket` (migration 022)
- **hooks com retry exponencial + DLQ**: backoff 1s/5s/25s, 3 tentativas; falhas finais persistidas em `hook_dead_letter` (migration 023) com endpoints `GET/POST /api/hooks/dead-letter` pra retry manual
- **gestão de usuários**: coluna `auth.user.status` (active/disabled) bloqueia login e mata sessões em <30s; reset de senha sem SMTP via "link manual" (`auth.password_reset_pending`); botões UI em `/companies/[id]/members`; histórico de acesso com IP/User-Agent em `/settings/security/login-history` (migration 026)
- **SSO Google** (opcional): reusa o mesmo OAuth Client do Calendar — basta adicionar redirect URI `https://<domínio>/api/auth/callback/google` no Google Cloud Console. Veja [docs/AUTH.md](docs/AUTH.md)
- **correlation ID** propagado API↔worker via header `X-Request-Id` + bind no structlog contextvars (todos logs do request ganham `request_id=X`)
- **outbound manual roteado por provider**: composer no painel envia via Twilio OU Evolution conforme `Conexao.provider`, não mais hardcoded
- **Calendar Agent v2** (S1+S2 entregues, plano de 5 sprints):
  - 7 tools no agente: `calendar_get_current_time`, `calendar_list_calendars`, `calendar_set_active_calendar`, `calendar_list_events`, `calendar_find_free_slots`, `calendar_create_event`, `calendar_cancel_event`
  - Source-of-truth interno em tabela `agendamento` (migration 027): INSERT local antes de chamar Google, drift compensation se Google falha
  - Hooks `agendamento.criado` e `agendamento.cancelado` em `EVENTOS_VALIDOS`
  - Endpoint `GET /api/agendamentos?inicio&fim&status&cliente_id` pra UI/integração externa
  - Pendentes (próximos sprints): regras de negócio configuráveis (S3), aprovação via WhatsApp ao gestor (S4), sync periódico Google→DB + reschedule + audit (S5)
- **stress test com Locust** (Evolution + Twilio): `make stress-evolution`, `make stress-twilio`, `make stress-both` com defaults `-u 10 -r 2 -t 60s` (sobrescrevíveis via `USERS=`, `RATE=`, `TIME=`, `HOST=`); fallback Docker pra ambientes sem `uv`
- **deploy Dokploy** documentado em [docs/DOKPLOY.md](docs/DOKPLOY.md): compose dedicado (`docker-compose.dokploy.yml`), passo a passo de Project + Compose service + Domains + envs

O harness foi desenhado para funcionar tanto em desenvolvimento local
(`sandbox`/`mock`) quanto em ambiente publicado com Twilio real. Para o fluxo
de cutover para número real, veja [Integração Twilio](docs/TWILIO.md) e
[Deploy](docs/DEPLOY.md). Para integrar Evolution API, veja
[Integração Evolution](docs/EVOLUTION.md).

## Arquitetura

![Arquitetura](docs/diagrams/harness_whatsapp.jpg)

Fluxo principal:

```text
WhatsApp/Twilio -> API (/webhook/twilio) -> PostgreSQL (message_queue)
                                              -> Worker -> LangGraph Agent
                                              -> PostgreSQL (response, conversation)
```

Separar API e Worker evita bloqueio na borda HTTP e melhora confiabilidade sob carga.

## Quick Start

### 1. Setup

```bash
git clone <repo-url>
cd whatsapp-langchain
make setup
cp .env.example .env
```

Edite o `.env` e configure pelo menos:

```bash
OPENROUTER_API_KEY=sk-or-v1-...
INTERNAL_SERVICE_TOKEN=seu-token-local
BETTER_AUTH_SECRET=seu-secret-local
TWILIO_OUTBOUND_MODE=mock
```

`INTERNAL_SERVICE_TOKEN` e `BETTER_AUTH_SECRET` precisam estar preenchidos
mesmo em desenvolvimento local para o painel administrativo funcionar.

### 2. Suba o stack local

```bash
make up
# sobe: db + api + worker + frontend
```

Para validar envio real pelo Twilio, mude `TWILIO_OUTBOUND_MODE=real` e
configure `TWILIO_ACCOUNT_SID`, `TWILIO_API_KEY_SID`,
`TWILIO_API_KEY_SECRET` e `TWILIO_FROM_NUMBER`. Nesse modo o worker faz
fail-fast se alguma credencial outbound estiver ausente. Para assinatura
de webhook público, veja [Integração Twilio](docs/TWILIO.md).

### Acesso ao banco (DBeaver)

Use estes dados de conexão PostgreSQL:

- Host: `localhost`
- Port: `5432`
- Database: `whatsapp_langchain`
- User: `postgres`
- Password: `postgres`

Valide saúde da API:

```bash
curl http://localhost:8000/health
```

### 3. Teste rápido (endpoint síncrono)

```bash
curl -X POST "http://localhost:8000/webhook/sync?agent=vsa_tech" \
  -H "Content-Type: application/json" \
  -d '{"phone":"+5511999999999","message":"Olá!"}'
```

### 4. Teste assíncrono (simulando Twilio)

```bash
curl -X POST "http://localhost:8000/webhook/twilio?agent=vsa_tech" \
  -d "MessageSid=SM123" \
  -d "From=whatsapp:+5511999999999" \
  -d "To=whatsapp:+14155238886" \
  -d "Body=Quero aprender harness para agentes" \
  -d "NumMedia=0"
```

Acompanhe métricas:

```bash
curl http://localhost:8000/api/metrics
curl http://localhost:8000/api/chats
```

### 5. Múltiplas mídias num único webhook (`NumMedia > 1`)

```bash
curl -X POST "http://localhost:8000/webhook/twilio?agent=vsa_tech" \
  -d "MessageSid=SM_MULTI_001" \
  -d "From=whatsapp:+5511999999999" \
  -d "To=whatsapp:+14155238886" \
  -d "Body=olha as fotos" \
  -d "NumMedia=2" \
  -d "MediaUrl0=https://demo.twilio.com/owl.png" \
  -d "MediaContentType0=image/png" \
  -d "MediaUrl1=https://demo.twilio.com/owl.png" \
  -d "MediaContentType1=image/png"
```

A API enfileira 1 row de texto + 2 rows de mídia, todas com o mesmo `message_id`.
O worker processa cada uma como turn separado do agente; o checkpointer LangGraph
agrega o histórico por `thread_id`. Twilio limita a 10 mídias por webhook — o
parser respeita esse cap.

## Hardening de produção

Em `ENVIRONMENT=production` o startup faz **fail-fast** se qualquer destes
invariantes falhar:

| Invariante | Variável | Critério |
|------------|----------|----------|
| Token interno presente | `INTERNAL_SERVICE_TOKEN` | não-vazio |
| Token forte em prod | `INTERNAL_SERVICE_TOKEN` | ≥ 32 caracteres |
| Signature obrigatória | `VALIDATE_TWILIO_SIGNATURE` | `true` |
| CORS configurado | `FRONTEND_ORIGINS` | pelo menos 1 origem |

Cabeçalhos de segurança aplicados automaticamente em toda resposta:

| Header | Dev | Prod |
|--------|-----|------|
| `X-Content-Type-Options: nosniff` | ✓ | ✓ |
| `X-Frame-Options: DENY` | ✓ | ✓ |
| `Referrer-Policy: no-referrer` | ✓ | ✓ |
| `Strict-Transport-Security` (1 ano) | — | ✓ |

`FRONTEND_ORIGINS` aceita CSV (ex: `https://chat.nexus.com,https://admin.chat.nexus.com`)
e o middleware CORS restringe `allow_methods` a verbos HTTP padrão e
`allow_headers` a `Authorization, Content-Type, X-Twilio-Signature`. Veja
[Deploy](docs/DEPLOY.md) para o checklist completo.

## Rate limit distribuído (multi-instância)

Por padrão, o rate limit por telefone é in-memory por processo
(`RATE_LIMIT_DISTRIBUTED=false`). Em deploys multi-instância isso permite que
um mesmo número estoure `N × RATE_LIMIT_PER_HOUR` requisições/hora.

Para ativar o sliding window distribuído em Postgres:

```bash
# 1. Configurar
RATE_LIMIT_DISTRIBUTED=true

# 2. Aplicar a migration nova
make migrate
# aplica db/migrations/005_rate_limit_buckets.sql
```

A função `_check_rate_limit_db` faz `INSERT ... ON CONFLICT DO UPDATE` atômico
contra a tabela `rate_limit_buckets` (PK `(phone_number, hour_start)`). O
cleanup de buckets > 24h roda inline com 1% de probabilidade — sem cron, sem
Redis. Mensagem de erro 429 e log `rate_limit_exceeded` são consistentes
entre os dois backends.

## Smoke test e2e com Twilio real

Antes do cutover sandbox→produção, rode o smoke test que valida o ciclo
completo (webhook simulado → worker → outbound REAL via Twilio Messages API
→ `mark_done`):

```bash
# 1. Stack rodando com TWILIO_OUTBOUND_MODE=real e credenciais válidas
make up

# 2. Configurar número de teste descartável
export TWILIO_LIVE_TESTS=1
export TWILIO_TEST_TO_NUMBER="+5511999999999"

# 3. Rodar smoke
make test-twilio-smoke
```

Características:

- **Opt-in duplo**: `TWILIO_LIVE_TESTS` precisa ser truthy E `TWILIO_TEST_TO_NUMBER` precisa começar com `+` (E.164)
- **Health check**: a fixture confirma que API e DB respondem antes de tentar enviar
- **Excluído de CI**: o marker `twilio_real` é filtrado em `make ci` e `make test`
- **Custos**: ~USD 0.005–0.05 por execução (1 mensagem real). Não rode em loop.

Veja [Integração Twilio](docs/TWILIO.md) para o checklist completo de cutover.

## Estrutura do Projeto

```text
whatsapp-langchain/
├── src/whatsapp_langchain/
│   ├── agents/        # Catálogo de agentes, middleware e tools
│   ├── server/        # API FastAPI (webhooks + admin APIs)
│   ├── worker/        # Loop consumidor da fila e execução dos agentes
│   └── shared/        # Config, DB, fila, modelos, logging, factory LLM
├── db/migrations/     # Schema SQL (fila + conversas + vector)
├── docs/              # Documentação técnica e onboarding
└── tests/             # Unit e integração
```

## Aprendizado (foco em harness)

Este projeto é para aprender decisões de engenharia reais:
- fronteiras entre serviços (`server`, `worker`, `shared`)
- contratos de dados (`MessageQueue`, `Conversation`, webhook payload)
- estados e transições (`queued -> processing -> done/failed`)
- consistência operacional (retry com backoff, debounce, lease)
- limites e custo (rate limit HTTP e rate limit de LLM)

Para detalhes técnicos:
- [Arquitetura](docs/ARCHITECTURE.md)
- [Primeiros Passos](docs/GETTING_STARTED.md)
- [Criando Agentes](docs/ADDING_AGENTS.md)
- [Banco de Dados](docs/DATABASE.md)
- [Integração Twilio](docs/TWILIO.md)
- [Integração Evolution API](docs/EVOLUTION.md) — provider WhatsApp não-oficial (Baileys)
- [Deploy](docs/DEPLOY.md)
- [Diagramas](docs/diagrams/)



## Comandos úteis

```bash
make help                 # lista todos os targets
make api                  # roda API local (uvicorn)
make worker               # roda Worker local
make migrate              # aplica migrações pendentes
make test                 # suite normal (exclui docker_demo e twilio_real)
make test-live            # testes live com OpenRouter real (gating OPENROUTER_LIVE_TESTS=1)
make test-demo            # testes Docker realísticos (marker docker_demo)
make test-twilio-smoke    # smoke e2e com Twilio real (gating TWILIO_LIVE_TESTS=1, custa $$)
make check                # ruff + pyright (sem alterar arquivos)
make ci                   # check + suite normal (o que CI roda)
make logs                 # docker compose logs -f
make reset                # rebuild Docker do zero (down -v + up --build)
```

## Licença

[VSA Tech Community License](LICENSE) - uso restrito a membros da comunidade [VSA Tech](https://chat.nexus.com).
