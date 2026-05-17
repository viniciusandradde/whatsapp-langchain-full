---
title: Decisão — Convergir Menu Chatbot vs Workflow LangGraph
type: projeto
status: em-aberto
priority: alta
created: 2026-05-17
updated: 2026-05-17
tags: [decisao, arquitetura, menu, workflow]
empresa: VSA-Tech
responsavel: Vinicius-Andrade
categoria: estrategia
area: Atendimento-Operacao
projeto_pai:
relacionados: [Workflow-Mackenzie, Wizard-Coleta-Menu]
stakeholders: [Vinicius-Andrade]
deadline:
progresso: 0
---

# Decisão — Convergir Menu Chatbot vs Workflow LangGraph

## Contexto

Hoje convivem 2 sistemas no Nexus pra triagem/menu antes do agente IA:

1. **`menu_chatbot` legacy** (mig 040+041+042 + wizard de coleta mig 080)
   - Árvore hierárquica de items com `acao_tipo` (12 tipos)
   - Pré-coleta multi-pergunta via `coleta_perguntas` JSONB
   - Worker: `_try_handle_menu` em `processor.py`
   - UI: `/menus/[id]/edit`

2. **`workflow_chatbot` LangGraph** (mig 076+077+078)
   - StateGraph declarativo JSON com 11 node types
   - Sub-workflows via `wf:` refs (BFS resolve)
   - Checkpointer Postgres (resume após desconectar)
   - Worker: `_try_handle_workflow` em `processor.py`
   - UI: `/workflows/[id]` (editor JSON)

Worker prioridade: workflow primeiro → menu_chatbot legacy → agente IA.

## Estado atual

- **Empresa 1 (VSA)**: menu_chatbot ativo (`Atendimento ao Cliente` com 8 chamar_agente). Workflows criados mas `ativo=false`
- **Empresa 1 (modo Mackenzie test)**: workflow `menu_principal` ATIVO, menu_chatbot DESATIVADO
- Outras empresas (se existirem): só menu legacy

## Problema

- Admin precisa entender 2 sistemas
- Docs em 2 lugares (`/menus` vs `/workflows`)
- Manutenção dupla (worker tem 2 handlers, validações duplicadas em alguns lugares)
- Wizard de coleta foi adicionado ao menu legacy DEPOIS do workflow, causando overlap funcional

## Opções

### A. Manter os 2 (status quo)
- **Pro**: menu legacy é simples pra casos triviais (1 nível, 5 opções, sem coleta)
- **Pro**: workflow é poderoso pra fluxos complexos
- **Contra**: confusão pra admin novo, manutenção dupla
- **Esforço**: 0

### B. Migrar tudo pra workflow + deprecar menu
- **Pro**: 1 sistema só, mais limpo
- **Pro**: workflow já suporta tudo que menu faz (e mais)
- **Contra**: migração de menus existentes (importer)
- **Contra**: workflow tem JSON editor que é menos amigável que tree editor do menu
- **Esforço**: alto — precisa de UI better pra workflow + importer menu→workflow + deprecation flag

### C. Migrar tudo pra menu_chatbot expandido + deprecar workflow
- **Pro**: menu já tem UI melhor (tree, drag-and-drop)
- **Contra**: precisa adicionar interrupt/resume, sub-fluxos, validators (basicamente reimplementar LangGraph)
- **Esforço**: muito alto, desperdiça trabalho do workflow

### D. Híbrido formalizado — menu é casca, workflow é miolo
- Menu existe só pra "boas-vindas + escolha primária"
- Cada item do menu pode opcionalmente apontar pra um workflow LangGraph
- **Pro**: usa força dos 2 (UX simples do menu + poder do workflow)
- **Contra**: ainda precisa de admin entender quando usar o quê
- **Esforço**: médio — só precisa add `workflow_id` no `menu_item.acao_payload`

## Recomendação inicial

**Opção D** se você for vender pra outras empresas (UX matters). **Opção B** se Mackenzie/VSA são clientes únicos previstos pra próximos 6 meses (corte ao redundante).

## Próximos passos

- [ ] Decidir A/B/C/D
- [ ] Se B ou D: spec do importer menu→workflow
- [ ] Atualizar [[00-INDEX]] removendo essa decisão de pending

## Relacionados

- [[01-Projects/Workflow-Mackenzie]]
- [[01-Projects/Wizard-Coleta-Menu]]
- [[03-Resources/ADRs/ADR-001-LangGraph-vs-Menu-Legacy]]
