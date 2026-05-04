# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project context

Educational, production-ready harness around WhatsApp agents built with LangGraph. The repo's pedagogy is the *harness around the agent*, not the agent itself: reliable inbound, async processing, durable context/memory, retries, rate limits, and operability. README and docs are in Portuguese (pt-BR); keep new docs/comments in pt-BR to match.

## Common commands

All Python work goes through `uv` (locked via `uv.lock`). The Makefile is the canonical entry point — prefer `make <target>` over raw commands so behavior matches CI.

Setup and dev:
- `make setup` — `uv venv` + `uv pip install -e ".[dev]"`
- `make up` / `make down` / `make reset` — full Docker stack (db + api + worker + frontend)
- `make db` — Postgres only (used when iterating on `make api`/`make worker`/`make frontend` outside Docker)
- `make migrate` — apply pending SQL migrations from `db/migrations/`
- `make api` — `uvicorn whatsapp_langchain.server.main:app --reload --port 8000`
- `make worker` — `python -m whatsapp_langchain.worker.main`
- `make frontend` — `cd frontend && npm run dev` (Next.js 16 / React 19)
- `make dev` — LangGraph Studio for agent iteration (`uv run langgraph dev`, reads `langgraph.json`)

Quality (these only check style/types, not logic):
- `make check` — `ruff check` + `ruff format --check` + `pyright src/` (run before commit)
- `make fix && make format` — auto-fix + format
- `make ci` — `check` + `pytest -m "not docker_demo"` (what CI runs)

Tests:
- `make test` — full suite minus `docker_demo` marker
- `make test-x` / `make test-v` — fail-fast / verbose
- Single test: `uv run pytest tests/unit/test_queue_claim.py::test_specific -v`
- `make test-live` — live OpenRouter tests; requires real `OPENROUTER_API_KEY` *and* `OPENROUTER_LIVE_TESTS=1` (the conftest fixture skips otherwise; placeholder keys like `sk-or-v1-xxx` are rejected)
- `make test-demo` / `make test-demo-up` — `docker_demo` marker; needs full Docker stack running
- `make test-flows` — realistic flow tests (`tests/integration/test_realistic_flows.py`); needs Docker stack
- pytest is configured `asyncio_mode = "auto"` — async tests don't need `@pytest.mark.asyncio`

Frontend (run from `frontend/`):
- `npm run dev` / `npm run build` / `npm run start` / `npm run lint`
- Frontend needs its own `frontend/.env.local` for `npm run dev` (separate from root `.env`); Docker uses compose env vars instead.

## Architecture

The system intentionally splits into two processes that share Postgres. Understanding the boundary is the prerequisite for almost any change.

**API (`src/whatsapp_langchain/server/`)** — FastAPI HTTP edge. Validates Twilio webhook (HMAC via official Twilio SDK when `VALIDATE_TWILIO_SIGNATURE=true`), applies per-phone rate limit, normalizes payload, and enqueues into `message_queue`. Returns empty TwiML in <100ms. Never invokes the agent inline. `/webhook/sync` exists for development only and is auto-disabled when `ENVIRONMENT=production`. Rate limit do webhook usa in-memory por default (single-process); em multi-instância habilite `RATE_LIMIT_DISTRIBUTED=true` para sliding window em Postgres (tabela `rate_limit_buckets`, migration `005`).

**Three middlewares are stacked in `server/main.py`** (Starlette LIFO — registered last runs first):
- `install_correlation_id` — accepts client `X-Request-Id` or generates UUID16, binds to `structlog.contextvars` so every log of the request carries `request_id=X`. Echoes the ID in response header.
- `install_admin_rate_limit` — sliding window 60 req/min per `user_id` on `/api/*` (excluding `/api/health`). Uses generic `rate_limit_bucket` (migration 022) via `shared/rate_limit.py::enforce_bucket_limit`. Skips OPTIONS (CORS preflight).
- `install_security_headers` — `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` always; `Strict-Transport-Security` in production.

Better Auth has its own `rateLimit` config in `frontend/src/lib/auth.ts` (5 attempts/15min on `/sign-in/email`, 3/15min on `/sign-up/email`, 3/h on `/forget-password`, 5/h on `/reset-password`).

