# Spec — Configuração da integração Asaas pela UI (global, superadmin)

**Data:** 2026-06-06 · **Status:** aprovado (brainstorming)

## Contexto / problema

A integração Asaas (billing da plataforma) hoje é configurada **só por env vars**
(`ASAAS_API_KEY`, `ASAAS_WEBHOOK_TOKEN`, `ASAAS_ENVIRONMENT`, `ASAAS_SUCCESS_URL`,
`ASAAS_CANCEL_URL`) — não há tela. Trocar a credencial exige editar env + redeploy.
A auditoria de prontidão também notou que as envs Asaas nem estão no `.env.example`.

Asaas é **uma conta global da plataforma** (Chat Nexus fatura as empresas-clientes
por uma única conta) — NÃO é por-empresa (decisão de 2026-05-22; o provider foi
removido do catálogo per-empresa por isso). Logo a config é **global**, editável só
pelo **superadmin**, mas exibida dentro de `/settings/integracoes` (a pedido).

## Objetivo

Superadmin configura/edita a credencial Asaas por um card na UI; o billing passa a
ler a config do **DB primeiro, env como fallback** (zero quebra na prod atual).

## Arquitetura

### Persistência
Nova tabela **global** (sem `empresa_id`):
```
platform_integration_config(
  slug TEXT PRIMARY KEY,        -- 'asaas'
  config_encrypted TEXT NOT NULL,  -- Fernet(JSON) via integrations/crypto
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_by TEXT
)
```
Migration `117`. Sem RLS (config de plataforma; acesso via bypass + gate superadmin
na rota). Blob Asaas: `{api_key, webhook_token, environment, success_url, cancel_url}`.
Reusa `integrations/crypto.encrypt_dict/decrypt_dict` (chave `wareline_encryption_key`).

### Resolver (precedência DB > env)
- `shared/platform_config.py`: `get_platform_config(pool, slug) -> dict | None`,
  `set_platform_config(pool, slug, data, updated_by)`.
- `shared/asaas.py::get_asaas_effective(pool) -> dict` → `{enabled, api_key,
  environment, base_url, webhook_token, success_url, cancel_url, source}` (DB se
  salvo, senão `settings.asaas_*`).
- `AsaasClient`: `__init__(*, api_key=None, base_url=None, ...)` — usa os args se
  dados, senão cai em `settings` (compat). `AsaasClient.from_pool(pool)` (async)
  carrega a config efetiva e constrói o client.

### Consumidores ajustados
- `create_subscription_for_plano` / `cancel_active_subscription` → `await
  AsaasClient.from_pool(pool)`.
- `billing.py::_ensure_asaas_enabled` → checa config efetiva (tem `get_pool`).
- `asaas_webhook.py` → valida o `asaas-access-token` contra o token efetivo
  (DB > env). (Mantém o `hmac.compare_digest` + o 503-on-error do R9.)

### Backend — endpoints (superadmin only)
- `GET /api/admin/integracoes/asaas` → `{configurado, environment, source: db|env,
  tem_api_key, tem_webhook_token, success_url, cancel_url}` — **sem** secrets.
- `PUT /api/admin/integracoes/asaas` → salva (cifra). Campos sensíveis (api_key,
  webhook_token) em branco **mantêm** o valor anterior (padrão `wareline-card`).
- `POST /api/admin/integracoes/asaas/testar` → valida a key (`GET /myAccount`).
- Gate: `is_superadmin` (config global). Novo router `routes/integracoes_asaas.py`.

### Frontend
Card "Asaas — Cobrança (plataforma)" em `/settings/integracoes`, **só renderiza
para superadmin** (rótulo "Global da plataforma"). Form: api_key, webhook_token,
ambiente (select sandbox/production), success/cancel URL + botão Testar + badge de
status (configurado / source env|db). Segue o padrão de `wareline-card.tsx`
(sensível em branco = mantém). Server actions em `billing/` ou `settings/integracoes/`.

## Não-objetivos (fora deste escopo)
- Per-empresa Asaas (billing é da plataforma).
- Dunning/downgrade automático e quota-everywhere (follow-ups do R9).

## Testes
- Smoke (TestClient): os 3 endpoints exigem superadmin → 401/403 sem.
- Unit: `get_asaas_effective` (DB > env; fallback quando DB vazio); `AsaasClient`
  com api_key/base_url explícitos.
- E2E pós-feature (CLAUDE.md): TestE2E httpx+psycopg PUT→GET→testar com superadmin;
  TestE2EIsolamento: não-superadmin → 403.

## Verificação
`make check` (ruff+pyright) verde; suíte unit por-arquivo verde; migration 117 aplica;
prod atual (env) segue funcionando sem salvar nada pela UI (fallback).
