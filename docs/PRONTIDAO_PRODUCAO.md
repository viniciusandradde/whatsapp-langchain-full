# Relatório de Prontidão para Produção SaaS — Chat Nexus

> **Gerado em** 2026-06-05 pela suíte de dynamic workflows `prontidao-producao` (`.claude/workflows/`), consolidando 3 auditorias multi-agente: `maturidade-saas` (scorecard 8 dimensões), `problemas-erros` (caça adversarial a bugs) e `status-planejamento` (roadmap vs entregue). Re-executável a qualquer momento via `Workflow({name})` ou `/workflows`.

> **Nota de 2026-07-31.** Este relatório é um retrato daquela data. Dois achados
> deixaram de existir com a remoção do Twilio e do Wareline (migration `153`):
> **R11** (SSRF com credencial Twilio anexada — o guard de validação por hop
> ficou, a auth do provider saiu) e **R16** (defaults Mackenzie no
> `agents/tools/wareline.py`, arquivo deletado). Os demais seguem válidos.

---

## 1. Veredito de Go-Live

### 🔴 NO-GO — Nota de maturidade: **54/100**

O Chat Nexus tem um **núcleo de produto forte e funcional** (multi-tenancy com RLS, billing Asaas funcional, RBAC granular, multi-provider WhatsApp, ~290 endpoints, ~1.200 testes locais), mas **não está pronto para operar como SaaS comercial** porque a camada operacional/de garantias tem buracos que causam **perda de dados de cliente, vazamento cross-tenant e cobrança perdida** sob condições normais de produção.

São **5 bloqueadores de maturidade** + **5 bugs P1 confirmados** (incluindo 1 vazamento cross-tenant ativo e 2 caminhos de perda de mensagem). Nenhum deles é grande em esforço — a maioria é correção cirúrgica — mas **todos precisam ser resolvidos antes de cobrar de clientes terceiros**.

> Importante: o sistema já roda 24/7 para o cliente atual (VSA/Mackenzie) com sucesso. O "NO-GO" é para o salto de **operação assistida (1 cliente)** → **SaaS self-service multi-cliente comercial**, que é o que expõe esses modos de falha.

---

## 2. Scorecard de Maturidade

| # | Dimensão | Score | Bloqueador? | Resumo |
|---|---|:---:|:---:|---|
| 1 | Multi-tenancy & isolamento | **4/5** | Não | RLS STRICT em 58 tabelas, 4 roles, defense-in-depth real. Gaps: suite RLS fora do CI, 14 tabelas FK-indireto sem RLS, fallback silencioso p/ superuser. |
| 2 | Billing & monetização | **3/5** | Não | Asaas funcional (retry, idempotência de customer, ativação só pós-PAYMENT_CONFIRMED). Falta: dedup de webhook, dunning/PAYMENT_OVERDUE, enforcement de limites além de conexões, sem trial, sem E2E do caminho do dinheiro. |
| 3 | Segurança | **3/5** | 🔴 **Sim** | Postura acima da média (token timing-safe, HMAC em prod, CORS, HSTS). Bloqueador: RLS frágil no deploy commitado, authz confia em headers, tokens de reset em plaintext, zero gate de segurança em CI. |
| 4 | Observabilidade & alerting | **2/5** | 🔴 **Sim** | Langfuse + logs JSON + health granular OK. Métricas Prometheus **definidas mas nunca incrementadas no worker**, sem dashboards/alerting/Sentry/heartbeat. Cliente é o primeiro a saber do incidente. |
| 5 | Confiabilidade & ops | **2/5** | 🔴 **Sim** | Runtime bom (fila + retry + DLQ de hooks + 4 réplicas). **Sem backup automatizado do Postgres** (container único = SPOF), sem DR/RTO/RPO/PITR, worker sem SIGTERM gracioso. |
| 6 | Qualidade & CI | **2/5** | 🔴 **Sim** | ~1.200 testes locais, gate cov 50%. Mas `.github/` **untracked** e o único workflow roda `make test-e2e \|\| true` (engole falhas). Sem lint/typecheck/unit/cobertura em CI, zero teste de frontend. |
| 7 | Onboarding & self-service | **2/5** | Não | Wizard pós-login + self-provisioning WhatsApp maduros. Mas sem signup público (`disableSignUp:true`), sem verificação de e-mail, sem trial, sem SMTP — modelo sales-assisted, não self-service. |
| 8 | Performance & escala | **3/5** | Não | Escala horizontal correta (FOR UPDATE SKIP LOCKED, 4 réplicas, at-least-once). Teto baixo: 1 msg/vez por réplica (sem `WORKER_CONCURRENCY`), polling 1s, pool hardcoded, sem autoscale. |

