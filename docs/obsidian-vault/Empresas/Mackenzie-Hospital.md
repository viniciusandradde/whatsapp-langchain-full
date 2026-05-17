---
title: Hospital Mackenzie
type: empresa
status: cliente-ativo
priority: alta
created: 2026-05-09
updated: 2026-05-17
tags: [cliente, hospital, mackenzie, saude, lgpd]
empresa:
responsavel: Vinicius-Andrade
categoria: cliente
area: Atendimento-Operacao
projeto_pai:
relacionados: [Workflow-Mackenzie, TODO-Placeholders-Mackenzie, Compliance-LGPD]
stakeholders: [Vinicius-Andrade]
deadline:
progresso:
---

# Hospital Mackenzie

## Perfil

- **Setor**: Saúde (hospital geral)
- **Localização**: Rua Hilda Bergo Duarte, 81 - Centro, Dourados/MS
- **Tipo Nexus**: Cliente principal (case de uso mais robusto)
- **Empresa ID no Nexus**: 1 (produção)

## Histórico

- 2026-05-09 — Sprint R+S: dump de 3 meses ZigChat importado em sandbox empresa 999, 8 agentes IA criados, 9055 fewshots classificados, 40 sugestões aprovadas via UI. Memória [[checklist_sprint_rs_radio_hospitalar]]
- 2026-05-12 — Workflows LangGraph completos: fluxo LGPD → coleta nome → menu 8 setores → sub-workflows por setor. 9 workflows ativos (123 nodes). Em produção em `chat.vsanexus.com`. Memória [[checkpoint_workflows_langgraph]]
- 2026-05-12+ — Wizard de coleta por menu_item (triagem antes do atendente humano)

## Setores no workflow

- Maternidade (`guia_maternidade.pdf`)
- Portaria (informações de visita)
- Outras (links + RH email)
- Demais setores via sub-workflows

## Dependências/pendências

- [[TODO-Placeholders-Mackenzie]] — 4 URLs/email genéricos aguardando dados reais do hospital
- LGPD — capturando consent via workflow ([[02-Areas/Compliance-LGPD]])
- Auto-deploy via Dokploy → push master → produção

## Stakeholders externos

- Hospital → ainda sem contato técnico direto formal estabelecido (lacuna)
- TI hospital → eventualmente vai precisar do contato pra trocar URLs placeholders

## Riscos do cliente

- Dados de saúde (LGPD Art. 11, sensíveis) — qualquer leak é grave. Multi-camadas de proteção:
  - Workflow exige consent
  - RBAC `.own` filtra cliente por departamento
  - Audit governança rastreia mudanças admin
- Hospital escala lento — uptime crítico no horário comercial
- Sem SLA formal ainda

## Volume estimado

- Workflows recebem ~300-500 msg/dia (estimativa)
- 8 agentes IA por departamento

## Relacionados

- [[01-Projects/Workflow-Mackenzie]]
- [[01-Projects/TODO-Placeholders-Mackenzie]]
- [[02-Areas/Compliance-LGPD]]
