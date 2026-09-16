# Expandir o Nexus para 10 clientes — custo, capacidade e segurança

Data: 2026-09-16 · Base: produção Nexus (30 dias), relatório do Hospital Mackenzie (jan–ago/2026, BSP atual), pesquisa de mercado. Câmbio R$ 5,50/US$.
Versão visual: artefato "Nexus para 10 clientes".

## Sumário

| | |
|---|---|
| Meta, a partir de 1º/10/2026 | **R$ 0,035 por mensagem enviada**, inclusive resposta livre dentro das 24h (grátis só até 30/09) e utilidade dentro da janela. Sem desconto por volume p/ service. Hospital ≈ R$ 1.218/mês direto na Meta (ZigChat cobra R$ 0,0385 c/ 10% imposto = R$ 1.302). 10 clientes ≈ R$ 4.900/mês → fica FORA do plano (cliente paga na WABA dele, Nexus é Tech Provider) |
| IA Nexus vs Meta Business Agent | Nexus ≈ R$ 0,043/msg (IA US$ 0,0015 + entrega R$ 0,035) vs Meta Business Agent US$ 2/M tokens ≈ R$ 0,22–0,28/msg → 6× mais barato; 10 mil msgs: US$ 79 vs US$ 400–500 |
| IA (medido no Luís) | US$ 0,0015/execução · **US$ 0,0113/atendimento (R$ 0,06)** · US$ 0,0011/msg recebida · ≈ R$ 38/mês para ~650 atendimentos |
| Servidor hoje | pico 80 msg/h contra ~1.050 msg/h teóricas (8%); CPU 15%, RAM 38%, disco 40%, 601 MB em swap |
| Segurança | **P0: porta 3000 (Dokploy) aberta na internet pública** (testado de fora em 16/09) |

## 1. Medições

**Produção (16/08→15/09):** Luís 4.773 msgs (160/dia, pico 304), ~650 atend/mês, 44% respondidas pela IA; VSA 1.946 msgs, 8% IA; total 6.728 msgs, pico horário 80. Latência p50 11,6 s / p95 18,2 s; 0,17% falhas. Picos 10–11h e 15–17h.

**Hospital (BSP atual):** 34.813 service/mês (últ. 3 m), média 32.994 em 8 meses, faixa 26.848–38.125; franquia 1.000; R$ 1.301,80/mês; R$ 9.854 em 8 meses. Empresa 1013 no Nexus, sem conexão ativa ainda.

## 2. Meta (Cloud API) — mudança de 1º/10/2026

Linha do tempo (Meta, "Pricing for non-template messages"): 01/07/2026 Meta Business Agent Platform; 01/08 cobrança por token do Business Agent (US$ 2/M, ~20–25k tokens/msg ≈ US$ 0,04–0,05); 01/09 tarifas publicadas (BR: R$ 0,035); **30/09 último dia de resposta grátis; 01/10 toda mensagem enviada pela empresa é cobrada** (service = utilidade = autenticação por mercado; sem tier de volume p/ service; revisão trimestral). Recebidas continuam grátis; 72h do Click-to-WhatsApp continua sem custo de entrega. Uma cobrança por mensagem (service com conteúdo promocional não vira marketing).

| Categoria | até 30/09 | a partir de 1º/10 | Uso |
|---|---|---|---|
| Service (qualquer balão livre nas 24h: humano, automação, IA de terceiro) | R$ 0 | **R$ 0,035** | atendimento humano e IA |
| Utilidade | R$ 0 nas 24h / ≈ R$ 0,035 fora | R$ 0,035 (desconto ≥10k/≥100k) | lembretes |
| Autenticação | ≈ R$ 0,035 | ≈ R$ 0,035 | não usado |
| Marketing | ≈ R$ 0,31–0,38 | ≈ R$ 0,31–0,38 | Disparador — à parte |
| Meta Business Agent | US$ 2/M tokens (desde 01/08) | ≈ R$ 0,22–0,28/msg | não usar |

Hospital: 34.813 × 0,035 = ≈ R$ 1.218/mês direto na Meta vs R$ 1.302 no ZigChat — trocar de fornecedor economiza ~6%, não elimina. O que o Nexus muda é o NÚMERO de envios (1 balão/turno — medido 1,03 parágrafos/75 chars no Luís; agrupamento 8 s mig 144; menus interativos WABA) e o custo da IA.

