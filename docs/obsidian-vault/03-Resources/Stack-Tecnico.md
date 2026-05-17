---
title: Stack técnica — versões e papéis
type: resource
status: ativo
priority: media
created: 2026-05-04
updated: 2026-05-17
tags: [stack, tech, referencia]
empresa: VSA-Tech
responsavel: Vinicius-Andrade
categoria: referencia-tecnica
area: Infra-Producao
projeto_pai:
relacionados: [Infra-Producao, Observabilidade]
stakeholders: [Vinicius-Andrade]
deadline:
progresso:
---

# Stack técnica

## Backend (`src/whatsapp_langchain/`)

| Componente | Versão / Lib | Papel |
|---|---|---|
| Python | 3.12 | Runtime |
| uv | latest | Package manager (locked via `uv.lock`) |
| FastAPI | latest | HTTP edge (`server/`) |
| Uvicorn | latest | ASGI server |
| asyncpg + psycopg | latest | Pool Postgres (psycopg pro LangGraph) |
| LangGraph | latest | Agentes + workflows estáticos (`agents/` + `shared/workflow_runtime.py`) |
| LangChain | latest | Lib bridge (poucos usos diretos, maioria via LangGraph) |
| AsyncPostgresSaver | LangGraph postgres | Checkpointer pra threads de agente |
| AsyncPostgresStore | LangGraph postgres | Store pra memória semântica |
| structlog | latest | Logs JSON + correlation ID |
| pydantic-settings | latest | Config singleton (`shared/config.py::settings`) |
| OpenRouter | API | LLM + embeddings + audio transcription unificados |
| Twilio SDK | latest | WhatsApp inbound HMAC + outbound (modo `real`) |
| Evolution API client | custom | WhatsApp inbound + outbound alternativo |

## Frontend (`frontend/`)

| Componente | Versão / Lib | Papel |
|---|---|---|
| Next.js | 16 | App Router + Server Components + Server Actions |
| React | 19 | UI lib |
| TypeScript | 5.x | Type system |
| Tailwind CSS | 4.x | Styling |
| Better Auth | latest | Auth (email+password, Google SSO opt-in) |
| shadcn/ui | latest | Componentes base (Button, Dialog, etc.) |
| `pg` (node-postgres) | latest | Driver pro Better Auth no schema `auth` |
| Turbopack | latest | Dev bundler (atenção: `lib/api.ts` é server-only) |

## Banco

- **Postgres 15+** (single instance)
- Schemas: `public` (app), `auth` (Better Auth)
- Tabelas LangGraph: `checkpoints*`, `store*` (criadas em-code via `bootstrap_langgraph_schema()`)
- **71+ migrations** em `db/migrations/` controladas por `_migrations` + advisory lock `8_642_000`

## Infra

- **Oracle Cloud ARM** (Ampere A1, tier gratuito)
- **Dokploy** (compose service `chat-vsanexus`)
- **Domínios**: `chat.vsanexus.com` (FE), `api.vsanexus.com` (BE)
- **Auto-deploy**: GitHub webhook → push master → Dokploy build + recreate

## Integrações externas

| Provedor | Uso | Auth |
|---|---|---|
| OpenRouter | LLM + embeddings + audio | API key (`OPENROUTER_API_KEY`) |
| Twilio | WhatsApp Twilio Sandbox + WABA | Account SID + API Key SID/Secret |
| Evolution API | WhatsApp não-oficial (multi-instância) | URL + token por conexão |
| Google Calendar | Agendamentos | OAuth2 por empresa |
| Google SSO | Login painel | OAuth2 client (opt-in) |
| LangSmith | Tracing LLM | API key (`LANGSMITH_API_KEY`) |
| GitHub | Source + auto-deploy | Webhook |

## Pastas críticas

- `src/whatsapp_langchain/server/` — FastAPI HTTP edge
- `src/whatsapp_langchain/worker/` — async loop processando `message_queue`
- `src/whatsapp_langchain/shared/` — config, db, queue, llm, helpers comuns
- `src/whatsapp_langchain/agents/catalog/` — agentes (cada um numa pasta)
- `frontend/src/app/` — App Router pages
- `frontend/src/components/` — Client + Server Components reusáveis
- `frontend/src/lib/` — server-only utils (auth.ts, api.ts)
- `db/migrations/` — SQL migrations numeradas
- `docs/` — documentação Markdown
- `docs/obsidian-vault/` — este vault PARA
- `tests/unit/` + `tests/integration/` — pytest com `asyncio_mode = "auto"`

## Relacionados

- [[02-Areas/Infra-Producao]]
- [[02-Areas/Observabilidade]]
- [[03-Resources/Reference-Dokploy]]
