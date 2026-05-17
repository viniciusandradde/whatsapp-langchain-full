---
title: Integração ZigChat — Documentação + Runtime pendente
type: projeto
status: parcial
priority: media
created: 2026-05-15
updated: 2026-05-17
tags: [zigchat, integracao, graphql, vendor]
empresa: ZigChat-Vendor
responsavel: Vinicius-Andrade
categoria: integracao
area: Atendimento-Operacao
projeto_pai:
relacionados: [Workflow-Mackenzie, Convergencia-Menu-vs-Workflow]
stakeholders: [Vinicius-Andrade, ZigChat-Vendor]
deadline:
progresso: 30
---

# Integração ZigChat

## Outcome desejado

Permitir que cliente que já usa ZigChat (com menu cadastrado lá) delegue opções específicas pro Nexus processar via agente IA, e Nexus responda de volta pro ZigChat enviar ao cliente.

## Status

🟡 **PARCIAL** — documentação completa, **runtime nunca foi integrado**.

### Feito
- Token JWT capturado (via DevTools → cookie da sessão de admin no painel ZigChat)
- Schema GraphQL completo via introspection (`docs/zigchat/schema-introspection.json` — 430KB)
- Documentação gerada em `docs/zigchat/` (9 arquivos: README, auth, queries, mutations, tipos, inputs, convenções, exemplos, mapping Nexus↔ZigChat)
- Confirmado: `criarAlterarAgenteIA(data: AgenteIAInput)` aceita schema flat

### Não feito
- Endpoint `/webhook/zigchat` no Nexus pra receber POST do ZigChat
- Cliente outbound `ZigChatClient` pra enviar resposta
- Mapeamento `conexao.provider = 'zigchat'` no Nexus
- Setup do hook no painel ZigChat apontando pro Nexus

## Limitação importante

ZigChat **não tem endpoint de API token machine-to-machine**. Auth é via JWT de sessão de usuário (`Authorization: JWT <token>`). Token dura 5 dias e precisa ser capturado via login no painel web. Pra integração runtime, precisa:
- Ou cron mensal pra renovar token via login programático (impossível sem capturas headless)
- Ou ZigChat lançar API key proper
- Ou usar webhook bidirecional (ZigChat dispara webhook quando user escolhe opção, Nexus responde sincrono no body) — sem precisar autenticar de volta

## Decisão pendente

Vale terminar essa integração? Se sim, qual fluxo (sync vs async)? Ver:

- [[01-Projects/Convergencia-Menu-vs-Workflow]] — alternativa: trazer cliente pro nosso `workflow_chatbot` sem ZigChat
- [[03-Resources/Reference-ZigChat-API]] — referência completa do schema

## Empresa

[[Empresas/ZigChat-Vendor]]

## Arquivos críticos

- `docs/zigchat/` (toda doc)
- `scripts/import_zigchat_dump.py` (importa dump histórico de 178MB pra sandbox empresa 999)
