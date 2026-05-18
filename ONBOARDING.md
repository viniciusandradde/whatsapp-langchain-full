# Onboarding — Nexus Chat AI (`whatsapp-langchain`)

> Doc pra próximas sessões Claude / colaboradores começarem rápido. Não substitui `CLAUDE.md` (instruções vinculantes), `docs/ARCHITECTURE.md` (deep-dive) nem o vault `docs/obsidian-vault/` (contexto de longo prazo).

## TL;DR

Plataforma WhatsApp multi-tenant com agentes LangChain/LangGraph. Em produção em **`chat.vsanexus.com`** (frontend) + **`api.vsanexus.com`** (API). Single dev (Vinicius Andrade, [[People/Vinicius-Andrade]]). Host Oracle Cloud ARM + Dokploy. Cliente principal: Hospital Mackenzie ([[Empresas/Mackenzie-Hospital]]).

## Onde olhar primeiro

| Pergunta | Onde |
|---|---|
| Como o sistema funciona? | `CLAUDE.md` (instruções) + `docs/ARCHITECTURE.md` |
| Por que essa decisão? | `docs/obsidian-vault/03-Resources/ADRs/` (8 ADRs) |
| Estado de projetos ativos | `docs/obsidian-vault/01-Projects/` |
| Áreas operacionais | `docs/obsidian-vault/02-Areas/` |
| Histórico de sprints | Memória `~/.claude/projects/.../memory/history_timeline.md` |
| Quem é o user/cliente | `docs/obsidian-vault/People/` + `Empresas/` |
| Comandos de operação prod | `docs/obsidian-vault/03-Resources/Reference-Dokploy.md` |
| Schema/estado banco | `docs/DATABASE.md` + `db/migrations/*` |

## Stack rápida

- **Backend** (`src/whatsapp_langchain/`): Python 3.12 + FastAPI + LangGraph + asyncpg + AsyncPostgresSaver
- **Frontend** (`frontend/`): Next.js 16 + React 19 + TypeScript + Tailwind + Better Auth
- **DB**: Postgres (queue via `FOR UPDATE SKIP LOCKED`, sem Redis — ver [[ADR-001]])
- **LLM**: OpenRouter unificado (LLM + embeddings + audio — ver [[ADR-004]])
- **Infra**: Dokploy on Oracle Cloud ARM ([[ADR-008]])

## Dois processos críticos

1. **API** (`server/main.py`): HTTP edge. Webhook → valida → enfileira → responde <100ms
2. **Worker** (`worker/main.py`): polla `message_queue` → preprocess → agente LangGraph → outbound → `mark_done`

Eles compartilham só Postgres. Worker NÃO importa de `server/`. Agentes NÃO importam de `server/` nem `worker/`. Detalhes em [[ADR-002]].

## Setup local

```bash
make setup        # uv venv + uv pip install -e ".[dev]"
make up           # docker compose: db + api + 4 workers + frontend
make migrate      # aplica db/migrations/ pendentes (auto no boot da API)
```

Frontend dev separado: `cd frontend && npm run dev` (precisa `frontend/.env.local`).

## Qualidade

```bash
make check        # ruff + pyright (style + types, NÃO logic)
make test         # pytest sem docker_demo
make ci           # check + test (o que CI roda)
```

## Deploy

**Auto-deploy ON** — push em `master` → webhook GitHub → Dokploy rebuilda. Build ARM demora 3-5min. Ver gotchas em [[Reference-Dokploy]] e [[Lessons-Auto-Deploy-Dokploy]].

## Decisões pendentes (ler antes de tocar nessas áreas)

- [[Convergencia-Menu-vs-Workflow]] — menu chatbot legacy + workflow LangGraph convivem
- [[Convergencia-RBAC-Role-vs-Perfis]] — `empresa_membro.role` (TEXT) + perfis RBAC (mig 031+083)
- [[Integracao-ZigChat]] — só docs hoje, runtime nunca conectado

## Preferências do owner (observadas, NÃO ignorar)

- **Foco 1 módulo por vez** — terminar 100% (BE+FE+tests+deploy+validar) antes de passar pra próximo. Memória [[feedback_foco_um_modulo]]
- **Server-side security padrão** — passwords/tokens gerados no backend, nunca digitados no client. Ver [[ADR-007]]
- **Sem mensagens técnicas vazando** — drawer atendimento mostra "⚠ Falha ao processar... entre em contato com suporte", não stack trace. Commit `8ac3320`
- **Doc em pt-BR** — todos os arquivos e comentários em português
- **Rebuild após código** — restart container não pega edits. Sempre `make up --build`. Memória [[feedback_rebuild_after_code_changes]]
- **`uv lock` antes de commitar dep nova** — senão Docker build quebra. Memória [[feedback_uv_lock_after_pyproject]]

## Estado em 2026-05-18

- master em `e22d0aa`
- 84 migrations aplicadas (última `084_audit_governanca`)
- RBAC sprint 1+2 SHIPPED
- Vault Obsidian criado em `docs/obsidian-vault/`
- Workflows LangGraph Mackenzie rodando em prod (9 workflows, 123 nodes)
- Calendar v2 S1+S2 entregue (S3-S5 pendente: rules, WhatsApp approval, sync+audit)

## Arquivos untracked sensíveis no working tree

Não commitados nesta sessão por risco PII / não revisão:
- `docs/agente/*.png` — screenshots painel admin
- `docs/zigchat/` — JWT real expirou mas inspecionar antes
- `docs/dump_3m_*.json` — dump de mensagens reais cliente (LGPD)
- `docs/ai-agent-sales/`, `docs/eval-101/`, `docs/guardrails/`, `webscap/` — não revisados
- `.github/workflows/e2e.yml` — token OAuth sem `workflow` scope; precisa push manual

## Como continuar (próxima sessão)

1. `git pull` na branch master
2. Ler `~/.claude/projects/.../memory/checkpoint_session_2026-05-18.md`
3. Se for trabalhar em área específica, abrir o `01-Projects/<X>.md` correspondente do vault
4. Confirmar se decisão pendente que afeta a área já foi tomada
