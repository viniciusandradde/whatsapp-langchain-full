---
title: Decisão — Convergir Role Legacy vs Perfis RBAC
type: projeto
status: em-aberto
priority: media
created: 2026-05-17
updated: 2026-05-17
tags: [decisao, rbac, governanca, legacy]
empresa: VSA-Tech
responsavel: Vinicius-Andrade
categoria: estrategia
area: Compliance-LGPD
projeto_pai:
relacionados: [Governanca-RBAC-Backend, Governanca-RBAC-Frontend]
stakeholders: [Vinicius-Andrade]
deadline:
progresso: 0
---

# Decisão — Convergir Role Legacy vs Perfis RBAC

## Contexto

`empresa_membro.role` (TEXT — `admin`/`operator`/`viewer`) é o sistema **antigo** de autorização. Foi parcialmente substituído pelos perfis RBAC (mig 031 + mig 083) mas continua existindo.

Hoje:
- **Role legacy**: usado em alguns endpoints (`is_admin_of` checa role='admin')
- **Perfis RBAC**: 4 sistema (Admin/Gestor/Operador/Leitura) + custom. Permissões granulares com `.own/.all`
- UI `/companies/[id]/members`: mostra ambos — select de role + chips/modal de perfis

## Problema

- Admin precisa entender qual mexer (role ou perfis?)
- 2 sources of truth pra "esse user é admin?"
- Refator difícil sem quebrar fluxos que dependem de `is_admin_of`

## Opções

### A. Manter role como "shortcut" pro perfil Admin
- Se `role='admin'` → user automaticamente tem perfil Admin
- Mudar role muda perfil correspondente (sync via trigger ou na action)
- **Esforço**: baixo — só trigger ou ajuste em changeMemberRoleAction

### B. Deprecar role completamente
- UI esconde select de role
- Backend: trocar todos `is_admin_of` por `hasPerm("empresa.update")` ou similar
- Migration: gerar perfil custom equivalente pra cada role atual e atribuir
- **Esforço**: alto — toca em 8+ arquivos backend, audit cuidadoso

### C. Status quo + documentar
- Manter os 2, escrever doc "role = atalho legacy, prefira perfis"
- Não muda código
- **Esforço**: zero

## Recomendação

**Opção A** — sync role↔perfil. Mantém compatibilidade com código existente que checa `is_admin_of`, mas alinha semântica. Tempo: 1-2h.

## Próximos passos

- [ ] Decidir A/B/C
- [ ] Se A: implementar trigger ou ajuste em `changeMemberRoleAction`

## Relacionados

- [[01-Projects/Governanca-RBAC-Backend]]
- [[01-Projects/Governanca-RBAC-Frontend]]