**Worker (`src/whatsapp_langchain/worker/`)** — Async loop polling `message_queue`. Claims a row with `FOR UPDATE SKIP LOCKED` + lease, preprocesses media (image/audio → text via OpenRouter multimodal), sends Twilio typing indicator (best-effort), invokes the LangGraph agent, sends the outbound reply via Twilio, *then* calls `mark_done`. **`mark_done` only runs after the outbound send succeeds** — a Twilio failure flows into `mark_failed`'s retry path. This ordering is load-bearing for at-least-once delivery.

**Postgres is the queue** — no Redis/RabbitMQ. State machine: `queued → processing → done | failed`, with retry going `processing → queued` (with `process_after = NOW() + attempts*5s` backoff) until `attempts >= max_attempts`. Lease expiry on a stuck `processing` row promotes to `failed` only when attempts are exhausted; otherwise the row is reclaimable.

**Debounce semantics** (in `shared/queue.py::enqueue_or_buffer`) — text-only messages from the same `(phone, agent)` within `MESSAGE_BUFFER_SECONDS` are concatenated into a single queued row. Media bypasses debounce *and* flushes any pending text from the same `(phone, agent)` so the worker processes text-then-media in `created_at` order. Concurrent webhooks are serialized via `pg_advisory_xact_lock` keyed on a SHA-256 hash of `phone:agent`. **Múltiplas mídias (NumMedia > 1) em um único webhook são enfileiradas como N rows independentes com o mesmo `message_id`; o worker processa cada uma como turn separado do agente; o checkpointer LangGraph agrega por `thread_id`.**

**LangGraph lifecycle is explicit, not lazy** — the worker opens `AsyncPostgresSaver` (checkpointer) and `AsyncPostgresStore` (semantic memory) once at boot via `open_checkpointer()` / `open_store()` (`shared/db.py`) using `AsyncExitStack`, then reuses them across every message. `bootstrap_langgraph_schema()` runs the LangGraph DDL at startup (gated by advisory lock `8_642_001` so API and Worker cooperate on first boot). Don't reintroduce per-request schema setup.

**Two memory contracts, runtime keys must be set together:**
- `thread_id = "{phone_number}:{agent_id}"` — checkpointer scope (single conversation history)
- `user_id = phone_number` — store scope (semantic, cross-thread; namespace `(user_id, "memories")`)
- The agent factory only exposes `save_memory` / `read_memory` tools when `store` is non-None (i.e. `MEMORY_ENABLED=true`). Conversely, `MEMORY_ENABLED=false` returns `(None, None)` from `open_store` — the agent loads without memory tools rather than failing.

**Agent contract (catalog plug-in)** — agents live at `src/whatsapp_langchain/agents/catalog/<agent_id>/` and must export:
- `agent.py::build_graph(checkpointer=None, store=None)` returning a compiled graph
- `graph.py::graph` (a top-level variable, used by `langgraph dev` / Studio)
- `prompts.py::SYSTEM_PROMPT`
- Register in `langgraph.json` under `graphs`. The `loader.py` discovers the directory; the JSON only matters for Studio.
- Agents must NOT import `server/` or `worker/` modules. Use `shared/llm.create_chat_model()` (rate-limited factory) and `agents/middleware.get_context_middleware()` (selects trim/summarize/none from `CONTEXT_STRATEGY`).

**Frontend / admin auth** — Next.js panel in `frontend/` uses Better Auth against the same Postgres in a separate `auth` schema (migrations `003_auth_schema.sql`, `004_better_auth_tables.sql`). Server-side fetches to `/api/*` go via `INTERNAL_API_URL` + bearer `INTERNAL_SERVICE_TOKEN` (enforced by `verify_service_token` dependency on the admin router). On first `/login` the frontend bootstraps the initial admin from `ADMIN_EMAIL`/`ADMIN_PASSWORD` if `auth."user"` is empty. **`INTERNAL_SERVICE_TOKEN` and `BETTER_AUTH_SECRET` must be set even locally** — `Settings.validate_runtime_settings()` raises at API startup otherwise; in production the token is also length-checked (≥32).