10 clientes: PME 5.000 envios ≈ R$ 175; hospital 35.000 ≈ R$ 1.225; total ≈ R$ 4.900/mês. **Fora do plano**: Nexus é Tech Provider (docs/WABA_SETUP.md), o cliente cadastra pagamento na própria WABA e a Meta fatura ele. Conexão Evolution (não oficial) = R$ 0/msg — diferencial real dos níveis "Web". Se a fatura BRL da Meta embute imposto: não identificado.

Práticas (ZigChat/Conversa Labs): 1 balão por turno; responder tudo junto; sem boas-vindas+confirmação+aguarde; mídia com legenda; revisar antes de enviar; responder no mesmo dia (fora das 24h só template); Click-to-WhatsApp 72 h grátis. Produto: painel de envios cobráveis por conexão (webhook status `pricing.billable`/`category`) + estimativa de custo no Uso + alerta de teto, antes de 1º/10.

## 3. IA

92% do custo em `google/gemini-3.1-flash-lite` (US$ 0,25/M in, 1,50/M out, cache 0,025/M). Saída é 0,7% dos tokens — custo é prompt+histórico; cache é a alavanca (14% dos tokens em cache em set vs 12% em ago após mover o volátil pro fim).

| Perfil | msgs/mês | IA/mês (44% IA) | IA/mês (100% IA) |
|---|---|---|---|
| PME | 5.000 | R$ 32 | R$ 70 |
| Porte hospital | 35.000 | R$ 220 | R$ 500 |
| 10 clientes | 140.000 | R$ 880 | R$ 2.000 |

`plano.limite_orcamento_ia_usd` é decorativo — amarrar ao `ia_budget`.

## 4. Capacidade

Host: 2 vCPU EPYC, 11 GB, 178 GB (40%), 13 containers; Postgres `shared_buffers=128MB`, `max_connections=100` (30 em uso). Banco 1.332 MB, 910 MB em `message_queue` (884 MB base64 esperando backfill).

Demanda 10 clientes: 140k msgs/mês, 6.400/dia útil, pico ≈ 1.400/h ≈ **23 msg/min** (pior caso 10 hospitais: 63 msg/min). Vazão atual: 2 workers seriais = **17,6 msg/min**. Conexões PG: ≈ 90–110 (SSE abre 1 LISTEN por operador).

**Veredito: cabe, mas não como está.** Gargalos (nenhum é CPU):
1. Worker serial → `asyncio.Semaphore(4)` por réplica (≈70 msg/min, sem RAM extra; SKIP LOCKED já permite). Réplicas a mais empurraram o host pro swap em 26/07.
2. Fila global sem justiça entre empresas → claim round-robin por empresa + teto de mensagens em voo.
3. Postgres de fábrica → `shared_buffers` 2 GB, `effective_cache_size`, `max_connections` 300; médio prazo multiplexar LISTEN ou PgBouncer.
Antes de crescer: backfill (Fase C) + `VACUUM FULL` + retenção (Fase E).

## 5. VPS

| Opção | Recursos | R$/mês promo → renovação | |
|---|---|---|---|
| OCI atual | 2/11 GB/178 GB | não identificado | hoje |
| Hostinger KVM 4 | 4/16 GB/200 GB | 59,99 → 149,99 | mínimo |
| **Hostinger KVM 8** | 8/32 GB/400 GB | 119,99 → 259,99 | **recomendado** (DC São Paulo; firewall, snapshot, DDoS inclusos; folga p/ stack dedicada) |
| Hetzner | 4–8 ded./16–32 GB | ≈ €25–60 +20% backup | sem DC BR, +37% abr/2026 |
| Contabo | 8/30 GB/400 GB | ≈ €15–20 + região | vCPU sobrevendida, sem backup — evitar |

Limites propostos (KVM 8): Postgres 3 CPU/8 GB · API 1,5/1,5 GB · workers 2×(1/768 MB) · frontend 1/1 GB · MinIO 0,5/1 GB · Evolution 1,5/2,5 GB · Dokploy+Traefik+registry 1/2 GB → ≈ 20 GB reservados, 12 GB de folga. Infra ≈ R$ 26/cliente.

## 6. Isolamento

Mantido: RLS FORCE 58 tabelas (role sem bypass), `ia_budget`, rate limits, retenção por empresa/agente, mídia fora do banco, auditoria.
Falta: justiça na fila, concorrência no worker, limites de plano ligados (atendimentos/usuários só contam), limites em todos os containers, métricas Prometheus + alerta de backlog/p95, Locust antes de cada leva.
Modelo: compartilhado com RLS é o padrão certo; stack dedicada (compose próprio, banco próprio) só para regulado — oferecer ao hospital no Enterprise.