**Nota ponderada: 54/100** (pesos maiores em segurança, multi-tenancy, billing e confiabilidade).

---

## 3. Risk Register

Ordenado por severidade × probabilidade. Fonte: `M`=maturidade, `P`=problemas-erros, `Pl`=planejamento.

| # | Risco | Sev | Fonte | Evidência | Mitigação |
|:--:|---|:--:|:--:|---|---|
| R1 | **Perda total e irreversível de dados de todos os tenants** — Postgres em container único, sem backup automatizado, sem PITR/réplica | 🔴 Crítica | M | `docker-compose.dokploy.yml` (volume único, sem job de backup) | `pg_dump`/`pg_basebackup` agendado + WAL archiving off-site + runbook de restore testado + avaliar réplica streaming |
| R2 | **Vazamento cross-tenant ATIVO** — `GET /api/traces` retorna traces de todas as empresas, expondo telefones de clientes no `thread_id` (LGPD) | 🔴 Crítica (P1) | P | `server/routes/traces.py:157-193` | Add `Depends(get_empresa_context)` + filtrar; ou restringir a `is_superadmin`; incluir `empresa_id` nas tags do trace no worker |
| R3 | **RLS pode estar inerte num redeploy** — `DATABASE_URL_APP`/`chat_nexus_app` ausentes no `docker-compose.yml` e `.env.example`; app cai no superuser que bypassa RLS, sem fail-fast | 🔴 Crítica | M, P | `shared/db.py:190`, `shared/config.py:49` | Fail-fast em `validate_runtime_settings()` exigindo `database_url_app` em prod; commitar no compose/.env.example; rodar `test_rls_isolation.py` como gate de CI |
| R4 | **Perda de mensagem inbound do cliente** — webhook WABA engole falha de enqueue e retorna 200 (Meta não retenta); mídia transitória vira `mark_done` em vez de `mark_failed` | 🔴 Crítica (P1×2) | P | `server/routes/webhook_waba.py:160-174`, `worker/media.py:217-229` + `processor.py:2068-2096` | Propagar exceção de enqueue (5xx → retry da Meta); separar erro transitório (429/5xx/timeout → `mark_failed`) de permanente |
| R5 | **Incidentes invisíveis** — métricas Prometheus do worker nunca incrementadas, sem alerting/Sentry/heartbeat; equipe descobre via reclamação do cliente | 🔴 Alta | M, Pl | `shared/metrics.py` (séries vazias), worker sem `import metrics` | Instrumentar worker + Prometheus/Grafana/Alertmanager sobre `/metrics` e `/api/health/*` + Sentry + heartbeat + runbooks on-call |
| R6 | **Código quebrado vai a prod** — `.github/` untracked + `make test-e2e \|\| true` engole falhas; sem lint/typecheck/unit/cobertura/segurança em CI; auto-deploy em master | 🔴 Alta | M | `.github/workflows/e2e.yml` | Commitar `.github/`; remover `\|\| true`; job bloqueante `ruff + pyright + pytest (unit/smoke, cov 50%)` + scanners `gitleaks/pip-audit/bandit` |
| R7 | **Resposta duplicada ao cliente (multi-worker)** — lease de 60s sem renovação permite reclaim concorrente; `send` antes de `mark_done` sem fencing/idempotência | 🟠 Alta (P1) | P | `shared/queue.py:287-310`, `worker/processor.py:2484-2495` | Renovar lease (heartbeat) + fencing por `attempts`/token no `mark_done`; idempotency key no send; subir `LEASE_SECONDS` p/ p99 real |
| R8 | **Status de template HSM nunca sincroniza** — `UPDATE waba_template` no webhook roda sem RLS context → 0 linhas (silent no-op); campanhas presas em `pending` | 🟠 Alta (P1) | P | `server/routes/webhook_waba.py:193-204` | Resolver empresa do template e `set_request_context` antes do UPDATE; ou `empresa_scope(bypass=True)` para op administrativa global |
| R9 | **Cobrança perdida** — webhook Asaas engole exceção e retorna 200; pagamento confirmado pode não ativar plano sem trilha de auditoria nem retry; enforcement de limites só em conexões | 🟠 Alta | M, P | `server/routes/asaas_webhook.py:67-74`, `shared/asaas.py` | Persistir `billing_event_log` 1º em txn isolada; 5xx em falha de infra; dunning em `PAYMENT_OVERDUE`; aplicar quotas de usuários/atendimentos/docs; reconciliação |
| R10 | **Mensagem inbound duplicada** — sem idempotência por `message_id`; retry do provider cria 2ª row e o agente responde 2x (custo LLM/HSM dobrado) | 🟡 Média (P2) | P | `shared/queue.py:204-239`, `webhook_waba.py:141-172` | UNIQUE parcial em `(empresa_id, conexao_id, message_id)` + `INSERT ... ON CONFLICT DO NOTHING` |
| R11 | **SSRF + vazamento de credencial Twilio** — `download_media` segue redirects com auth Twilio anexada, sem allowlist de host | 🟡 Média (P2) | P | `shared/midia_processing.py:84-93` | Exigir https, bloquear IPs privados/loopback/link-local, não anexar auth cross-host, `follow_redirects=False` |
| R12 | **Contexto RLS derivado de header não validado** — `X-Empresa-Id` seta `app.empresa_id` antes da checagem de membership; qualquer rota futura sem `get_empresa_context` vaza cross-tenant | 🟡 Média (P2) | P | `server/middlewares.py:200-214` | Validar membership no middleware antes de `set_request_context`, ou só setar via `get_empresa_context` |
| R13 | **14 tabelas tenant (FK-indireto) sem RLS** — `cliente_anotacao`, `cliente_tag`, `menu_item*` etc. dependem 100% de validação na aplicação, sem backstop de banco | 🟡 Média (P2) | M, P | `db/migrations/101_*.sql:15-23`, `shared/cliente.py:389` | Denormalizar `empresa_id` + RLS, ou policy via JOIN com a tabela pai; teste E2EIsolamento por tabela |
| R14 | **Campanha duplica/trava** — select sem claim atômico reenvia HSM cobrado; loop fire-and-forget no processo da API sem proteção top-level fica preso em `running` | 🟡 Média (P2) | P | `shared/campanha.py:319-510`, `routes/campanha.py:149` | Claim atômico (`status='enviando'`), reter ref forte da task, mover dispatch p/ worker, try/except + reconciliação |
| R15 | **Eventos de hook perdidos** — `asyncio.create_task` sem ref forte (GC) e shutdown não aguarda tasks de hook → entregas descartadas sem DLQ | 🟡 Média (P2) | P | `shared/hook_dispatcher.py:265` | Reter refs fortes + aguardar no shutdown; idealmente `hook_outbox` durável no mesmo commit |
| R16 | **Acoplamento Mackenzie no harness** — defaults Wareline hardcoded (`cod_especialidade=015`, `cod_plano=BPA`, `cod_servico=00000048`) criam agendamentos errados p/ outros clientes | 🟡 Média (P2) | P | `agents/tools/wareline.py:151-154`, `integrations/wareline/models.py:103` | Mover códigos p/ config por empresa (`wareline_credentials`); remover defaults; campos obrigatórios enquanto não houver config |
| R17 | **Comparações de token não timing-safe** — webhooks Asaas/WABA/Evolution usam `!=` em vez de `hmac.compare_digest` | 🔵 Baixa (P3) | P | `asaas_webhook.py:50`, `webhook_waba.py:83`, `evolution_webhook.py:165` | Trocar por `hmac.compare_digest` |
| R18 | **WABA aceita payload sem assinatura fora de prod** — staging exposto/env mal configurada aceita webhook forjado | 🔵 Baixa (P2) | P | `webhook_waba.py:117-128` | Exigir assinatura sempre que `app_secret` configurado, independente de `is_production` |

