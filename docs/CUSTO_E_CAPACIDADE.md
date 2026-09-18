# Custo, capacidade e expansão — Chat Nexus

Documento de referência para dimensionar custo por cliente, capacidade do servidor e o que ligar antes de crescer. Base: medições reais da produção (30 dias), o relatório de mensagens do Hospital Mackenzie (jan–ago/2026, via ZigChat), a nova política de preços da Meta e pesquisa de mercado de VPS e isolamento. Câmbio: **R$ 5,50/US$**. Relatório datado de origem: `.planning/reports/20260916-capacidade-10-clientes.md`.

---

## 1. Resumo executivo

| | |
|---|---|
| Meta, a partir de **1º/10/2026** | **R$ 0,035 por mensagem enviada** — inclusive resposta livre dentro das 24h (grátis só até 30/09) e utilidade dentro da janela. Sem tier de volume para service. Fica **fora do plano** (o cliente paga na WABA dele — o Nexus é Tech Provider). |
| IA (LLM) medida | US$ 0,0015/execução · **US$ 0,0113/atendimento (R$ 0,06)** · ~R$ 38/mês para ~650 atendimentos |
| IA Nexus × Meta Business Agent | Nexus ≈ R$ 0,043/msg vs Meta Business Agent ≈ R$ 0,22–0,28/msg → **6× mais barato** |
| Servidor hoje | pico 80 msg/h contra ~1.050 msg/h teóricas (8%); CPU 15%, RAM 38%, disco 40% |
| VPS recomendado p/ 10 clientes | **Hostinger KVM 8, São Paulo** (8 vCPU/32 GB, R$ 259,99 na renovação) ≈ R$ 26/cliente |

---

## 2. Meta / WhatsApp Cloud API — mudança de 1º/10/2026

Linha do tempo (Meta, "Pricing for non-template messages"):
- **01/07/2026** — Meta Business Agent Platform (IA da própria Meta).
- **01/08/2026** — Business Agent cobrado por token: US$ 2/M, ~20–25k tokens/msg ≈ US$ 0,04–0,05.
- **01/09/2026** — tarifas publicadas (BR: **R$ 0,035**).
- **30/09/2026** — último dia de resposta grátis dentro das 24h.
- **01/10/2026** — **toda mensagem enviada pela empresa é cobrada** (humana, automática ou IA, cada balão).

| Categoria | até 30/09 | a partir de 1º/10 | Uso no Nexus |
|---|---|---|---|
| Service (balão livre nas 24h) | R$ 0 | **R$ 0,035** (sem tier de volume) | atendimento humano e IA |
| Utilidade | R$ 0 nas 24h / ~0,035 fora | R$ 0,035 (desconto ≥10k/≥100k) | lembretes |
| Autenticação | ~R$ 0,035 | ~R$ 0,035 | não usado |
| Marketing | ~R$ 0,31–0,38 | ~R$ 0,31–0,38 | Disparador — à parte, 10× a utilidade |
| Meta Business Agent | US$ 2/M tokens (desde 01/08) | ~R$ 0,22–0,28/msg | **não usar** — o Nexus faz mais barato |

Notas: mensagens recebidas continuam grátis; a janela de 72h do Click-to-WhatsApp continua sem custo de entrega; só **uma** cobrança por mensagem (resposta livre com conteúdo promocional é cobrada como service, não marketing). Se a fatura BRL da Meta embute imposto além dos R$ 0,035: **não identificado** (o ZigChat cobra 10% em cima → R$ 0,0385).

**Quem paga:** a mensagem da Meta **nunca entra no preço do plano**. O Nexus é Tech Provider (ver `docs/WABA_SETUP.md`): o cliente cadastra o método de pagamento na própria WABA e a Meta fatura o cliente. Conexão **Evolution** (não oficial) = R$ 0/msg — diferencial dos níveis "Web" da tabela de preços, com o risco de banimento que o anti-ban trata.

**O que o Nexus muda:** não a tarifa (existe em qualquer fornecedor), mas o **número de balões** e o **custo da IA**. Práticas embutidas/possíveis:
- 1 balão por turno (o agente já faz: ~1,03 parágrafos, 75 caracteres medidos).
- Agrupamento de resposta (janela de 8s por conexão, mig 144).
- Menus com botões/listas (WABA interativo) em vez de 5 idas e vindas.
- Automação sem redundância; mídia com legenda; responder no mesmo dia (fora das 24h só template).
- **Produto a construir antes de 1º/10:** painel de mensagens cobráveis por conexão (o webhook de status já traz `pricing.billable` e `category`) + estimativa de custo no módulo de Uso + alerta de teto.

