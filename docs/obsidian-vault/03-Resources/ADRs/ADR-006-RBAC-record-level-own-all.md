---
title: ADR-006 — RBAC com sufixos `.own` e `.all` (record-level)
type: adr
status: aceito
priority: alta
created: 2026-05-15
updated: 2026-05-17
tags: [adr, rbac, permissoes, governanca]
empresa: VSA-Tech
responsavel: Vinicius-Andrade
categoria: decisao
area: Compliance-LGPD
projeto_pai: Governanca-RBAC-Backend
relacionados: [Governanca-RBAC-Backend, Governanca-RBAC-Frontend]
stakeholders: [Vinicius-Andrade]
deadline:
progresso:
---

# ADR-006 — RBAC com sufixos `.own` e `.all` (record-level)

## Status

Aceito (migration 083 em prod desde 2026-05-15).

## Contexto

Modelo RBAC inicial (mig 031) tinha permissões flat tipo `cliente.read`, `atendimento.update`. Problema: operador num hospital com 50 atendentes via TODOS os clientes/atendimentos da empresa — inclusive de outros departamentos (ex: ortopedia vendo dados de oncologia).

LGPD pra dados de saúde exige princípio de menor privilégio. Operador deve ver só **seus** clientes ou só **clientes do seu departamento**.

## Decisão

Sufixos `.own` e `.all`:
- `cliente.read.own` — só atende clientes vinculados aos departamentos do user (`usuario_departamento`)
- `cliente.read.all` — vê todos da empresa
- Idem pra `atendimento.read.own/.all`, `cliente.update.own/.all`, etc.

12 novas perms granulares em mig 083 (4 entidades × 3 verbos).

## Como aplica

Backend (`shared/permissoes.py`):
```python
def effective_scope(perms: set[str], base: str) -> Literal["all", "own", "none"]:
    if f"{base}.all" in perms: return "all"
    if f"{base}.own" in perms: return "own"
    if base in perms: return "all"  # legacy fallback
    return "none"
```

Cada endpoint chama `effective_scope` e adapta SQL WHERE:
```python
scope = effective_scope(perms, "cliente.read")
if scope == "none":
    raise HTTPException(403)
elif scope == "own":
    dept_ids = await get_user_departamento_ids(user_id, empresa_id)
    where_clause = "AND cliente.departamento_id = ANY(%s)"
elif scope == "all":
    pass  # sem filtro extra
```

Frontend (`hasPerm`) tem semântica idêntica — operador que só tem `.own` ainda **vê** a entrada de menu, mas dados filtrados.

## Consequências

### Positivas
- **Princípio de menor privilégio cumprido** — operador só vê o que precisa
- **Compliance LGPD pra saúde** — dados sensíveis isolados por departamento
- **Custom roles flexíveis** — admin pode dar `.own` ou `.all` granular por user
- **Compatibilidade preservada** — `cliente.read` sem sufixo ainda funciona (legacy fallback)

### Negativas
- **2x mais perms no catálogo** — UI de edição mais densa
- **SQL mais complexo** — todo endpoint READ vira UPDATE/DELETE precisa branch por scope
- **Performance** — JOIN extra com `usuario_departamento` em queries `.own`. Mitigado com index

## Trade-off explícito

Operador `.own` que **não tem departamento atribuído** → vê **zero registros**. Decisão consciente: melhor zero que vazamento. Admin precisa atribuir depto antes.

## Relacionados

- [[01-Projects/Governanca-RBAC-Backend]]
- [[01-Projects/Governanca-RBAC-Frontend]]
- [[02-Areas/Compliance-LGPD]]
- `db/migrations/083_rbac_record_level.sql`