---

## 4. Roadmap de Remediação

### 🔴 P0 — Bloqueadores de go-live (resolver ANTES de abrir o SaaS)

| Ação | Risco | Esforço | Onde |
|---|:--:|:--:|---|
| Backup automatizado Postgres + WAL off-site + runbook de restore testado | R1 | M | infra Dokploy/Oracle + `docs/` |
| Escopar `GET /api/traces` por empresa (ou restringir a superadmin) | R2 | **S** | `server/routes/traces.py` |
| Fail-fast exigindo `DATABASE_URL_APP` em prod + commitar no compose/.env.example | R3 | **S** | `shared/config.py`, `docker-compose*.yml` |
| WABA webhook: propagar falha de enqueue (5xx); mídia transitória → `mark_failed` | R4 | S/M | `webhook_waba.py`, `worker/media.py`, `processor.py` |
| CI: commitar `.github/`, remover `\|\| true`, gate `ruff+pyright+pytest+cov` + scanners de segurança | R6 | M | `.github/workflows/` |
| Alerting mínimo: instrumentar worker + Prometheus/Grafana/Alertmanager + Sentry + heartbeat | R5 | M/L | `shared/metrics.py`, worker, infra |
| Rodar `test_rls_isolation.py` como job bloqueante de CI | R3 | **S** | `.github/`, `tests/integration/` |

