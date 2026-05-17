---
title: TODO — Placeholders Mackenzie aguardando dados do hospital
type: projeto
status: pendente
priority: media
created: 2026-05-12
updated: 2026-05-17
tags: [todo, mackenzie, hospital, dados]
empresa: Mackenzie-Hospital
responsavel: Vinicius-Andrade
categoria: configuracao
area: Atendimento-Operacao
projeto_pai: Workflow-Mackenzie
relacionados: [Workflow-Mackenzie]
stakeholders: [Vinicius-Andrade, Mackenzie-Hospital]
deadline:
progresso: 0
---

# TODO — Placeholders Mackenzie

## Outcome desejado

Substituir 4 URLs/email placeholders dos workflows Mackenzie pelos valores reais quando hospital informar.

## Placeholders ativos em prod

| # | Workflow slug | Workflow ID | Node | Valor atual |
|---|---|---|---|---|
| 1 | menu_atendimento_cliente | 2 | `guia_maternidade` (url) | `https://hospitalmackenzie.com.br/guias/maternidade.pdf` |
| 2 | menu_portaria | 9 | `vis_link` (URL no texto) | `https://hospitalmackenzie.com.br/visitantes` |
| 3 | menu_outras | 10 | `manual_link` (URL no texto) | `https://hospitalmackenzie.com.br/manual` |
| 4 | menu_outras | 10 | `rh_resp` (email no texto) | `rh@hospitalmackenzie.com.br` |

## Como atualizar (quando tiver dados)

1. Abrir `https://chat.vsanexus.com/workflows/<id>` no painel admin
2. Editar JSON do node correspondente, substituir o placeholder
3. Salvar → cria nova versão imutável em `workflow_chatbot_version` (sem precisar redeploy)

Alternativamente: editar `scripts/import_workflow_mackenzie.py` no repo + push pra master + rodar importer (idempotente).

## URLs que SÃO reais (não mexer)

- `https://bit.ly/3QJXkWw` — Política Privacidade LGPD (menu_principal)
- `https://bit.ly/3SWiqnC` — Guia Pacientes (menu_atendimento)
- `https://modulos.conectew.com.br/conecte/laudos/loginPaciente/view.jsf?edc=265` — Portal Resultados Exames
- Endereço "Rua Hilda Bergo Duarte, 81 - Centro, Dourados/MS" (menu_portaria)

## Relacionados

- [[01-Projects/Workflow-Mackenzie]]
- [[Empresas/Mackenzie-Hospital]]
