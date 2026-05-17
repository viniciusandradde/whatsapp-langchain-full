---
title: VSA-Tech
type: empresa
status: ativo
priority: alta
created: 2026-04-15
updated: 2026-05-17
tags: [empresa, vsa, owner, sandbox]
empresa:
responsavel: Vinicius-Andrade
categoria: owner
area:
projeto_pai:
relacionados: []
stakeholders: [Vinicius-Andrade]
deadline:
progresso:
---

# VSA-Tech

## Perfil

- **Tipo**: Empresa própria (Vinicius Andrade)
- **Papel no Nexus**: Owner + ambiente de desenvolvimento/sandbox
- **Domínio operacional**: `vsanexus.com` (`chat.vsanexus.com` + `api.vsanexus.com`)
- **Empresa ID no Nexus**: 1 (próprio admin tenant) e 999 (sandbox isolado pra testes)

## Papéis

- Provedor do produto Nexus Chat AI pra clientes externos (atual: [[Mackenzie-Hospital]])
- Sandbox isolado (empresa 999) pra:
  - Imports de dump ZigChat
  - LLM-as-judge eval
  - Datasets LangSmith
  - Teste de novos agentes antes de copiar pra cliente

## Stack/infra própria

- Oracle Cloud ARM (Free Tier) — host
- Dokploy em `dockploy.vsatecnologia.com.br` — orquestração
- GitHub `viniciusandradde/whatsapp-langchain` — source
- OpenRouter — única chave LLM (paga só esse)
- LangSmith — tracing

## Membros do tenant 1 no painel

- Vinicius (superadmin) — owner
- Test users (`atendente.atendimento@vsanexus.test`, etc.) — pra QA RBAC

## Relacionados

- [[People/Vinicius-Andrade]]
- [[02-Areas/Infra-Producao]]
- [[03-Resources/Reference-Dokploy]]