### 🟢 Quick wins (baixo esforço, alto valor — pegar junto)

- `hmac.compare_digest` nos 3 webhooks (R17) — minutos.
- Idempotência inbound: UNIQUE parcial `message_id` + `ON CONFLICT` (R10).
- `download_media`: allowlist de host + bloquear IP privado + não anexar auth cross-host (R11).
- Reter referência forte das tasks fire-and-forget (hooks + campanha) (R14, R15).
- `try/except` no loop principal do worker para não derrubar o consumo (parte de R14).
- WABA: exigir assinatura sempre que `app_secret` existir (R18).
- Decisão **role ↔ perfil RBAC**: sync (Opção A, ~1-2h) — fecha dívida de governança.
- `billing_event_log` dedup por `event.id` (R9 parcial).

### 🟡 Médio prazo (antes de escalar volume/clientes)

- Fencing de lease (renovação periódica + token no `mark_done`) e idempotência `send→mark_done` (R7).
- RLS nas 14 tabelas FK-indireto: denormalizar `empresa_id` ou policy via JOIN (R13).
- Middleware: validar membership antes de `set_request_context` (R12).
- Billing comercial: dunning/`PAYMENT_OVERDUE`, enforcement de quotas de usuários/atendimentos/docs, reconciliação, E2E do caminho do dinheiro (R9).
- Wareline: defaults Mackenzie → config por empresa (R16).
- Onboarding self-service: signup público + verificação de e-mail + SMTP + trial (dim. 7).
- Concorrência intra-worker (`WORKER_CONCURRENCY`) + LISTEN/NOTIFY no claim (dim. 8 / roadmap).
- Decisão **menu legacy vs workflow LangGraph** (Opção D recomendada) antes de vender a terceiros.

---

## 5. Status do Planejamento

**Nenhum item de roadmap bloqueia o go-live** — todos os pendentes são melhorias futuras. Mas há **deltas roadmap × realidade** a corrigir e **3 decisões em aberto**.

### Roadmap desatualizado (já entregue, marcado como pendente no README)

| Item | README diz | Real |
|---|---|---|
| Calendar Agent v2 S3-S5 | 🟡 pendente | ✅ **Entregue (95%)** — regras (mig 028), aprovação WhatsApp (mig 029), sync cron 5min (mig 030). Falta só teste de S4/S5. |
| Dashboard IA (custo/agente + modelo) | 🟡 pendente | ✅ **Entregue (90%)** — migs 057/058, `dashboard_ia.py`, UI. Falta só suite Smoke/E2E. |

