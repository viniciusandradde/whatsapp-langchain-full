---
title: Nexus Chat AI — Índice
type: index
status: ativo
priority: alta
created: 2026-05-17
updated: 2026-05-17
tags: [index, nexus, vault]
empresa: VSA-Tech
responsavel: Vinicius-Andrade
categoria: meta
area: Gestao-Projeto
projeto_pai:
relacionados: []
stakeholders: [Vinicius-Andrade]
deadline:
progresso: 100
---

# Nexus Chat AI — Vault PARA

Vault Obsidian do projeto **Nexus Chat AI** (`whatsapp-langchain`), plataforma WhatsApp + agentes LangChain/LangGraph, deployada em `chat.vsanexus.com`.

## Estrutura

- **01-Projects/** — projetos ativos com deadline ou outcome concreto
- **02-Areas/** — áreas contínuas de responsabilidade (sem deadline)
- **03-Resources/** — referências reutilizáveis + ADRs (Architecture Decision Records)
- **04-Archive/** — projetos encerrados (vazio na inicialização)
- **People/** — pessoas envolvidas
- **Empresas/** — entidades cliente/vendor
- **Insights/** — lições aprendidas, padrões observados, decisões implícitas

## Atalhos críticos

### Decisões pendentes (alta prioridade)
- [[01-Projects/Convergencia-Menu-vs-Workflow]] — convivem 2 sistemas de menu (legacy + LangGraph)
- [[01-Projects/Integracao-ZigChat]] — exploração feita, runtime nunca integrado
- [[01-Projects/Convergencia-RBAC-Role-vs-Perfis]] — role legacy convive com perfis RBAC novos

### Projetos SHIPPED recentes
- [[01-Projects/Workflow-Mackenzie]] — 9 workflows LangGraph em prod
- [[01-Projects/Governanca-RBAC-Backend]] — record-level + audit (sprint 1)
- [[01-Projects/Governanca-RBAC-Frontend]] — UI filtra por perm (sprint 2)
- [[01-Projects/Wizard-Coleta-Menu]] — triagem multi-pergunta por menu_item

### Áreas operacionais
- [[02-Areas/Infra-Producao]] — Dokploy, Oracle Cloud, autoDeploy
- [[02-Areas/Compliance-LGPD]] — audit, retenção, LGPD gate Mackenzie
- [[02-Areas/Atendimento-Operacao]] — fluxo cliente → IA → atendente
- [[02-Areas/Observabilidade]] — logs, traces, métricas, SSE
- [[02-Areas/Gestao-Projeto]] — sprints, deploys, processo

### Referências quentes
- [[03-Resources/Stack-Tecnico]] — Python/FastAPI/LangGraph/Next.js/Postgres
- [[03-Resources/Reference-ZigChat-API]] — schema GraphQL ZigChat
- [[03-Resources/Reference-Dokploy]] — comandos API, gotchas

### ADRs (Architecture Decision Records)
- [[03-Resources/ADRs/ADR-001-Postgres-como-fila]]
- [[03-Resources/ADRs/ADR-002-Worker-separado-do-API]]
- [[03-Resources/ADRs/ADR-003-LangGraph-checkpointer]]
- [[03-Resources/ADRs/ADR-004-OpenRouter-unificado]]
- [[03-Resources/ADRs/ADR-005-Better-Auth-em-schema-separado]]
- [[03-Resources/ADRs/ADR-006-RBAC-record-level-own-all]]
- [[03-Resources/ADRs/ADR-007-Reset-password-server-side]]
- [[03-Resources/ADRs/ADR-008-Dokploy-vs-Kubernetes]]

### People
- [[People/Vinicius-Andrade]] — owner

### Empresas
- [[Empresas/VSA-Tech]] — owner tenant
- [[Empresas/Mackenzie-Hospital]] — cliente principal
- [[Empresas/ZigChat-Vendor]] — concorrente/referência

### Insights
- [[Insights/Patterns-Frontend-Server-Actions]] — wrappers Server Actions evitam bundle de `pg` no client
- [[Insights/Lessons-Auto-Deploy-Dokploy]] — 3 falhas recorrentes do auto-deploy + fix
