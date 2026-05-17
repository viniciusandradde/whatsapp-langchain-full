---
title: ADR-008 — Dokploy (vs Kubernetes / Vercel / Railway)
type: adr
status: aceito
priority: media
created: 2026-04-20
updated: 2026-05-17
tags: [adr, infra, dokploy, deploy]
empresa: VSA-Tech
responsavel: Vinicius-Andrade
categoria: decisao
area: Infra-Producao
projeto_pai:
relacionados: [Reference-Dokploy, Infra-Producao]
stakeholders: [Vinicius-Andrade]
deadline:
progresso:
---

# ADR-008 — Dokploy (vs Kubernetes / Vercel / Railway)

## Status

Aceito.

## Contexto

Precisa deployar 4 containers (db + api + worker + frontend) com:
- Auto-deploy de GitHub
- HTTPS via Let's Encrypt
- Env vars gerenciadas
- Multi-réplica de worker
- Custo baixíssimo (solo dev, sem cliente pagante grande no início)

Opções:
- **Kubernetes** (managed: GKE/EKS) — overkill, $$, curva
- **Vercel** — só frontend, sem worker long-running
- **Railway** — bom mas trial limitado, $$ pra produção
- **Render** — caro, sem free tier persistente
- **Dokploy** (self-hosted on Oracle Cloud) — open source, free, gerencia compose

## Decisão

**Dokploy self-hosted em Oracle Cloud ARM (tier gratuito)**.

## Consequências

### Positivas
- **Custo: ~$0/mês** — Oracle Free Tier ARM (Ampere A1, 4 vCPU + 24GB RAM gratuito permanente)
- **Auto-deploy nativo** — webhook GitHub configurado
- **UI decente** — env, domains, logs, deploy history
- **Multi-stack** — Docker Compose direto (não exige Dockerfile especial)
- **Traefik integrado** — HTTPS automático com Let's Encrypt
- **API REST** — controlable via curl + `x-api-key` (memória [[reference_dokploy]] tem IDs)

### Negativas
- **Self-hosted** — uptime depende de Oracle Cloud + nosso cuidado com SO
- **Bugs operacionais frequentes** (memória [[reference_dokploy]]):
  - Container conflict no autoDeploy ("already in use")
  - `addPrefix` bug com path != "/" → workaround com domínios separados
  - Build ARM lento (3-5min)
- **Sem multi-zona** — single host, se Oracle pifar = downtime
- **Comunidade pequena** — bugs novos demoram pra serem corrigidos

## Quando trocaria

- Cliente pagante exigindo SLA 99.9%+ → Kubernetes managed
- Trafego >100K req/dia → load balancer + multi-réplica em outras regiões
- Compliance enterprise → SOC2 / ISO host → managed cloud

## Operação

Tudo em [[03-Resources/Reference-Dokploy]] — comandos, IDs, gotchas.

## Relacionados

- [[02-Areas/Infra-Producao]]
- [[03-Resources/Reference-Dokploy]]