---

## 3. Custo de IA (LLM) — medido no agente do Luís

- US$ 0,0015/execução (6.360 tokens in, 43 out, 870 em cache — média).
- 7,3 execuções por atendimento → **US$ 0,0113/atendimento (R$ 0,06)**.
- ~R$ 38/mês para ~650 atendimentos (setembro: US$ 3,44 em 15 dias; budget US$ 10).
- 92% do custo em `google/gemini-3.1-flash-lite`; a saída é 0,7% dos tokens → **o custo é o prompt + histórico, e cache é a alavanca** (14% dos tokens em cache em set vs 12% em ago, após mover a variável volátil para o fim do prompt).

| Perfil | msgs/mês | IA/mês (44% via IA) | IA/mês (100% IA) |
|---|---|---|---|
| PME (porte Luís) | 5.000 | ~R$ 32 | ~R$ 70 |
| Porte hospital | 35.000 | ~R$ 220 | ~R$ 500 |
| 10 clientes | 140.000 | ~R$ 880 | ~R$ 2.000 |

**Nexus × Meta Business Agent** (por mensagem, a partir de outubro): Nexus IA US$ 0,0015 + entrega US$ 0,0064 ≈ **US$ 0,008 (R$ 0,043)**; Meta Business Agent ≈ US$ 0,045 (R$ 0,25). 10 mil mensagens: **US$ 79** vs US$ 400–500. A IA é 15% do custo por mensagem; a entrega, 85% → **a partir de outubro, economizar balão vale mais que economizar token.** O teto por empresa (`ia_budget`) deve virar limite de plano (o `plano.limite_orcamento_ia_usd` é decorativo — ver `docs/SEGURANCA.md` M1).

---

## 4. Capacidade do servidor

Host atual (OCI, `vps-dev-hermes`): 2 vCPU AMD EPYC, 11 GB RAM, 178 GB (40% usado), Oracle Linux 10.2, 13 containers. Postgres `shared_buffers=128MB` (default), `max_connections=100` (30 em uso). Banco 1.332 MB, 910 MB em `message_queue` (884 MB de base64 esperando o backfill para o MinIO).

Demanda projetada (10 clientes = 3 porte hospital + 7 PME): 140k msgs/mês, ~6.400/dia útil, pico ~23 msg/min. Vazão atual: 2 workers seriais = **17,6 msg/min**. Conexões PG: ~90–110 (SSE abre 1 LISTEN por operador).

**Veredito: cabe, mas não como está.** Gargalos (nenhum é CPU):
1. **Worker estritamente serial** — cada réplica processava 1 msg por vez, ~7s esperando o LLM (CPU 0,35%). **Entregue em 18/09**: `WORKER_CONCURRENCY` (semáforo asyncio na réplica) — medido 4,1× com 4 slots, 89 msg/min por réplica, sem RAM extra (§4b). Réplicas a mais empurraram o host para o swap em 26/07. **Pré-requisito descoberto em 18/09**: o claim com `FOR UPDATE SKIP LOCKED` puro **não era seguro por conversa** — medidas 75 execuções de IA sobrepostas no mesmo atendimento em 30 dias (3.404 execuções, 608 atendimentos) com as 2 réplicas atuais; dois turnos no mesmo `thread_id` disputam o checkpoint do LangGraph. Corrigido com o claim serializado por conversa (`claim_next`: advisory lock com a mesma chave do webhook + `NOT EXISTS` de row `processing` com lease válido), que também exige `LEASE_SECONDS` curto em produção (era 5000; com a trava, crash = conversa presa 83 min).
2. **Fila global sem justiça entre empresas** — um burst do hospital atrasa todos. Precisa de claim round-robin por empresa (ou teto de mensagens em voo por empresa).
3. **Postgres de fábrica** — `shared_buffers` 128 MB num host de 11 GB; e o SSE abre 1 conexão `LISTEN` por operador. Subir para 200–300 e, a médio prazo, multiplexar o LISTEN ou PgBouncer (modo transação). Ver `docs/SEGURANCA.md` M3.