### Genuinamente pendente

- Métricas Prometheus do worker — **25%** (definidas, nunca incrementadas; ver R5).
- LISTEN/NOTIFY no claim — **0%** (polling 1s segue ativo).
- Concorrência intra-worker / Multi-app Meta / Auto-fallback provider / Telegram+IG / IDE visual de workflows — futuro.

### Decisões arquiteturais pendentes

| Decisão | Impacto go-live | Recomendação |
|---|:--:|---|
| **Menu chatbot legacy vs Workflow LangGraph** (2 sistemas de triagem coexistindo) | Alto (produto) | Opção D — menu como casca, cada item aponta p/ workflow. Decidir antes de vender a terceiros. |
| **`empresa_membro.role` vs Perfis RBAC** (2 sources of truth de autz) | Médio (governança/LGPD) | Opção A — sync role↔perfil (~1-2h). Quick win. |
| **Integração ZigChat** (runtime nunca conectado) | Baixo/Nulo | Despriorizar — bloqueio externo (sem API key M2M). Manter docs congeladas. |

### Placeholders de produto em produção (4 — não bloqueadores, links Mackenzie)

`menu_atendimento_cliente` (guia maternidade), `menu_portaria` (visitantes), `menu_outras` (manual + `rh@hospitalmackenzie.com.br`) — URLs para `hospitalmackenzie.com.br/*` possivelmente inexistentes. Editáveis via `/workflows/[id]` sem deploy. Aguardando URLs reais do hospital.

---

## 6. Checklist de Produção SaaS

- [ ] **Backup & DR**: backup Postgres automatizado + off-site + restore testado + RTO/RPO documentados *(R1)*
- [ ] **Isolamento cross-tenant**: `/api/traces` escopado *(R2)* + RLS fail-fast em prod *(R3)* + RLS nas 14 tabelas FK-indireto *(R13)* + middleware valida membership *(R12)*
- [ ] **Garantia de entrega**: webhooks não engolem falha *(R4, R9)* + idempotência inbound *(R10)* + fencing de lease/send *(R7)*
- [ ] **CI gates**: `.github/` commitado, sem `\|\| true`, lint+typecheck+unit+cov + scanners de segurança + suite RLS *(R3, R6)*
- [ ] **Observabilidade/SLA**: métricas do worker instrumentadas + Prometheus/Grafana/Alertmanager + Sentry + heartbeat + runbooks on-call *(R5)*
- [ ] **Segurança**: `hmac.compare_digest` nos webhooks *(R17)* + assinatura WABA sempre *(R18)* + SSRF guard no `download_media` *(R11)* + rotação de secrets documentada
- [ ] **Billing comercial**: dunning/`PAYMENT_OVERDUE` + enforcement de todas as quotas + dedup de webhook + reconciliação + E2E do caminho do dinheiro *(R9)*
- [ ] **Onboarding self-service**: signup público + verificação de e-mail + SMTP transacional + trial
- [ ] **Multi-tenant genérico**: remover acoplamento Mackenzie hardcoded (Wareline, placeholders) *(R16)*
- [ ] **Governança**: decidir role↔perfil RBAC + menu vs workflow
- [ ] **Resiliência de tasks**: fire-and-forget (hooks/campanha) com ref forte + outbox durável *(R14, R15)*

---

## Apêndice — Como reproduzir esta auditoria

```bash
# Suíte completa (orquestrador):
Workflow({ name: 'prontidao-producao' })

# Ou auditorias isoladas:
Workflow({ name: 'maturidade-saas' })      # scorecard 8 dimensões
Workflow({ name: 'problemas-erros' })      # caça a bugs P0-P3
Workflow({ name: 'status-planejamento' })  # roadmap vs entregue
```

Scripts em `.claude/workflows/*.js`. Os achados de `problemas-erros` passam por verificação adversarial (1 refutador refutando-por-padrão nos P0/P1); 31 confirmados de 32 brutos nesta execução (P1:5, P2:22, P3:4).
