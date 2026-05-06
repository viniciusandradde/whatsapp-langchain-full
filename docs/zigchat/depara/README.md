# Depara ZigChat → Nexus (whatsapp-langchain)

> Mapeamento detalhado de cada entidade ZigChat para o equivalente Nexus, com gaps explicitados e SQL pronto pra alcançar paridade.

**Snapshot:** ZigChat schema GraphQL em 2026-05-06 (ver `../_schema_full.json`) × Nexus pós-mig 040 (54 tabelas, 39 migrations).

## Arquivos

1. **[01_master_table.md](./01_master_table.md)** — tabela master de todas as entidades ZigChat → equivalente Nexus, status global (✅ existe / 🟡 parcial / ❌ pendente).
2. **[02_paridade_alta.md](./02_paridade_alta.md)** — entidades já bem alinhadas, faltam só extras pontuais.
3. **[03_gap_grande.md](./03_gap_grande.md)** — entidades que existem nos dois lados mas precisam ALTER significativo.
4. **[04_pendentes_criar.md](./04_pendentes_criar.md)** — entidades ZigChat que não temos. SQL CREATE TABLE pronto.
5. **[05_so_nexus.md](./05_so_nexus.md)** — coisas só nossas que ZigChat não tem (LangGraph infra, agendamento Calendar v2, audit log, RBAC granular).
6. **[06_migrations_consolidado.md](./06_migrations_consolidado.md)** — sequência completa mig 041-060 com SQL pronto, dependências e ordem otimizada.

## Como ler

Para cada entidade ZigChat existem três tipos de notas:

- ✅ **Equivalente direto** — campo Nexus mapeia 1:1 ao ZigChat (talvez com tipo idiomatic diferente).
- 🟡 **Equivalente parcial** — campo existe mas semântica/escopo diferente, pode precisar adaptação.
- ❌ **Sem equivalente** — gap a fechar com mig nova ou ALTER TABLE.

Linhas com `_(bookkeeping comum)_` (id/empresa_id/ativo/created_at) são triviais e não precisam matching field-by-field.

## Premissas Nexus

- Boolean nativo (não `"S"`/`"N"`)
- IDs `BIGSERIAL`/`bigint` (não `Float`)
- Audit centralizado em `audit_log` (mig 036) em vez de `criacao_usuario_id`/`alteracao_usuario_id` em cada tabela
- JSONB tipado pra estruturas variáveis (vs colunas separadas como ZigChat usa)
- Array Postgres pra listas simples (`tags TEXT[]`, `trigger_keywords TEXT[]`)
- Better Auth gerencia `auth.user` em schema separado
- LangGraph checkpointer + store em tabelas próprias (não relacionais)
- Calendar Agent v2 é diferencial Nexus (não tem na ZigChat)