**Migrations** — application schema lives in `db/migrations/*.sql` (controlled by `_migrations` table; lock id `8_642_000`). LangGraph schema (`checkpoints*`, `store*`) is created in-code by `bootstrap_langgraph_schema()` at startup. Don't write SQL migrations for LangGraph tables. **Currently 27 migrations** (skipping 021 — chronological gap, not a problem). Recent (E1 + Calendar v2):
- `022_rate_limit_generic.sql` — generic `rate_limit_bucket` (used by admin endpoints middleware)
- `023_hook_dead_letter.sql` — DLQ for hooks that exhaust retries
- `024_user_status.sql` — `auth.user.status` (active/disabled) blocks login + kills sessions
- `025_password_reset_pending.sql` — cache of reset links (no SMTP path, admin shares manually)
- `026_login_event.sql` — auth audit log with IP/user-agent
- `027_agendamento.sql` — local mirror of Google Calendar events with governance

**Twilio outbound modes** (`TWILIO_OUTBOUND_MODE`) — `mock` (logs only, default in dev) vs `real` (Twilio Messages API via API Key auth). Worker startup fail-fasts if `real` mode is missing any of `TWILIO_ACCOUNT_SID`, `TWILIO_API_KEY_SID`, `TWILIO_API_KEY_SECRET`, `TWILIO_FROM_NUMBER`. Empty value resolves to `real` in production, `mock` otherwise (`Settings.resolved_twilio_outbound_mode`).

**Outbound manual** (`shared/outbound.py::send_outbound_manual`) — used by composer in `/atendimento` drawer. Routes by `Conexao.provider` via `_build_client()`: `twilio_*`/`waba` → `TwilioClient`, `evolution` → `EvolutionClient`. Same `OutboundClient` Protocol the worker uses (`worker/outbound_client.py`). Don't reintroduce hardcoded Twilio.

**Hooks dispatcher** (`shared/hook_dispatcher.py`) — fire-and-forget with **retry exponencial (1s, 5s, 25s) + DLQ**. Each attempt is logged in `hook_log`; if all attempts fail, the event lands in `hook_dead_letter` (migration 023). Admin can list/retry/archive via `GET/POST /api/hooks/dead-letter[/{id}/retry|archive]`. `EVENTOS_VALIDOS` currently lists 7: `mensagem.recebida`, `atendimento.{aberto,atendido,fechado,transferido}`, `agendamento.criado`, `agendamento.cancelado`.

**Calendar Agent v2** (`shared/calendar_integration.py`, `shared/agendamento.py`) — local source-of-truth in `agendamento` table (migration 027). `create_event` does INSERT local → POST Google → UPDATE local with `evento_id_externo` + dispatch hook `agendamento.criado`. If Google fails, marks local as `cancelado` and logs `agendamento_drift_*` (compensating action). 7 tools exposed to the agent when `calendar_enabled`: `get_current_time`, `list_calendars`, `set_active_calendar`, `list_events`, `find_free_slots`, `create_event`, `cancel_event`. Plan in `/home/opc/.claude/plans/como-est-a-base-jazzy-sketch.md` documents 5 sprints (S1+S2 done, S3-S5 pending: rules, WhatsApp approval, sync+audit).

