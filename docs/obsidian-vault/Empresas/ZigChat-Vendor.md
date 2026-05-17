---
title: ZigChat (concorrente / referência)
type: empresa
status: referencia
priority: baixa
created: 2026-05-06
updated: 2026-05-17
tags: [concorrente, zigchat, paridade]
empresa:
responsavel: Vinicius-Andrade
categoria: concorrente
area:
projeto_pai:
relacionados: [Integracao-ZigChat, Reference-ZigChat-API]
stakeholders: []
deadline:
progresso:
---

# ZigChat (concorrente / referência)

## Perfil

- **Site**: `https://dev.zigchat.com.br`
- **Tipo**: Plataforma concorrente do Nexus (SaaS multi-tenant pra atendimento WhatsApp + agentes IA)
- **Papel**: Benchmark de paridade — usamos como referência de features esperadas

## Histórico de relação

- 2026-05-06 — Vinicius forneceu credenciais de admin (sessão no painel ZigChat) pra captura de JWT
- Documentação extraída: schema GraphQL completo (introspection), agentes, mutations, tipos. Em `docs/zigchat/`
- Sprint paridade ZigChat ([[checklist_paridade_zigchat_completa]]) — 19 migrations cobrindo modelo de dados (mig 040-060)

## Pendências

- [[01-Projects/Integracao-ZigChat]] — decisão em aberto: usar runtime? Documentar e abandonar? Híbrido?
- JWT expira em 5 dias, sem M2M API key → integração runtime inviável hoje

## Pontos de paridade alcançados (vs ZigChat)

Mig 040-060 + UI:
- Departamentos hier
- Perfis + permissões
- Atendentes online/offline
- Modelos de mensagem (quick reply)
- Base de conhecimento
- Campanhas
- Agente IA + catalog
- Menu chatbot
- Webhooks (com DLQ — Nexus tem extra)
- Conexão WhatsApp (Twilio + Evolution)

## Diferenciais Nexus vs ZigChat

- **RBAC `.own/.all`** (mig 083) — ZigChat tem só flat
- **Workflows LangGraph estáticos** — ZigChat tem só menu chatbot
- **Checkpointer LangGraph** — agente IA com memória de conversa
- **NPS automático** — captura ao fechar atendimento
- **OpenRouter multi-LLM** — ZigChat hardcode 1 provider
- **DLQ pra webhooks**
- **Audit governança granular** (mig 084)
- **Coleta wizard por menu_item**

## Relacionados

- [[01-Projects/Integracao-ZigChat]]
- [[03-Resources/Reference-ZigChat-API]]
