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

**API (`src/whatsapp_langchain/server/`)** — FastAPI HTTP edge. Validates Twilio webhook (HMAC via official Twilio SDK when `VALIDATE_TWILIO_SIGNATURE=true`), applies per-phone in-memory rate limit, normalizes payload, and enqueues into `message_queue`. Returns empty TwiML in <100ms. Never invokes the agent inline. `/webhook/sync` exists for development only and is auto-disabled when `ENVIRONMENT=production`.

**Worker (`src/whatsapp_langchain/worker/`)** — Async loop polling `message_queue`. Claims a row with `FOR UPDATE SKIP LOCKED` + lease, preprocesses media (image/audio → text via OpenRouter multimodal), sends Twilio typing indicator (best-effort), invokes the LangGraph agent, sends the outbound reply via Twilio, *then* calls `mark_done`. **`mark_done` only runs after the outbound send succeeds** — a Twilio failure flows into `mark_failed`'s retry path. This ordering is load-bearing for at-least-once delivery.

**Postgres is the queue** — no Redis/RabbitMQ. State machine: `queued → processing → done | failed`, with retry going `processing → queued` (with `process_after = NOW() + attempts*5s` backoff) until `attempts >= max_attempts`. Lease expiry on a stuck `processing` row promotes to `failed` only when attempts are exhausted; otherwise the row is reclaimable.

**Debounce semantics** (in `shared/queue.py::enqueue_or_buffer`) — text-only messages from the same `(phone, agent)` within `MESSAGE_BUFFER_SECONDS` are concatenated into a single queued row. Media bypasses debounce *and* flushes any pending text from the same `(phone, agent)` so the worker processes text-then-media in `created_at` order. Concurrent webhooks are serialized via `pg_advisory_xact_lock` keyed on a SHA-256 hash of `phone:agent`. **Known limitation: `NumMedia > 1` in a single webhook is out of scope.**

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

**Migrations** — application schema lives in `db/migrations/*.sql` (controlled by `_migrations` table; lock id `8_642_000`). LangGraph schema (`checkpoints*`, `store*`) is created in-code by `bootstrap_langgraph_schema()` at startup. Don't write SQL migrations for LangGraph tables.

**Twilio outbound modes** (`TWILIO_OUTBOUND_MODE`) — `mock` (logs only, default in dev) vs `real` (Twilio Messages API via API Key auth). Worker startup fail-fasts if `real` mode is missing any of `TWILIO_ACCOUNT_SID`, `TWILIO_API_KEY_SID`, `TWILIO_API_KEY_SECRET`, `TWILIO_FROM_NUMBER`. Empty value resolves to `real` in production, `mock` otherwise (`Settings.resolved_twilio_outbound_mode`).

## Branch / patch layout (didactic)

The repo is structured as a teaching harness across phases (`Fase_1` → `Fase_4`). The `patch/Fase_N/` directory holds drop-in replacements (`pyproject.toml`, `uv.lock`, Dockerfiles, `rhawk_assistant/graph.py`) meant to be copied over after `git checkout Fase_N`. Don't merge or "clean up" `patch/` — see `patch/README.md` for the intended workflow. The Docker patches matter because `make up` rebuilds against `uv.lock`, and a clean build without the patched lockfile can resolve incompatible transitive deps.

## Configuration

All config flows through `pydantic-settings` in `shared/config.py` as a singleton `settings` object — import that, don't read env vars directly. The full env surface is documented in `.env.example`. Notable defaults that matter at runtime: `CONTEXT_STRATEGY=trim`, `MEMORY_ENABLED=true`, `MAX_ATTEMPTS=3`, `LEASE_SECONDS=60`, `RATE_LIMIT_PER_HOUR=30`, `MESSAGE_BUFFER_SECONDS=2.0`, `FRONTEND_ORIGINS=http://localhost:3000`. All LLM, embeddings, and audio transcription go through one OpenRouter key (`OPENROUTER_API_KEY`).

`Settings.validate_runtime_settings()` enforces three invariants no startup: (1) `INTERNAL_SERVICE_TOKEN` não pode ser vazio; (2) em produção, o token deve ter ≥32 caracteres; (3) em produção, `VALIDATE_TWILIO_SIGNATURE` deve ser `true` — sem isso o endpoint `/webhook/twilio` aceita payloads não autenticados e o startup falha imediatamente.

## Reference docs

When in doubt, prefer these over inferring from code:
- `docs/ARCHITECTURE.md` — full data flow + endpoint inventory
- `docs/ADDING_AGENTS.md` — the agent contract above, with examples
- `docs/DATABASE.md` — schema overview + ready-to-run inspection queries (queue, conversation, memory, checkpoints)
- `docs/TWILIO.md` — sandbox vs production cutover, signature validation, tunneling
- `docs/DEPLOY.md` / `docs/RAILWAY.md` — deploy targets
- `docs/STRESS_TESTING.md` — Locust setup (`stress/` profile in compose)
