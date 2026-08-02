---
title: ADR-016 — `SKIP_MIGRATIONS` — processo local nunca aplica migration em banco compartilhado
type: adr
status: aceito
priority: alta
created: 2026-07-31
updated: 2026-07-31
tags: [adr, infra, migrations, seguranca, incidente]
empresa: VSA-Tech
responsavel: Vinicius-Andrade
categoria: decisao
area: Infra-Producao
projeto_pai:
relacionados: [ADR-001-Postgres-como-fila]
stakeholders: [Vinicius-Andrade]
deadline:
progresso:
---

# ADR-016 — `SKIP_MIGRATIONS`: processo local nunca aplica migration em banco compartilhado

## Status

Aceito. Implementado em `shared/config.py:70` e `shared/db.py:321`.

## Contexto

Nasceu do **incidente I1**, em 2026-07-31.

Para testar a busca de contatos com dados reais (19.647 registros), subiu-se um
`uvicorn` local com `DATABASE_URL` apontando para o banco de **produção**. A API
roda o migrator no startup — então cada restart aplicou as migrations pendentes
**do checkout local** naquele banco:

| migration | aplicada em | efeito |
|---|---|---|
| `151_drop_wareline.sql` | 01:22 UTC | `DROP TABLE wareline_credentials, wareline_sync_log` + `DELETE` da permissão `integracao.wareline.manage` |
| `152_perfis_descricao_pt.sql` | 03:25 UTC | `UPDATE` na descrição dos 4 perfis de sistema |

Passou despercebido porque **o migrator é silencioso quando dá certo**. E as
tabelas tinham sido verificadas como vazias *antes* de escrever a migration —
daí a associação errada entre "vazias" e "sem consequência".

A consequência não era o dado. Era que **o código rodando em produção ainda usava
o schema antigo**: `GET /api/integracoes/wareline` passou de "não configurado"
para **403**, porque a migration apagou a permissão que o código em produção
ainda exigia.

O efeito medido foi pequeno (11 mensagens na fila desde o horário, todas `done`,
zero falha), mas o modo de falha é grave: **um processo de desenvolvimento
alterou o schema de produção sem que ninguém pedisse**.

## Decisão

Campo `skip_migrations` em `Settings`, lido por `run_migrations`. Quando `true`,
o migrator loga `migrations_skipped` e **retorna sem tocar no schema**.

Regra de uso: **qualquer processo local apontado para banco compartilhado sobe
com ele ligado.** O deploy deixa em `false`.

## Consequências

### Positivas
- O modo de falha deixa de depender de disciplina. É uma variável, não uma
  lembrança.
- O log diz explicitamente que pulou — silêncio deixa de ser ambíguo.

### Negativas
- É **opt-in**: quem esquecer de ligar reproduz o incidente. A proteção real veio
  junto, e é outra — o ambiente de desenvolvimento saiu do VPS de produção, e o
  banco local é um dump saneado.
- Um processo local com `SKIP_MIGRATIONS=true` contra um banco **próprio** e
  desatualizado falha de outro jeito: código novo contra schema velho. O sinal é
  diferente e mais fácil de ler que o do I1.

## Alternativas consideradas

| opção | por que não |
|---|---|
| Não rodar migration no startup | Migration no startup é o que garante que o container novo sobe com o schema certo; tirar isso troca um problema por outro |
| Bloquear por host do `DATABASE_URL` | Frágil — produção e dev podem estar atrás do mesmo hostname ou de um túnel |
| Só documentar | Foi o que existia. Não impediu |

## Relacionados

- Incidente I1 — `docs/benchmark/nosso-painel/defeitos.md`
- [[ADR-001-Postgres-como-fila]] — o migrator e a tabela `_migrations`
- `docs/MIGRACAO_DEV.md` — o contrato de isolamento do ambiente local
