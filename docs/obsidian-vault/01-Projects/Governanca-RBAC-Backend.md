---
title: Governança RBAC — Backend (Sprint 1)
type: projeto
status: shipped
priority: alta
created: 2026-05-15
updated: 2026-05-15
tags: [rbac, governanca, backend, lgpd]
empresa: VSA-Tech
responsavel: Vinicius-Andrade
categoria: infraestrutura
area: Compliance-LGPD
projeto_pai:
relacionados: [Governanca-RBAC-Frontend, Convergencia-RBAC-Role-vs-Perfis]
stakeholders: [Vinicius-Andrade]
deadline:
progresso: 100
---

# Governança RBAC — Backend (Sprint 1)

## Outcome

Catálogo de permissões expandido com **record-level access control** (`.own`/`.all`), audit trail de mudanças de perfil/depto/role/status, e endpoints PUT/GET pra atribuição perfil↔user via UI.

## Status

✅ **SHIPPED** (commits 529d3b2 + 4 hotfixes — 710f89d, 41470fa, fba4563, 0b54a2a).

## Entregas

### Backend
- 12 permissões novas: `cliente.read.own/all`, `cliente.write.own/all`, `atendimento.read/write/transfer/close.own/all`
- Helper `effective_scope(perms, base) → 'all'|'own'|None` (precedência: .all > .own > legacy)
- Helper `get_user_departamento_ids(user_id, empresa_id)`
- Tabela `audit_governanca` (13 cols + 3 índices)
- Helper `record_audit_governanca(...)` best-effort
- 5 endpoints novos: GET/PUT perfis por member, GET/PUT deptos por member, GET audit
- Filtros `.own` aplicados em routes `cliente.py` + `atendimento.py`
- Reseed perfis system: Admin/Gestor → .all, Operador → .own, Leitura → .all

### Tests
- `tests/unit/test_permissoes_scope.py` (10 testes)
- `tests/integration/test_governanca_endpoints.py` (5 testes smoke 401)

## Decisões

- [[03-Resources/ADRs/ADR-004-Permissions-Strings-vs-IDs-Numericos]] — strings semânticas, não IDs
- [[03-Resources/ADRs/ADR-005-Record-Level-Own-Vs-All]] — sufixos `.own`/`.all`
- [[03-Resources/ADRs/ADR-006-Audit-Governanca-Vs-Audit-Log]] — tabela separada

## Hotfixes pós-deploy (lessons learned)

1. **Mig 083 `column "id" does not exist`** — tabela `permissao` usa `codigo` TEXT como PK. Refator DO $$ → INSERT...SELECT...CROSS JOIN
2. **`usuario_perfil` NotNullViolation `empresa_id`** — PK composta (user_id, perfil_id, empresa_id). INSERT precisa passar todos
3. **Build Turbopack `pg → fs/net/tls`** — Client Component importava `lib/api.ts` (server-only). Fix: Server Actions wrappers

## Próximos sprints

- Sprint 2 (UI visual): [[01-Projects/Governanca-RBAC-Frontend]] ✅ SHIPPED
- Sprint 3 (futuro): convite por email/link sem SMTP, bulk assign, perms `.own` pra mais módulos

## Arquivos críticos

- `db/migrations/083_rbac_record_level.sql`
- `db/migrations/084_audit_governanca.sql`
- `src/whatsapp_langchain/shared/permissoes.py`
- `src/whatsapp_langchain/shared/audit_governanca.py`
- `src/whatsapp_langchain/server/routes/empresa_admin.py`
