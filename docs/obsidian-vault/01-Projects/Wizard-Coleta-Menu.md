---
title: Wizard de Coleta Multi-pergunta no Menu Chatbot
type: projeto
status: shipped
priority: media
created: 2026-05-12
updated: 2026-05-12
tags: [menu-chatbot, coleta, triagem, ux]
empresa: VSA-Tech
responsavel: Vinicius-Andrade
categoria: produto
area: Atendimento-Operacao
projeto_pai:
relacionados: [Workflow-Mackenzie, Convergencia-Menu-vs-Workflow]
stakeholders: [Vinicius-Andrade]
deadline:
progresso: 100
---

# Wizard de Coleta Multi-pergunta no Menu Chatbot

## Outcome

Cada `menu_item` do menu chatbot legacy pode ter sequência de N perguntas (CPF, data, telefone, texto livre) com validators BR. Antes da `acao_tipo` original ser executada, wizard coleta dados → grava em `atendimento.coleta_resumo` (JSONB) → bloco no drawer pro atendente humano ver.

## Status

✅ **SHIPPED** (commit 4e080ea) em 2026-05-12.

## Stack

- 3 migrations: 080 (`menu_item.coleta_perguntas` JSONB), 081 (`atendimento.coleta_estado` runtime), 082 (`atendimento.coleta_resumo` snapshot)
- `src/whatsapp_langchain/shared/coleta.py` (Pydantic + state machine)
- Worker `_try_handle_coleta_em_curso` ANTES de `_try_handle_workflow`
- Frontend `coleta-editor.tsx` (Client Component) + integração em `ItemForm`
- Drawer atendimento: `ColetaPreviaCard` mostra respostas no topo

## Diferenças vs Workflow LangGraph

| | Wizard Coleta (menu) | Workflow LangGraph |
|---|---|---|
| Engine | State simples em JSONB | LangGraph StateGraph |
| Use case | Triagem antes de despachar ação do menu | Fluxo conversacional completo |
| Persistência | `atendimento.coleta_estado` | `langgraph_checkpoints` |
| Complexidade | Linear | Branch + interrupt + sub-workflows |
| Quando usar | Menu chatbot já existe e precisa só coletar 2-5 campos antes do handover | Fluxo Mackenzie-style com LGPD gate, retomada, ramificação |

## Validators BR reusados

CPF, CNPJ, data_br, telefone_br, email, UF, CEP, min_len, max_len, regex — todos de `shared/validators_br.py`.

## Não conflita com workflow

Worker tenta: wizard primeiro → workflow → menu_item legacy. Wizards de coleta operam só dentro do menu chatbot, não interferem com workflows LangGraph.

## Arquivos críticos

- `db/migrations/080_menu_item_coleta.sql`
- `src/whatsapp_langchain/shared/coleta.py`
- `frontend/src/app/menus/[id]/edit/coleta-editor.tsx`
