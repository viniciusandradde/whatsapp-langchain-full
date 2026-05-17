---
title: Vinicius Andrade
type: pessoa
status: ativo
priority: alta
created: 2026-04-15
updated: 2026-05-17
tags: [pessoa, owner, dev, vsa]
empresa: VSA-Tech
responsavel:
categoria: stakeholder
area:
projeto_pai:
relacionados: []
stakeholders: []
deadline:
progresso:
---

# Vinicius Andrade

## Perfil

- **Email**: viniciusandradde@gmail.com
- **Empresa**: VSA-Tech (founder)
- **Papel**: Owner + dev solo do Nexus Chat AI (`whatsapp-langchain`)
- **Username** dev: viniciusandradde (GitHub)
- **Working dir**: `/home/dev/projetos/whatsapp-langchain`

## Preferências de trabalho (observadas)

Memórias `~/.claude/projects/.../memory/`:

- [[feedback_foco_um_modulo]] — **terminar 100% antes de passar pra próximo**. Backend + UI + tests + deploy + validar. Sem UIs órfãs.
- [[feedback_rebuild_after_code_changes]] — restart container não pega edits novos. **Sempre rebuild** após mudança de código
- [[feedback_testing_policy]] — 4 regras + cov gate 50% (sobe pra 65% até Fase 6)
- [[feedback_uv_lock_after_pyproject]] — sempre `uv lock` antes de commitar dep nova (senão Docker build falha)
- [[feedback_docker_sg_grupo]] — `sg docker -c "..."` em SSH novo (opc no grupo docker mas precisa relogar)
- Atendimento humanizado — quando entrega de feature foca em mensagens (preferência por "entre em contato com suporte" vs "veja os logs")

## Stack que domina

- Python (FastAPI, LangGraph, asyncpg)
- TypeScript/React (Next.js App Router)
- SQL/Postgres
- Docker + Compose + Dokploy
- LangSmith / OpenRouter

## Tradeoffs preferidos

- **Pragmatismo > pureza** — aceita Postgres como fila, Dokploy self-hosted
- **Custo baixo > escala teórica** — Oracle Free Tier > Kubernetes pago
- **Solo > delegação** — toca tudo: backend, FE, infra, comercial
- **Sprints curtos** — 1-3 dias por sprint, deploy mesmo dia
- **Doc em pt-BR** — todos os arquivos do projeto em português

## Padrão de comunicação

- Mensagens curtas, sem cerimônia
- Aceita interrupção do plano se cliente pediu algo urgente
- Quer ver resultado ASAP — paciência baixa pra setup longo
- **Não gosta** de mensagens técnicas vazando pro cliente final (motivo da sanitização do drawer de atendimento 296)

## Clientes/projetos ativos

- [[Empresas/Mackenzie-Hospital]] — cliente principal (workflows hospitalares + RBAC)
- [[Empresas/VSA-Tech]] — empresa própria, sandbox/staging

## Relacionados

- [[02-Areas/Gestao-Projeto]]