## 7. Segurança (produção, 16/09)

| Sev | Achado | Correção |
|---|---|---|
| P0 | Dokploy :3000 acessível do IP público 163.176.232.179 (docker-proxy 0.0.0.0; Security List OCI deixa) | bloquear 3000 na Security List/`DOCKER-USER`; acesso só via Tailscale ou domínio com `ipAllowList` 100.64.0.0/10; 2FA |
| P0 | SSH 22 público, `PermitRootLogin without-password`, sem fail2ban (chave obrigatória OK) | restringir ao tailnet; `PermitRootLogin no`; fail2ban/sshguard |
| P1 | firewalld inativo, `INPUT ACCEPT`, `DOCKER-USER` vazio; rpcbind/pmcd/pmlogger/Swarm em 0.0.0.0 (filtrados só pela nuvem) | regras no `DOCKER-USER` (80/443 público, resto tailnet); desabilitar pcp/rpcbind |
| P1 | 187 updates pendentes, sem dnf-automatic | `dnf-automatic` security + reboot mensal |
| P1 | 11 de 13 containers sem limites | tabela da seção 5 |
| P2 | Cloudflare "somente DNS" (sem WAF) | proxy laranja + WAF no painel; webhooks passam; Cloudflare Access opcional em /companies, /settings |
| P2 | swap em uso, swappiness 60 | swappiness 10 |
| OK | RLS, HMAC/apikey webhooks, headers+HSTS, rate limit login, backup cifrado off-site, segredos fora do repo, Tailscale, login events | — |

Gerenciamento por IP: Dokploy/SSH/Postgres/MinIO só pelo tailnet; painel Nexus público com WAF + ipAllowList/Access nas telas de plataforma; webhooks públicos com assinatura; `api:8000` nunca no Traefik.

## 8. Custo por cliente

| Item | PME (5k) | Hospital (35k) |
|---|---|---|
| Infra | R$ 26 | R$ 26 |
| IA (44%) | R$ 32 | R$ 220 |
| Backup/domínio/monitor | R$ 5 | R$ 5 |
| **Custo do Nexus** | **≈ R$ 63** | **≈ R$ 251** |
| Meta envios (a partir de 1º/10) — fora do plano, conta do cliente | ≈ R$ 175 | ≈ R$ 1.225 |

Hospital: a mensageria (≈ R$ 1.218 na Meta) existe em qualquer fornecedor; o Nexus vende IA a R$ 0,06/atendimento, menos balões por conversa e painel de custo. Enterprise R$ 1.499 com custo interno ≈ R$ 251 → ~R$ 1.250 de margem. Comparação honesta: "ZigChat R$ 1.302 tudo incluso" vs "Nexus R$ 1.499 + Meta R$ 1.218" — a resposta é redução de envios + IA, não tarifa.

## 9. Plano de ação

1. Hoje: fechar 3000 e SSH público (Security List + DOCKER-USER), 2FA Dokploy.
2. Semana: backfill 884 MB + VACUUM FULL; PR Fase E.
3. Worker: concorrência 4 + claim justo por empresa (dev + Locust antes do merge).
4. Postgres tuning; limites em todos os containers; swappiness; dnf-automatic.
5. Ligar limites de plano.
6. Migrar para KVM 8 (Hostinger SP) pelo runbook, firewall + Tailscale desde o boot; Cloudflare proxy + WAF.
7. Antes de 1º/10: painel de mensagens cobráveis por conexão + estimativa no Uso + alerta; revisar prompts/automações p/ 1 balão por turno; menus interativos WABA.
8. Hospital: Enterprise com Cloud API (Embedded Signup, pagamento na conta Meta deles) + stack dedicada; medir 30 dias de envios contra os 34.813 — meta é reduzir o número.
9. A cada 3 clientes: Locust, backlog, p95, conexões PG.

## Fontes
Meta "Pricing for non-template messages" (developers.facebook.com/…/pricing/non-template-messages), ZigChat boas-práticas (zigchat.nym.net.br/boas-praticas), Landbot/Wati/SendPulse (mudança de outubro), Conversa Labs (whatsapp-2026), Meta pricing (developers.facebook.com), Message Central BR 2026, EngageLab, go4whatsup; OpenRouter gemini-3.1-flash-lite; Hostinger BR, leiturasingular (renovação), valebyte, VPSBenchmarks; Dokploy docs Tailscale, issues #2661/#4048, Traefik IPAllowList, MassiveGRID; Neon noisy neighbor, ClickHouse multi-tenant Postgres, PostgreSQL SME Cookbook.
