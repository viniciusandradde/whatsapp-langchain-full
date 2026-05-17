---
title: Lição — Auto-deploy Dokploy + falhas recorrentes
type: insight
status: validado
priority: alta
created: 2026-05-04
updated: 2026-05-17
tags: [licao, infra, dokploy, auto-deploy, ops]
empresa: VSA-Tech
responsavel: Vinicius-Andrade
categoria: lessons-learned
area: Infra-Producao
projeto_pai:
relacionados: [Reference-Dokploy]
stakeholders: [Vinicius-Andrade]
deadline:
progresso:
---

# Lição — Auto-deploy Dokploy + falhas recorrentes

## Cenário

Auto-deploy ON: push em master → webhook GitHub → Dokploy rebuilda e recria containers. Soa perfeito mas tem 3 falhas que apareceram MAIS DE 5 vezes desde abril.

## Falhas observadas

### 1. Container conflict ("already in use")

`Error response from daemon: container name "/projetos-chatvsanexus-er02mp-api-1" is already in use`

**Causa**: Dokploy tenta criar o novo container **antes** do antigo morrer/ser removido. Race condition.

**Fix manual** (SSH no Oracle):
```bash
sg docker -c '
# Identificar o container com hash random (criado mas sem nome final)
docker ps -a --filter status=created --format "{{.ID}} {{.Names}}"
# Renomear ou remover antigo
docker rm projetos-chatvsanexus-er02mp-api-1
docker rename <hash_novo> projetos-chatvsanexus-er02mp-api-1
docker start projetos-chatvsanexus-er02mp-api-1
'
```

**Mitigation**: Após fix manual + cleanup, próximos auto-deploys geralmente funcionam.

### 2. Migration falha em SQL = API crashloop

Mig 083 inicial usava `column "id"` que não existia em `permissao` (a PK é `codigo` TEXT). API entrava em crashloop e Dokploy continuava marcando "deploy success" porque build passou.

**Fix**:
- Aplicar migration manualmente via psql (corrigida)
- `INSERT INTO _migrations (name) VALUES ('083_rbac_record_level')`
- `docker restart` da API
- Commitar versão corrigida pra que outros ambientes peguem

**Mitigation**: Testar migration localmente antes de push. Ter healthcheck que detecta crashloop e alerta.

### 3. Build ARM lento (3-5min)

Build no Oracle Ampere A1 demora. Pequena typo em frontend = 4min de wait pro deploy.

**Mitigation**: 
- Reduzir uso de auto-deploy pra pushes triviais
- Considerar BuildKit cache (não testado ainda)

## Padrão de troubleshoot

1. Quando push não reflete em produção em 5min:
   - Checar Dokploy UI → último deploy status
   - SSH + `sg docker -c "docker ps"` → containers em "Restarting"?
   - `sg docker -c "docker logs <container>"` → traceback?

2. Se container conflict:
   - Fix manual com rm/rename
   - Re-trigger deploy via UI Dokploy

3. Se migration falhou:
   - Aplicar manual + INSERT em `_migrations` + restart
   - Corrigir migration no repo

## O que tem que fazer (TODO)

- [ ] Adicionar healthcheck Docker que detecta crashloop e alerta (Slack/email)
- [ ] CI roda migrations contra DB efêmero antes de permitir merge
- [ ] Documentar runbook completo em [[03-Resources/Reference-Dokploy]]
- [ ] Considerar Watchtower como complemento (graceful container swap)

## Por que não migramos pra Kubernetes ainda

Vide [[03-Resources/ADRs/ADR-008-Dokploy-vs-Kubernetes]] — custo + complexidade não compensam pro volume atual. Mas se essas falhas continuarem custando 1h/semana de fix manual, vale revisitar.

## Relacionados

- [[02-Areas/Infra-Producao]]
- [[03-Resources/Reference-Dokploy]]
- [[03-Resources/ADRs/ADR-008-Dokploy-vs-Kubernetes]]