**Auth & user management**:
- `auth.user.status` (active|disabled) — admin toggles via UI in `/companies/[id]/members`. `frontend/src/lib/auth.ts::databaseHooks.session.create.before` blocks login if disabled; `set_user_status()` deletes `auth.session` rows on disable to expire active cookies in <30s.
- Reset password without SMTP — Better Auth callback `sendResetPassword` persists URL+token in `auth.password_reset_pending` (1h expiry). Admin retrieves via `generateResetLinkAction()` and shares via WhatsApp/Slack/whatever. UI button (KeyRound icon) in members list.
- Login audit — `databaseHooks.session.create.{before,after}` write to `auth_login_event` (migration 026). Best-effort (errors don't break login). Viewer at `/settings/security/login-history` (admin sees all, non-superadmin sees own).
- Google SSO — opt-in. If `GOOGLE_OAUTH_CLIENT_ID/SECRET` are set, `socialProviders.google` is enabled in Better Auth and login form shows the Google button. Reuses Calendar OAuth Client; just add redirect URI `https://<domain>/api/auth/callback/google` in Google Console.

**Bootstrap admin** (`frontend/src/lib/bootstrap-admin-core.ts`) — on first login, when `auth.user` is empty, creates the user from `ADMIN_EMAIL`/`ADMIN_PASSWORD` PLUS `empresa_membro` row (empresa_id=1, role=admin, is_default=true) PLUS `is_superadmin=true`/`emailVerified=true`. Without this triple-insert, the user logs in but every `/api/*` returns 403 because `get_empresa_context` requires membership or superadmin. Don't drop these inserts when refactoring.

## Branch / patch layout (didactic)

The repo is structured as a teaching harness across phases (`Fase_1` → `Fase_4`). The `patch/Fase_N/` directory holds drop-in replacements (`pyproject.toml`, `uv.lock`, Dockerfiles, `vsa_tech/graph.py`) meant to be copied over after `git checkout Fase_N`. Don't merge or "clean up" `patch/` — see `patch/README.md` for the intended workflow. The Docker patches matter because `make up` rebuilds against `uv.lock`, and a clean build without the patched lockfile can resolve incompatible transitive deps.

## Configuration

All config flows through `pydantic-settings` in `shared/config.py` as a singleton `settings` object — import that, don't read env vars directly. The full env surface is documented in `.env.example`. Notable defaults that matter at runtime: `CONTEXT_STRATEGY=trim`, `MEMORY_ENABLED=true`, `MAX_ATTEMPTS=3`, `LEASE_SECONDS=60`, `RATE_LIMIT_PER_HOUR=30`, `RATE_LIMIT_DISTRIBUTED=false`, `MESSAGE_BUFFER_SECONDS=2.0`, `FRONTEND_ORIGINS=http://localhost:3000`. All LLM, embeddings, and audio transcription go through one OpenRouter key (`OPENROUTER_API_KEY`). Rate limit: por default usa dict in-memory por processo (`RATE_LIMIT_DISTRIBUTED=false`); em implantações multi-instância ative `RATE_LIMIT_DISTRIBUTED=true` para sliding window em Postgres via tabela `rate_limit_buckets` (migration `005_rate_limit_buckets.sql`).

`Settings.validate_runtime_settings()` enforces four invariants no startup: (1) `INTERNAL_SERVICE_TOKEN` não pode ser vazio; (2) em produção, o token deve ter ≥32 caracteres; (3) em produção, `VALIDATE_TWILIO_SIGNATURE` deve ser `true` — sem isso o endpoint `/webhook/twilio` aceita payloads não autenticados; (4) em produção, `FRONTEND_ORIGINS` deve ter pelo menos uma origem configurada — sem isso o CORS nega todos os requests cross-origin e o painel quebra silenciosamente. O startup falha imediatamente em qualquer desses casos.

## Stress testing (Locust)

Locust profile in `stress/` (Dockerfile + locustfile.py). Supports both providers via `LOCUST_PROVIDER` env:
- `make stress-evolution` (default — `LOCUST_PROVIDER=evolution`) — sends `/webhook/evolution` JSON payloads
- `make stress-twilio` — sends `/webhook/twilio` form-urlencoded with valid HMAC-SHA1 signature (needs `TWILIO_AUTH_TOKEN`)
- `make stress-both` — both classes spawn together
- Defaults `-u 10 -r 2 -t 60s` against `https://api.vsanexus.com`. Sobrescrevíveis via `USERS=20 RATE=5 TIME=120s HOST=https://other.url`.
- Fallback Docker (`stress-evolution-docker`/`stress-twilio-docker`) for environments without `uv` — builds image from `stress/Dockerfile`.

When stress-testing for real worker throughput, temporarily set `EVOLUTION_OUTBOUND_MODE=mock` and `RATE_LIMIT_PER_HOUR=500` in env to avoid Evolution rejecting fake numbers (400) and rate limit blocking. Revert after.

## Reference docs

When in doubt, prefer these over inferring from code:
- `docs/ARCHITECTURE.md` — full data flow + endpoint inventory
- `docs/ADDING_AGENTS.md` — the agent contract above, with examples
- `docs/DATABASE.md` — schema overview + ready-to-run inspection queries (queue, conversation, memory, checkpoints)
- `docs/TWILIO.md` — sandbox vs production cutover, signature validation, tunneling
- `docs/EVOLUTION.md` — Evolution API provider (M2.b)
- `docs/AUTH.md` — Better Auth + user status + reset sem SMTP + login history + SSO Google + rate limits
- `docs/DOKPLOY.md` — passo a passo completo Dokploy (Project + Compose service + Domains + envs); inclui caveat do bug do `addPrefix` quando usa `path != "/"`
- `docs/DEPLOY.md` / `docs/RAILWAY.md` — alternative deploy targets
- `docs/STRESS_TESTING.md` — Locust setup (`stress/` profile in compose)