Antes de crescer: executar o **backfill** dos 884 MB + `VACUUM FULL` e ligar o **loop de retenção** (cada cliente novo multiplica o problema que hoje é só do Luís).

---

## 4b. Baseline medido — teste de carga de 2026-09-18

Locust (`stress/`, perfil Evolution) contra o **dev**: 20 clientes simultâneos (10 normais + 10 em
rajada), rampa 5/s, 45 s, empresa 1, IA ligada, saída em `mock`; 20 streams SSE abertos (operadores).

| Camada | Medido |
|---|---|
| Webhook (API) | 233 msgs de 20 telefones, 19 req/s, p50 21 ms / max 372 ms, 0 × 5xx |
| Rate limit por telefone | 147 × 429 nos usuários em rajada (dev = 30/h; produção = 120/h) — proteção, não falha |
| SSE / `NotifyHub` (PR #143) | 20 streams → **1 `LISTEN`** no Postgres; 20/20 com 319 eventos idênticos; sem descarte nem reconexão |
| Debounce (PR #138) | 233/233 `done`, 0 erros no worker |
| **Worker** | **14,7 msg/min** (serial; cada mensagem é um turno de IA, ~4 s). Latência média 6,7 min, máxima 12 min até a fila drenar |

**Repetição com o claim serializado por conversa** (mesma carga, 18/09 à tarde): 252/252 `done`, **0 mensagens
fora de ordem por telefone, 0 execuções de IA sobrepostas por atendimento, 0 deadlock**, 21,8 msg/min (1 réplica;
a diferença para 14,7 é variação do LLM — p50 1,9 s / p95 3,6 s — não ganho da PR). Achado: **229 de 252 respostas
foram "superadas"** (chegou mensagem mais nova do mesmo telefone antes do envio). É a forma da carga (~12 msgs por
telefone em 45 s), mas mostra o desperdício: um turno de IA por row, quase todos engolidos. Em produção são 6,9 %.
Próxima alavanca depois da concorrência: absorver as rows `queued` da conversa ANTES de invocar o agente.

**Com `WORKER_CONCURRENCY=4`** (mesma carga, mesma tarde, 1 réplica):

| | 1 slot | **4 slots** |
|---|--:|--:|
| Vazão | 21,8 msg/min | **89,0 msg/min** (4,1×, linear) |
| Latência média / máxima até responder | 5,6 / 10,9 min | **1,2 / 2,3 min** |
| Fora de ordem por telefone · IA sobreposta por atendimento | 0 · 0 | **0 · 0** (14 amostras ao vivo, 4 em voo, nunca 2 da mesma conversa) |
| Erros de IA · erros do worker · deadlock | 0 | **0** |
| RSS do worker | 115 MB | **168 MB** (CPU 0,3 %) |
| Conexões PG do banco inteiro durante a carga | — | 16 |

Deploy sob carga (SIGTERM com 4 em voo): `worker_draining em_voo=4` → as 4 terminaram em 4,4 s → `worker_stopped`,
0 rows presas em `processing`; o `restart` inteiro levou 5 s. Produção: 2 réplicas × 4 slots ≈ 180 msg/min contra
pico real de 27 — o gargalo passa a ser o LLM (p50 1,9 s / p95 3,4 s por chamada) e as respostas superadas.

Leitura: a leva de 18/09 (TanStack #141/#142, Better Auth #140, NotifyHub #143, aviso de deploy #144)
aguentou 20 simultâneos sem degradar — o painel deixou de ser o limite (operador parado: 48 → 4
req/min; conexões `LISTEN` por processo, não por aba). O limite agora é o **worker serial**: 20
conversas simultâneas com IA é ~5× o que ele entrega. Próximo trabalho de capacidade: paralelismo por
telefone (N workers ou concorrência por thread), preservando a ordem dentro de cada conversa — antes
de qualquer VPS maior.

## 5. VPS — custo-benefício

| Opção | vCPU/RAM/NVMe | R$/mês promo → renovação | Nota |
|---|---|---|---|
| OCI atual | 2/11 GB/178 GB | não identificado | 2 vCPU já dividem 13 containers; swap em uso |
| Hostinger KVM 4 | 4/16 GB/200 GB | 59,99 → 149,99 | mínimo p/ 10 clientes |
| **Hostinger KVM 8** | 8/32 GB/400 GB | 119,99 → 259,99 | **recomendado**: DC São Paulo; firewall, snapshot, DDoS inclusos; folga p/ stack dedicada |
| Hetzner | 4–8 ded./16–32 GB | ~€25–60 (+20% backup) | melhor CPU/€, mas sem DC no Brasil (~200 ms), +37% em abr/2026 |
| Contabo | 8/30 GB/400 GB | ~€15–20 + taxa de região | vCPU sobrevendida, sem backup — evitar para produção |

Migração pelo runbook `docs/MIGRACAO_SERVIDOR.md` (a sessão do WhatsApp vive no Postgres da Evolution; ordem de corte é requisito).

**Divisão de recursos proposta (KVM 8, limites por container):** Postgres 3 CPU/8 GB (`shared_buffers` 2 GB, `max_connections` 300) · API 1,5/1,5 GB · workers 2×(1/768 MB) · frontend 1/1 GB · MinIO 0,5/1 GB · Evolution 1,5/2,5 GB · Dokploy+Traefik+registry 1/2 GB → ~20 GB reservados, 12 GB de folga. Sem limites, um serviço que vaza memória derruba os outros (padrão dos incidentes de jul/ago).

---

## 6. Isolamento entre clientes

**Já existe:** RLS FORCE em 58 tabelas com role sem bypass; teto de IA por empresa (`ia_budget`); rate limits; retenção por empresa/agente; mídia fora do banco; auditoria; relatório de uso mensal.

**Falta para 10 clientes:** justiça na fila (round-robin + teto por empresa); concorrência no worker; limites de plano ligados (atendimentos/usuários hoje só contam); limites de container em todos os serviços; métricas Prometheus + alerta de backlog/p95; teste de carga com Locust antes de cada leva.

**Modelo:** banco compartilhado + `tenant_id` + RLS é o padrão certo para B2B com dezenas de clientes; stack dedicada (compose próprio, banco próprio) só para regulado ou "vizinho barulhento" — oferecer ao hospital no Enterprise (o KVM 8 comporta as duas).

---

## 7. Custo total por cliente

| Item | PME (5k msgs) | Porte hospital (35k msgs) |
|---|---|---|
| Infra (KVM 8 ÷ 10) | R$ 26 | R$ 26 |
| IA (44% via agente) | R$ 32 | R$ 220 |
| Backup, domínio, monitoramento | R$ 5 | R$ 5 |
| **Custo do Nexus** | **~R$ 63** | **~R$ 251** |
| Meta — envios (a partir de 1º/10, fora do plano) | ~R$ 175 | ~R$ 1.225 |

Enterprise (R$ 1.499) com custo interno ~R$ 251 → ~R$ 1.250 de margem. Comparação honesta ao hospital: "ZigChat R$ 1.302 tudo incluso" vs "Nexus R$ 1.499 + Meta R$ 1.218" — o argumento é redução de balões + IA, não a tarifa da mensagem.

---

## 8. Plano de ação (ordem)

1. **Hoje:** fechar a porta 3000 e o SSH público (ver `docs/SEGURANCA.md` C1/C2), 2FA no Dokploy.
2. **Semana:** backfill dos 884 MB + `VACUUM FULL`; PR da retenção (Fase E).
3. Worker: concorrência 4 + claim justo por empresa (dev + Locust antes do merge).
4. Postgres tuning; limites em todos os containers; `swappiness=10`; `dnf-automatic`.
5. Ligar limites de plano (IA, atendimentos, usuários).
6. **Antes de 1º/10:** painel de mensagens cobráveis por conexão + estimativa no Uso + alerta.
7. Migrar para o KVM 8 (Hostinger SP) pelo runbook, firewall + Tailscale desde o boot; Cloudflare proxy + WAF.
8. Hospital: Enterprise com Cloud API (Embedded Signup, pagamento na conta Meta deles) + stack dedicada; medir 30 dias de envios contra os 34.813 do relatório do ZigChat.
9. A cada 3 clientes: Locust, backlog, p95, conexões PG.

Ver também: `docs/SEGURANCA.md`, `docs/MIGRACAO_SERVIDOR.md`, `docs/DOKPLOY.md`, `docs/WABA_SETUP.md`, `docs/BACKUP.md`.
