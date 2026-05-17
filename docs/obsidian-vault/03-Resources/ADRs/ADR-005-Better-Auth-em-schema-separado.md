---
title: ADR-005 — Better Auth em schema Postgres separado (`auth`)
type: adr
status: aceito
priority: media
created: 2026-04-29
updated: 2026-05-17
tags: [adr, auth, better-auth, security]
empresa: VSA-Tech
responsavel: Vinicius-Andrade
categoria: decisao
area: Compliance-LGPD
projeto_pai:
relacionados: [Governanca-RBAC-Backend]
stakeholders: [Vinicius-Andrade]
deadline:
progresso:
---

# ADR-005 — Better Auth em schema Postgres separado (`auth`)

## Status

Aceito.

## Contexto

Painel admin Nexus (Next.js) precisa de auth (login, sessão, password reset, SSO). Opções:
- Auth0/Clerk (SaaS)
- NextAuth (open source, popular)
- Better Auth (open source, mais novo)
- Build próprio

## Decisão

**Better Auth** com tabelas em schema **`auth`** separado do schema `public` da aplicação. Migrations `003_auth_schema.sql` + `004_better_auth_tables.sql`.

## Por que separar schema

1. **Isolamento de PII** — `auth.user` tem email + password hash. Aplicação principal não toca direto, só via `empresa_membro.user_id` (FK pra `auth.user.id`)
2. **Migrations independentes** — Better Auth tem próprio versioning de schema. Manter num namespace evita conflito com migrations app
3. **GRANT controlável** — futuramente pode dar permissão diferente pro role do app vs role do Better Auth

## Por que Better Auth (vs NextAuth)

- **Database-first** — sessão persistida em `auth.session` (NextAuth defaulta JWT, harder pra invalidar)
- **`databaseHooks`** — interceptar before/after de session.create. Usado pra:
  - Bloquear login se `auth.user.status = 'disabled'` (mig 024)
  - Audit log em `auth_login_event` (mig 026)
- **`sendResetPassword` callback custom** — persiste link em `auth.password_reset_pending` (mig 025) em vez de SMTP. Admin compartilha pelo canal escolhido
- **Rate limit nativo** — config em `frontend/src/lib/auth.ts::rateLimit`
- **SSO opt-in** — Google reusa OAuth Client do Calendar; só ativa se `GOOGLE_OAUTH_CLIENT_ID/SECRET` setados

## Consequências

### Positivas
- Painel autenticado sem dependência externa (Auth0/Clerk = $$)
- Sessão expira em <30s ao desativar user (DELETE em `auth.session`)
- Reset password sem SMTP — bom pra Nexus (não temos infra de email)

### Negativas
- Better Auth é jovem — breaking changes possíveis (já aconteceu em upgrade de tabela)
- Bootstrap admin é manual (mig + `bootstrap-admin-core.ts` cria primeiro user de env)
- 2 schemas pra navegar quando se queryia user info

## Bootstrap admin (load-bearing)

Em primeiro login, se `auth.user` vazio:
1. INSERT em `auth.user` (do `ADMIN_EMAIL`/`ADMIN_PASSWORD`)
2. INSERT em `empresa_membro` (empresa_id=1, role=admin, is_default=true)
3. UPDATE `is_superadmin=true`, `emailVerified=true`

**Sem essa triple-insert, user loga mas `/api/*` retorna 403** porque `get_empresa_context` requer membership ou superadmin.

## Relacionados

- [[01-Projects/Governanca-RBAC-Backend]]
- [[02-Areas/Compliance-LGPD]]
- `frontend/src/lib/auth.ts` — configuração Better Auth
- `frontend/src/lib/bootstrap-admin-core.ts` — primeiro admin
