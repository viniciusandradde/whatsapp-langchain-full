---
title: Workflow Mackenzie — Chatbot LangGraph
type: projeto
status: shipped
priority: alta
created: 2026-05-11
updated: 2026-05-12
tags: [workflow, langgraph, mackenzie, hospital, lgpd]
empresa: Mackenzie-Hospital
responsavel: Vinicius-Andrade
categoria: produto
area: Atendimento-Operacao
projeto_pai:
relacionados: [Wizard-Coleta-Menu, Convergencia-Menu-vs-Workflow]
stakeholders: [Vinicius-Andrade, Mackenzie-Hospital]
deadline:
progresso: 95
---

# Workflow Mackenzie — Chatbot LangGraph

## Outcome

Hospital Presbiteriano Mackenzie tem chatbot WhatsApp 24/7 com:
- LGPD gate obrigatório antes de coletar qualquer dado
- Coleta de nome
- Menu 8 setores (Atendimento, Agendamento, Exames, Tesouraria, Orçamentos, Portaria, Outras, Ouvidoria)
- Sub-workflows por setor com validators BR (CPF, data_br, telefone_br)
- Handover pra atendente humano com `resumo_template` (vars coletadas)

## Status

✅ **SHIPPED em produção** (`chat.vsanexus.com`) em 2026-05-12.

- 9 workflows ativos pra `empresa_id=1`
- 123 nodes total
- Flag `ENABLE_WORKFLOW_ENGINE=true` em prod
- Fluxo testado E2E via WhatsApp real (commits: 04e034d, d49bba4, 2330100, c5310ee + 4 hotfixes)

## Stack técnica

- **Engine**: LangGraph state-machine (StateGraph + AsyncPostgresSaver)
- **Storage**: Postgres tabelas `workflow_chatbot`, `workflow_chatbot_version` (imutável), `workflow_evento` (audit LGPD)
- **State**: `thread_id = "wf:{atendimento_id}"` no checkpointer
- **11 node types**: send_messages, send_media, send_link, ask_text, ask_choice, set_var, branch, audit_event, transfer_departamento, handover, delegate_to_agent
- **Sub-workflow refs**: `wf:menu_<setor>` resolvidos via BFS + DFS cycle detection

## Decisões importantes

- [[03-Resources/ADRs/ADR-001-LangGraph-vs-Menu-Legacy]] — por que LangGraph
- [[03-Resources/ADRs/ADR-002-Pool-Via-Config-Nao-State]] — fix do msgpack non-serializable
- [[03-Resources/ADRs/ADR-003-Agente-Atual-Default-Como-Estado-Inicial]] — gate do worker

## Riscos / TODO

- ⚠ 4 URLs/email placeholders aguardando dados reais do hospital — ver [[01-Projects/TODO-Placeholders-Mackenzie]]
- ⚠ Workflow `menu_principal` é o root — sub-workflows não precisam estar `ativo=TRUE` individualmente, só ele
- ⚠ `agente_atual` continua com default `'vsa_tech'`/`'atendimento'` que confunde

## Próximos passos

- [ ] Substituir placeholders quando hospital informar
- [ ] Drawer "Ver state runtime" no `/atendimento` (endpoint já existe: `/api/admin/atendimentos/{id}/workflow-state`)
- [ ] Validação cycle detection no PUT do editor
- [ ] Refinar 7 sub-workflows setoriais com MDs originais

## Arquivos críticos

- `db/migrations/076_workflow_chatbot.sql` + `077`/`078`
- `src/whatsapp_langchain/workflows/` (state, nodes, validators, compiler, runner, audit, loader)
- `src/whatsapp_langchain/worker/processor.py::_try_handle_workflow`
- `frontend/src/app/workflows/[id]/editor.tsx`
- `scripts/import_workflow_mackenzie.py`
- `docs/mackenzie/1_*.md` a `9_*.md` (MDs originais do hospital)

## Empresa cliente

[[Empresas/Mackenzie-Hospital]]
