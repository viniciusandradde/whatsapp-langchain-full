---
title: Gestão de Projeto — sprints, deploys, decisões
type: area
status: ativo
priority: media
created: 2026-05-04
updated: 2026-05-17
tags: [gestao, processo, sprints, sdlc]
empresa: VSA-Tech
responsavel: Vinicius-Andrade
categoria: processo
area:
projeto_pai:
relacionados: []
stakeholders: [Vinicius-Andrade]
deadline:
progresso:
---

# Gestão de Projeto

## Modelo operacional

- **Solo dev** (Vinicius) — todas as funções acumuladas
- **Cadência**: sprints temáticos curtos (1-3 dias por sprint)
- **Branching**: master único, PR opcional (mas geralmente push direto)
- **Deploy**: auto via Dokploy on push master (cuidado: nada de WIP sem flag)

## Workflow padrão de sprint

1. **Discovery** — entender necessidade (cliente, observação prod, débito técnico)
2. **Planejamento** — usar `/plan` ou conversa Claude pra escopar
3. **Implementação** — backend → frontend → tests → docs
4. **Validação** — testes locais + smoke prod
5. **Memória** — registrar SHIPPED em `~/.claude/projects/.../memory/`
6. **Documentação Obsidian** — atualizar vault aqui

## Critério de "feito"

Memória [[feedback_foco_um_modulo]]: terminar 100% (backend + UI + tests + deploy + validar) antes de passar pra próximo módulo. Não deixar UIs órfãs ou endpoints sem consumer.

## Memórias de processo relevantes

- [[feedback_foco_um_modulo]] — não fragmentar atenção
- [[feedback_rebuild_after_code_changes]] — restart container não pega edits novos, sempre rebuild
- [[feedback_testing_policy]] — 4 regras + cov gate 50%
- [[feedback_uv_lock_after_pyproject]] — sempre `uv lock` antes de commitar dep nova
- [[feedback_docker_sg_grupo]] — `sg docker -c "..."` em sessões SSH novas

## Histórico de sprints

Memória [[history_timeline]] tem timeline completa desde `da16ae9` (pré-migração).

Sprints recentes notáveis:
- 2026-04-29: Portal /models /traces + M1 multi-tenant + M2 multi-conexão
- 2026-04-30: M1.x gestão de empresas
- 2026-05-02: M3 CRM Light
- 2026-05-06: Sub-fase A multi-agente + Sub-fase B menu chatbot + paridade ZigChat (19 migs!)
- 2026-05-07: Módulo Agente IA 100% (sidebar 30→6 + TopNavTabs)
- 2026-05-09: Sprint R+S Mackenzie (sandbox 999 + 8 agentes + 9055 fewshots)
- 2026-05-12: Workflows LangGraph + Wizard Coleta
- 2026-05-15..17: Governança RBAC (backend mig 083+084 + frontend perms-context)

## Próximos sprints (planejamento atual)

Decisões pendentes ([[01-Projects/Convergencia-Menu-vs-Workflow]], [[01-Projects/Convergencia-RBAC-Role-vs-Perfis]], [[01-Projects/Integracao-ZigChat]]) bloqueiam pra abrir frentes seguintes.

Próximos candidatos:
1. Integração WhatsApp Business Cloud API direta (sem Twilio)
2. Multi-LLM routing por custo
3. Painel cliente (acesso self-service end user) — primeiro fora do escopo
4. DPO + compliance LGPD ([[02-Areas/Compliance-LGPD]])

## Relacionados

- [[02-Areas/Infra-Producao]]
- [[02-Areas/Observabilidade]]
