---
title: Governança RBAC — Frontend Visual (Sprint 2)
type: projeto
status: shipped
priority: alta
created: 2026-05-16
updated: 2026-05-16
tags: [rbac, governanca, frontend, ux]
empresa: VSA-Tech
responsavel: Vinicius-Andrade
categoria: ux
area: Compliance-LGPD
projeto_pai: Governanca-RBAC-Backend
relacionados: [Governanca-RBAC-Backend]
stakeholders: [Vinicius-Andrade]
deadline:
progresso: 100
---

# Governança RBAC — Frontend Visual (Sprint 2)

## Outcome

Operador logado **não vê** menus/recursos que não tem permissão. Erros 403 viram mensagens amigáveis. UI esconde botões destrutivos por perm.

## Status

✅ **SHIPPED** (commit 622f3da) em 2026-05-16.

## Entregas

- `PermissionsProvider` carrega perms server-side (sem flash)
- Hook `usePermission(perm)` + `useAllPermissions(perms)` (AND)
- Sidebar filtra 6 grupos por `requires`
- Top-nav-tabs filtra ~30 tabs por `requires`
- `members-list.tsx`: 5 botões condicionais (Shield, KeyRound, Trash2, XCircle, "Adicionar membro")
- `apiFetch` intercepta 403 → "Você não tem permissão para essa ação."
- `apiFetch` intercepta 401 → "Sessão expirada. Faça login novamente."

## Verificação por persona

**Operador** (`atendente.atendimento@vsanexus.test`):
- Sidebar: Visão Geral + Operação
- Top-nav (em /atendimento): Atendimentos, Conversas, Clientes, Agendamentos, Campanhas
- Companies/members: select role vira badge, botões admin escondidos

**Admin**: vê tudo como antes.

## Não-objetivos (sprint futuro)

- ❌ `<PermissionGuard>` em todas as páginas (defesa em profundidade)
- ❌ Cache localStorage de perms (atual: refetch por session, mais seguro)
- ❌ Botões condicionais nas outras telas (perfis, deptos, workflows)

## Decisão chave

- [[03-Resources/ADRs/ADR-007-Filtro-Menus-Client-Side-Static-Map]] — mapa estático com `requires` por item, não navegação dinâmica do backend

## Arquivos críticos

- `frontend/src/components/permissions-context.tsx`
- `frontend/src/hooks/use-permission.ts`
- `frontend/src/lib/permissions-actions.ts`
- `frontend/src/components/sidebar.tsx`
- `frontend/src/components/top-nav-tabs.tsx`
- `frontend/src/lib/api.ts` (apiFetch interceptor)
- `frontend/src/app/companies/[id]/members/members-list.tsx`
