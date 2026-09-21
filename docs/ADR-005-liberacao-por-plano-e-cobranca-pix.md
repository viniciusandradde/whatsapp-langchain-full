# ADR-005 — Liberação de recursos por plano e cobrança por Pix (Mercado Pago + InfinitePay)

- **Status:** aceito pelo dono em 20/09/2026 ("Continue conforme todo o plano proposto") · **em execução** — rastreio etapa a etapa na §9 (é a lista que não pode se perder) · **revisão 20/09 (mesmo dia):** cobrança passa a usar os **planos hospedados** do Mercado Pago (Assinaturas) e da InfinitePay (Cobrança Recorrente) com ativação manual — D7/D8/D9/D12 e a leva F reescritos; a integração por API fica como referência no §6.3
- **Origem:** `docs/PLANOS_RECURSOS.md` (levantamento recurso × plano, 20/09), ADR-004 (gate de contexto/modelos — mig 188, PR #164, o primeiro gate desta série), memória `reference_gateways_pix_mercadopago_infinitepay`
- **Público deste documento:** quem for codar (inclusive um modelo menor). O que precisa de decisão já está decidido aqui; o que não está escrito **não** deve ser inventado — perguntar ao dono.
- **Regra de manutenção:** cada PR desta série atualiza a §9 (status, número da PR, data) no mesmo commit ou no docs-only seguinte. Uma etapa sem linha na §9 não existe.

---

## 1. Contexto

O painel vende quatro planos (Free R$ 0 · Pessoal R$ 97 · Pro R$ 299 · Enterprise R$ 1.499) com limites e features semeados em `plano` (migs 059, 122, 134, 177, 188), mas **só seis recursos são gateados de verdade** (`calendar`, `voz`, teto/mídia do disparo, `limite_conexoes`, `contexto_max`, `modelos_premium`). O resto — inclusive o teto de IA do plano — é liberado para todo mundo: um Free pode digitar US$ 1.000 em `/governanca/ia-budget` e a plataforma paga. Detalhes por recurso em `docs/PLANOS_RECURSOS.md` §2–§4.

A cobrança nunca existiu de verdade: `routes/billing.py` aponta para o Asaas (mig 105) e nenhuma empresa pagou por ali. O dono decidiu (20/09) cobrar por **Pix** com **Mercado Pago** e **InfinitePay**, substituindo o Inter planejado (zero código, nada a desfazer).

**Por que os gates vêm antes da cobrança:** quando um pagamento atrasa, a única ação automática segura é rebaixar a empresa para Free — e isso só significa alguma coisa se os gates do Free valerem. Sem eles, "rebaixar" não muda nada e a inadimplência não tem consequência.

## 2. Decisões

| # | Decisão | Alternativa rejeitada |
|---|---|---|
| D1 | A coluna **Proposta** do levantamento vira a **matriz de liberação** (§3), sem alteração. Exceções por empresa entram como grandfathering (D3), não como mudança da matriz. | Rediscutir recurso a recurso — o dono aprovou o conjunto. |
| D2 | **Padrão único de gate**, o mesmo da voz (mig 177) e do contexto (mig 188): rota → 402 `detail{error, feature|recurso, plano_atual, upgrade_to, message}` via `require_plano_feature`/`assert_plano_feature`/`require_plano_limit`; worker → **degrada** (nunca falha o turno) lendo `get_plano_info` (cache 30 s); painel → cadeado que leva ao `/billing` (o item não some). | Esconder o item do menu (o cliente não descobre o que existe); 403 (a UI já traduz 402). |
| D3 | **Grandfathering por empresa via `feature_flag`** (mig 037, já tem tela superadmin em `/settings/feature-flags`): chave `plano.<nome>` sobrepõe a chave do plano na leitura (`get_plano_info` faz o merge). Antes de ligar cada leva em produção, rodar a consulta de uso da §5 e cadastrar as exceções — **a 1018 (Pro) é a âncora: nada regride nela sem aviso**. | Coluna nova em `empresa` (mais schema para a mesma coisa); editar o plano (afeta todos). |
| D4 | **Teto de IA do plano é o máximo do `ia_budget`**: `PUT /api/v1/ia-budget` recusa `limite_usd > plano.limite_orcamento_ia_usd` (402) e a linha do mês nova herda `min(limite anterior, teto do plano)`. `limite_orcamento_ia_usd` NULL = sem teto. | Substituir o `ia_budget` pelo teto do plano (perde a governança fina que já existe e a ação de estouro). |
| D5 | **Atendimentos/mês é bloqueio suave**: ao atingir o limite, a **IA para** (marker interno + chip na timeline) e o **atendimento humano continua**; aviso ao admin em 80 % (banner no painel + WhatsApp pelo caminho do resumo diário). Nunca recusar mensagem de cliente. | 402 no webhook (perde mensagem de cliente — inaceitável). |
| D6 | **Ordem fixa das levas**: A (limites que já existem + teto de IA) → B (custo de LLM por mensagem) → C1 (módulos) → C2 (quantidades e retenção) → D (painel: cadeados + `/billing` real) → E (vigência do plano e rebaixamento) → F (cobrança por planos hospedados nos gateways). Uma PR por leva, dev primeiro, o dono faz o merge. (Reconfirmada pelo dono em 20/09: manter a ordem, gateways depois de C1/C2/D.) | Tudo numa PR (impossível validar e conferir em produção); antecipar os gateways (o dono preferiu fechar os gates primeiro). |
| D7 | **Cobrança pelos planos hospedados dos gateways, sem API de cobrança** (decisão do dono 20/09, revisando a versão inicial desta ADR): o dono cria os planos no **Mercado Pago → Assinaturas** (recorrência automática — só **cartão de crédito ou saldo em conta**, Pix não entra na assinatura) e na **InfinitePay → Cobrança Recorrente** (cartão com cobrança automática, ou **Pix com lembrete por WhatsApp a cada ciclo**). O Nexus guarda o **link** de cada plano por gateway e mostra no `/billing`; a **ativação é manual pelo superadmin** ("Registrar pagamento até <data>" em `/companies/[id]` → `transacao` `status='pago'` + `empresa.plano_valido_ate`), conciliando pelo painel do gateway. Avisos em D-7, D-3 e no vencimento; **carência de 5 dias**; depois, rebaixa para Free automaticamente (job diário no worker) — leva E inalterada. Ciclo anual fica para depois. | Versão inicial: cobrança avulsa mensal por Pix via API (Orders API do MP + Checkout da IP, QR no painel, ativação automática) — 3 levas de código para 8 empresas; e o Pix avulso não tem recorrência, que os planos hospedados no cartão têm. A especificação da API fica no §6.3 como referência, caso o volume justifique voltar. |
| D8 | **Nada no gateway ativa plano sozinho.** Só o registro de pagamento (superadmin) estende a vigência; a evidência é o painel do gateway. Incremento opcional (F.1): webhook de assinatura do Mercado Pago (`subscription_authorized_payment`) estendendo a vigência **depois** de validar `x-signature` e confirmar por `GET /preapproval/{id}` — webhook continua não sendo fonte de verdade. InfinitePay: a recorrência **não tem webhook** documentado; fica manual. | Confiar no corpo do webhook (qualquer um poderia "pagar" um plano com um POST). |
| D9 | **Reaproveitar `transacao`** (migs 059/105/116): o registro manual grava `gateway` (`mercadopago | infinitepay | manual`), `gateway_id` (id da cobrança no painel do gateway, opcional), `periodo_inicio/fim`, `status='pago'`; as colunas `asaas_*` ficam órfãs de propósito — não reescrever migração aplicada. O código Asaas (`shared/asaas.py`, rotas) sai numa PR própria depois de F em produção. | Tabela nova por gateway. |
| D10 | **Reprecificação do Pro antes de publicar preço** (raio-X 28/08: R$ 397–497 com teto de IA US$ 25–30 + excedente). Proposta padrão desta ADR: **R$ 497 / US$ 30**; o número final é do dono e vira migration (é dado). Até lá, D4 usa o teto atual da tabela (Pro = US$ 100), que não regride ninguém. Enterprise segue contrato/manual (fora do checkout self-service). | Publicar o Pix com o Pro a R$ 299 (margem negativa medida na 1018). |
| D11 | **Quem troca o plano:** admin da empresa faz upgrade pagando Pix no `/billing`; downgrade só no vencimento (ou superadmin à mão, como hoje). Upgrade no meio do ciclo paga o valor cheio do plano novo e o período recomeça (sem pró-rata). | Pró-rata (regra a mais para explicar e testar; volume não justifica). |
| D12 | **InfinitePay é o padrão** (decisão do dono 20/09: "o padrão é o que tem mais recursos sem custo para mim" — pelo site da InfinitePay: conta sem mensalidade, Pix taxa zero, cartão até 12×, recorrência por cartão ou Pix com lembrete); o `/billing` destaca o link da InfinitePay como "Recomendado" e mostra o do Mercado Pago como alternativa ("cartão recorrente com retentativas"). Não há gateway "ativo" nem fallback — não há chamada de API para falhar. As **taxas de cartão** dos dois não foram lidas nesta ADR: conferir nos painéis antes de publicar (F.0). | Um gateway ativo com fallback (só fazia sentido com criação de cobrança por API); dois links com o mesmo peso (o dono quer um padrão). |
| D13 | Free **não** tem vencimento (`plano_valido_ate` NULL); plano pago cadastrado à mão pelo superadmin também pode ficar sem vencimento (cortesia/contrato). Só cobrança Pix cria vencimento. | Vencer tudo (quebraria a 1 e a 1024, que são contrato). |

## 3. Matriz de liberação (fonte única — os seeds das migrations copiam daqui)

Colunas numéricas de `plano` (`NULL` = ilimitado):

| coluna | Free | Pessoal | Pro | Enterprise | leva |
|---|---|---|---|---|---|
| `limite_usuarios` | 2 | 2 | 10 | NULL | A (já semeado) |
| `limite_conexoes` | 1 | 1 | 3 | NULL | feito (mig 059/134) |
| `limite_atendimentos_mes` | 100 | 500 | 5.000 | NULL | A (já semeado) |
| `limite_orcamento_ia_usd` | 5 | 10 | 100 → **30** (D10) | 500 → **150** (D10) | A usa o valor atual; D10 muda por migration |
| `limite_documentos_kb` | 5 | 20 | 100 | NULL | A (já semeado) |
| `limite_agentes` (**nova**, mig 189) | 1 | 1 | 5 | NULL | A |

Chaves de `plano.features` (boolean, ou número quando é teto):

| chave | Free | Pessoal | Pro | Enterprise | leva | onde aplica |
|---|---|---|---|---|---|---|
| `contexto_max` / `modelos_premium` | lite / off | regular / off | large / on | extended / on | feito (mig 188) | — |
| `calendar` | off | off | on | on | feito | `routes/calendar_integration.py`; a tela `/agendamentos` segue esta chave (D) |
| `voz` | off | off | on | on | feito | — |
| `disparador_max_contatos` / `disparador_media` | 25 / off | — / off | 500 / on | NULL / on | feito | — |
| `transcricao_operador` | off | off | on | on | B | `PUT conexao.transcrever_audio_sempre` (402) + `worker` gancho de transcrição (degrada) + `POST /atendimentos/{id}/mensagens/{mid}/transcrever` (402) |
| `documentos_cliente` | off | on | on | on | B | `worker/media.py::preprocess_incoming_message` → bloco `[Arquivo recebido: … — não lido: recurso indisponível no plano]` |
| `imagem_cliente` | off | on | on | on | B | `preprocess_incoming_message` (visão) — mesmo bloco; áudio do cliente continua liberado no Free |
| `fewshot` | off | off | on | on | B | `PUT agente` (402 ao ligar) + worker (não injeta exemplos) |
| `catalogo_completo` | off | off | on | on | B | `GET /modelos-llm/catalogo` devolve só `curado=true` quando off (a tela já cai no curado) |
| `disparador` | **off** (hoje `true` no seed — corrigir) | off | on | on | C1 | rotas `/api/campanhas*`, `/api/disparador*`, `/api/captura*` + menu |
| `mcp` | off | off | off | on | **adiada** (dono 20/09: "não vamos mexer agora com MCP") | chave semeada, sem gate no código |
| `rbac` | off | off | on | on | C1 | `POST/PUT /api/perfis` (perfis system continuam) |
| `white_label` | off | off | off | on | C1 | `PUT /api/empresas/{id}` (campos `logo_path/nome_exibicao/cor_*`) + `POST …/logo` |
| `menu_moderno` | off | off | on | on | C1 | `PUT menu_chatbot` com `menu_moderno=true` |
| `webhooks` | off | off | on | on | C1 | `POST/PUT /api/hooks*` (os existentes continuam disparando; grandfathering) |
| `waba` | off | off | on | on | C1 | `POST /api/conexoes` com `provider='waba'` + Embedded Signup |
| `departamentos_max` | 1 | 2 | 10 | NULL | C2 | `POST /api/departamentos` (`require_plano_limit("departamentos")`) |
| `workflows_max` | 0 | 0 | 3 | NULL | C2 | `POST /api/workflows` |
| `menus_max` | 1 | NULL | NULL | NULL | C2 | `POST /api/menus` |
| `retencao_max_dias` | 30 | 90 | 365 | NULL | C2 | `PUT empresa/agente` valida `retencao_dias ≤ teto` (402); histórico/export respeitam a retenção que já existe |
| `auditoria_dias` | 30 | 90 | NULL | NULL | C2 | `GET /api/audit*` filtra `created_at ≥ now() − dias` |
| `csat` | off | on | on | on | C2 | `PUT empresa csat_*` (402) + `trigger_csat_se_ativo` (não dispara) |
| `resumo_diario` | off | on | on | on | C2 | `PUT empresa resumo_diario_ativo` (402) + `shared/resumo_diario.py` (pula) |
| `bateria_testes` | off | on | on | on | C2 | `POST /agentes/{slug}/testar-bateria` (402); `/testar` simples continua |
| `observabilidade` | off | off | on | on | C2 | `/api/queue*`, `/api/traces*` (402) + menu |
| `qualidade_ia` | off | off | on | on | C2 | `/api/rag/qualidade*`, sandbox, Allure (402) + menu |

Fora do plano (plataforma, superadmin): catálogo OpenRouter, Saúde de IA, feature flags (`/settings/feature-flags` passa a `requiresSuperadmin` na C1), reCAPTCHA, Google SSO. Ferramentas do agente **não** ganham chave própria: cada uma segue o gate do recurso que usa (calendar, KB, mídia). Anti-ban do disparo é proteção, não feature.

## 4. Padrão de implementação (código que já existe + o que falta)

### 4.1 Leitura (`shared/plano_limits.py`)
- `PlanoInfo` ganha `limite_agentes` (mig 189) em `limite_de`/`passou_limite`, e `get_plano_info` passa a **mesclar** `feature_flag` da empresa: toda flag ativa com `key LIKE 'plano.%'` sobrepõe `features[<key sem prefixo>]` — e as chaves `plano.limite_*` sobrepõem as colunas numéricas. Uma query a mais dentro do mesmo cache de 30 s. `clear_plano_cache(empresa_id)` também é chamado por `upsert_flag`/`delete_flag`.
- Helper novo `limite_numerico(chave) -> int | None` para as chaves de `features` que são teto (`departamentos_max`, …): ausente = **0/off** (errar para o lado barato, como `contexto_max`).

### 4.2 Rotas (`server/dependencies_plano.py`)
- `require_plano_limit(recurso)` aceita também `"agentes"`, `"departamentos"`, `"workflows"`, `"menus"`; os contadores novos entram em `_COUNTERS` (`count_departamentos`, `count_workflows`, `count_menus`). O payload 402 não muda (`quota_exceeded`).
- `require_plano_feature` / `assert_plano_feature` não mudam. Regra de escolha continua: empresa do header → `Depends`; empresa do path → `assert_`.

### 4.3 Worker (degradar, nunca falhar)
- Helper único `shared/plano_gate.py::plano_libera(pool, empresa_id, chave) -> bool` (try/except → `True` com log `plano_ilegivel`, como o loader faz com `contexto_max`: plano ilegível não cala o agente).
- Markers novos em `MARKERS_INTERNOS` (`worker/processor.py`) com chip em `aviso-ia.tsx`: `[limite de atendimentos do plano — IA pausada]` (A). Recursos de mídia não geram marker: o agente recebe o bloco `[Arquivo recebido … — não lido]` e responde com as próprias palavras (contrato da mig 164).

### 4.4 Painel
- `layout.tsx::resolveEmpresaUI` (já resolve a empresa ativa para o white-label) passa `plano{slug, nome, features, limites, upgrade_sugerido}` ao `AppShell` → contexto `usePlano()`.
- `nav-catalog.ts` ganha `feature?: string` ao lado de `requires:`; item com feature off renderiza com `Lock` e `href="/billing?feature=<chave>"` (não some).
- Toggles gateados (transcrição da conexão, resumo diário, CSAT, white-label, menu moderno, few-shot, voz) usam o mesmo `aria-disabled` + toast do seletor de modelos (`seletor-modelo.tsx`, PR #163). Playwright: `click({ force: true })`.
- `api-error-shared.ts` já traduz 402; `billing-page-client.tsx` troca a lista de marketing pelas chaves reais da §3 (D).

### 4.5 Testes (contrato E2E do repo)
Cada leva ganha `tests/integration/test_plano_<leva>_endpoints.py` no molde de `test_aba_endpoints.py`: **TestSmoke** (endpoint existe + 401 sem token) e **TestE2E** (`docker_demo`): empresa fixture no plano Pro + `empresa_free_id` (mesmo desenho de `test_catalogo_modelos_endpoints.py`); cada gate testa 402 no Free, 200 no Pro e o **grandfathering** (flag `plano.<chave>` na empresa Free → 200). Worker: unit da função pura de degradação. Suite verde + captura do cadeado no dev = pré-condição do merge.

## 5. Levas — o que cada PR entrega

Antes de **cada** leva: rodar em produção (`ssh opc@… psql`) a consulta de uso da leva e cadastrar as flags `plano.*` de grandfathering **antes** do merge (a mig da leva pode semear as flags, se a lista for conhecida).

### Leva A — limites que já existem + teto de IA (`feat/plano-leva-a-limites`)
- **mig 189 `plano_limite_agentes.sql`**: `plano.limite_agentes INT` + seed 1/1/5/NULL.
- `require_plano_limit("usuarios")` em `POST /api/usuarios` **e** no legado `POST /api/empresas/{id}/membros` (aqui via `assert_` + contagem, porque a empresa vem do path); `("documentos_kb")` em `POST /api/base-conhecimento/upload` (e no endpoint de criação por texto, se existir); `("agentes")` em `POST /api/v1/agentes`.
- **Atendimentos/mês (D5)**: no worker, antes de invocar o agente (depois de whitelist/modo manual/menu, no mesmo ponto do `ia_budget_block`), `count_atendimentos_mes ≥ limite` → marker + chip; 80 % → `empresa.plano_alerta_atendimentos_em` (coluna na mig 189) para avisar UMA vez por mês pelo caminho do resumo diário; banner no `/atendimento` quando `percentual ≥ 80`. Cache do contador 60 s por empresa (não é um COUNT por mensagem).
- **Teto de IA (D4)**: `upsert_budget_endpoint` valida contra `plano.limite_orcamento_ia_usd` (402 `feature_unavailable`, `feature="orcamento_ia"`, mensagem com o teto); `acrescentar_consumo` herda `LEAST(limite anterior, teto do plano)` ao criar o mês; `GET /ia-budget` devolve `teto_plano_usd` para o form mostrar.
- Consulta de uso ANTES: usuários/agentes/KB por empresa vs limite do plano; `ia_budget` do mês corrente vs `limite_orcamento_ia_usd` (a 1018 tem ~US$ 104/mês de consumo com teto de plano US$ 100: **cadastrar `plano.limite_orcamento_ia_usd` = valor atual dela** antes do merge, ou a linha de outubro nasce menor).
- Docs: `CLAUDE.md` (mig 189 + parágrafo da leva), `docs/PLANOS_RECURSOS.md` §2 (mover os itens para "gateado"), §9 desta ADR.

### Leva B — custo de LLM por mensagem (`feat/plano-leva-b-llm`)
- **mig 190 `plano_features_llm.sql`**: semeia `transcricao_operador`, `documentos_cliente`, `imagem_cliente`, `fewshot`, `catalogo_completo` (§3).
- Gates da §3 (rota 402 + worker degrada). `preprocess_incoming_message` recebe o `PlanoInfo` (ou lê pelo pool) e devolve o bloco de arquivo não lido com motivo "recurso indisponível no plano" — **sem retry** (é recusa permanente, mesmo contrato de `UnsupportedFileTypeError`).
- Consulta ANTES: conexões com `transcrever_audio_sempre`, agentes com few-shot ligado, `aceita_imagem/documento` por plano.

### Leva C1 — módulos (`feat/plano-leva-c1-modulos`)
- **mig 191**: `disparador` Free → `false`; semeia `webhooks`, `waba`. `mcp`/`rbac`/`white_label`/`menu_moderno` já existem.
- Gates da §3; `/settings/feature-flags` → `requiresSuperadmin`.
- Consulta ANTES: quem tem campanhas, MCP, perfis customizados, white-label, webhooks, conexão WABA — por plano.

### Leva C2 — quantidades e retenção (`feat/plano-leva-c2-quantidades`)
- **mig 192**: semeia `departamentos_max`, `workflows_max`, `menus_max`, `retencao_max_dias`, `auditoria_dias`, `csat`, `resumo_diario`, `bateria_testes`, `observabilidade`, `qualidade_ia`.
- Contadores novos + gates da §3. `retencao_max_dias` valida no PUT; não apaga nada retroativamente (a retenção que já roda continua a mesma).
- Consulta ANTES: departamentos/workflows/menus por empresa; `retencao_dias` configurado; CSAT e resumo ligados.

### Leva D — painel (`feat/plano-leva-d-painel`)
- `usePlano()` + `nav-catalog.feature` + cadeados nas telas de toggle + `/billing` com as chaves reais e comparação de planos (dados do `GET /api/billing/planos`, que já existe, sem texto de marketing). Capturas claro/escuro, 1440/390. `scripts/ui_metrics.sh --check` não sobe.

### Leva E — vigência do plano e rebaixamento (`feat/plano-leva-e-vigencia`) — pré-requisito dos gateways
- **mig 193 `plano_vigencia.sql`** (como ficou, 21/09): `empresa.plano_valido_ate` **DATE** ("válido até o dia X, inclusive" — DATE em vez de TIMESTAMPTZ para não haver dúvida de fuso; NULL = sem vencimento, estado de todas as empresas hoje), `plano_aviso_vencimento_etapa/_ref/_em` (claim por etapa amarrado à data), `transacao.periodo_inicio/periodo_fim`. As colunas `expira_em/checkout_url/pix_*` /`gateway_status` e as de `billing_event_log` da versão inicial **não entram**: com planos hospedados (D7) não há QR nem evento de gateway por transação (F.1, se vier, cria o que precisar). CHECK de `transacao.gateway` não existe (TEXT livre) — manter; valores: `mercadopago | infinitepay | manual`.
- `shared/plano_vigencia.py::processar_vigencias` (worker, a cada 30 min, idempotente): D-7/D-3/D0 uma vez por etapa (WhatsApp do telefone do resumo diário + aviso ao superadmin pelo canal dos alertas de IA + banner no painel via `resumo_para_painel`), só em horário comercial local (08–20h); vencida há mais de 5 dias → `plano='free'` num `UPDATE … RETURNING` condicional, `audit_log`, `clear_plano_cache`, aviso aos dois lados. `PUT /api/empresas/{id}/vigencia` (superadmin) fixa ou limpa a data (cortesia) e zera o claim.
- **E.1 — textos (para aprovação do dono; em `plano_vigencia.py::texto_aviso_cliente/plataforma`)**: D-7 "Olá! O plano *Pro* da *{empresa}* no Chat Nexus vence em 7 dias ({data}). Para continuar com todos os recursos, renove até lá — em *Plano e cobrança* no painel ou falando com a nossa equipe." · D-3 "Lembrete: o plano *Pro* da *{empresa}* no Chat Nexus vence em 3 dias ({data}). Renove em *Plano e cobrança* no painel ou fale com a nossa equipe para não perder os recursos do plano." · D0 "O plano *Pro* da *{empresa}* no Chat Nexus vence hoje ({data}). Você tem até {data+5} para renovar — depois disso a conta volta ao plano Free: os atendimentos continuam, mas os recursos do Pro ficam pausados." · Rebaixamento "O plano *Pro* da *{empresa}* no Chat Nexus venceu em {data} e não foi renovado: a conta passou para o plano Free. Os atendimentos continuam normalmente; para voltar ao Pro, renove em *Plano e cobrança* no painel ou fale com a nossa equipe." · Superadmin: "⚠️ Plano a vencer — {empresa} (id N, Pro) vence em 3 dias ({data}). Registre o pagamento em Empresas → {empresa} para estender a vigência." / "⬇️ Plano rebaixado — {empresa} (id N) passou de Pro para Free: venceu em {data} e não houve pagamento em 5 dias."
- Reprecificação (D10) entra como migration de dados quando o dono fixar o número.

### Leva F — Cobrança por planos hospedados (`feat/billing-planos-hospedados`) — substitui as antigas F/G/H
- **mig 194 `plano_links_gateway.sql`**: `plano.link_mercadopago TEXT`, `plano.link_infinitepay TEXT` (NULL = plano sem venda self-service, ex.: Enterprise e Free). É dado: o dono cola os links criados nos painéis dos gateways (tela de superadmin em `/companies`/planos ou direto por migration).
- **Registrar pagamento (superadmin)**: `POST /api/empresas/{id}/pagamentos` `{plano_slug, gateway: mercadopago|infinitepay|manual, gateway_id?, valor_brl, periodo_inicio, periodo_fim, observacao?}` → `transacao` (`status='pago'`, `pago_em=now()`), `empresa.plano`/`plano_id` (upgrade se mudou), `plano_valido_ate = max(now, plano_valido_ate) + período`, `clear_plano_cache`, `audit_log`, WhatsApp de confirmação (caminho do resumo diário). Idempotência por `(gateway, gateway_id)` quando informado. `GET /api/empresas/{id}/pagamentos` lista.
- **Painel**: `/companies/[id]` ganha o bloco "Plano e vigência" (plano atual, `plano_valido_ate`, histórico, botão "Registrar pagamento" com formulário); `/billing` (cliente) mostra o plano atual, a vigência, os links do plano escolhido — **InfinitePay em destaque como "Recomendado" (D12), Mercado Pago como alternativa** —, o histórico de transações e os banners de vencimento (leva E). Sem QR, sem polling.
- **F.1 (opcional, depois de F em produção)**: webhook `POST /webhook/pagamento/mercadopago` para os tópicos de assinatura, validando `x-signature` + `GET /preapproval/{id}` antes de chamar o mesmo `registrar_pagamento` — mesma função, origem `mercadopago-webhook`.
- Remoção do Asaas (rotas, `shared/asaas.py`, tela de Integrações) em PR própria depois de F em produção ≥ 1 ciclo de cobrança.

## 6. Gateways — o que cada um oferece (lido nos sites/portais em 20/09/2026)

### 6.0 Planos hospedados (o que a leva F usa)
- **Mercado Pago → Ferramentas para vender → Assinaturas**: cria-se o plano (nome, valor, frequência semanal/mensal/anual) no app/site e sai um link; a cobrança recorre com retentativas automáticas. **Meios: cartão de crédito ou saldo em conta Mercado Pago** (Pix e boleto não entram na assinatura). Status no painel do MP; webhooks dos tópicos `subscription_preapproval`/`subscription_authorized_payment` só com integração (F.1).
- **InfinitePay → Gestão de Cobrança → Cobrança Recorrente**: cadastra-se o cliente e o plano no app/conta web; **cartão = cobrança automática todo mês; Pix = lembrete automático por WhatsApp na data, o cliente paga a cada ciclo** (Pix taxa zero, cartão até 12×). Status no app; **sem API/webhook documentado** para a recorrência.
- Consequência: o Nexus não sabe sozinho quem pagou → registro manual (D7/D8). Com 8 empresas, é conciliação de minutos por mês.

### 6.3 Referência — integração por API (versão inicial da ADR; NÃO implementar salvo decisão nova)
Mantida para o caso de o volume justificar voltar: as especificações abaixo foram lidas nos portais e continuam válidas como ponto de partida.

#### Mercado Pago — Orders API (Pix)

- Criar: `POST https://api.mercadopago.com/v1/orders` · headers `Authorization: Bearer <ACCESS_TOKEN>`, `X-Idempotency-Key: <uuid4>` (= `transacao.id` + tentativa), `Content-Type: application/json`.
- Corpo: `{"type":"online","total_amount":"497.00","external_reference":"<transacao.id>","processing_mode":"automatic","transactions":{"payments":[{"amount":"497.00","payment_method":{"id":"pix","type":"bank_transfer"},"expiration_time":"PT24H"}]},"payer":{"email":"<email do admin>"}}` — `expiration_time` ISO 8601 entre 30 min e 30 dias (usar 24 h).
- Resposta: `id` ("ORD…"), `status` (`action_required` + `status_detail: waiting_transfer` enquanto aguarda), `transactions.payments[0].payment_method.{qr_code (copia-e-cola), qr_code_base64, ticket_url}`.
- Consultar: `GET /v1/orders/{id}` → pago quando `status = "processed"` (`payments[0].status = "processed"`). Só isto ativa o plano.
- Webhook (tópico **Order**, configurado em "Suas integrações → Webhooks"): headers `x-signature: ts=<ts>,v1=<hmac>` e `x-request-id`; query `data.id`; corpo `{action, type, data.id, live_mode}`. Validar `HMAC-SHA256(secret, "id:{data.id};request-id:{x-request-id};ts:{ts};")` = `v1` (comparação em tempo constante; rejeitar `ts` com mais de 5 min). Responder 200 em < 22 s (senão reenvia a cada 15 min, 3×) — por isso o handler só valida, grava `billing_event_log` (dedup por `x-request-id`) e agenda a consulta; a consulta + ativação rodam fora do request. `live_mode=false` só é aceito em dev.

#### InfinitePay — Checkout Integrado (Pix ou cartão)
- Criar link: `POST https://api.checkout.infinitepay.io/links` — **sem token**; a conta é o `handle` (InfiniteTag sem `$`). Corpo: `{"handle":"<handle>","order_nsu":"<transacao.id>","redirect_url":"https://chat.vsanexus.com/billing?ok=1","webhook_url":"https://api.vsanexus.com/webhook/pagamento/infinitepay?token=<segredo>","items":[{"quantity":1,"price":49700,"description":"Chat Nexus — plano Pro — set/2026"}],"customer":{"name":…,"email":…,"phone_number":…}}` — **preço em centavos**. Resposta traz a `url` do checkout (não há QR na API: o cliente abre o link e escolhe Pix ou cartão; `checkout_url` na `transacao`, `pix_*` ficam NULL).
- Webhook (POST na `webhook_url`, **não assinado**): `{invoice_slug, amount, paid_amount, installments, capture_method: "pix"|"credit_card", transaction_nsu, order_nsu, receipt_url, items}`. Responder 200. Handler: token da query bate? → grava `billing_event_log` (dedup `transaction_nsu`) → **`POST https://api.checkout.infinitepay.io/payment_check`** com `{handle, order_nsu, transaction_nsu, slug: invoice_slug}` → `{"success":true,"paid":true,"paid_amount":…}` e `paid_amount ≥ amount` → ativa. Sem `paid:true` do `payment_check`, nada acontece.
- O `redirect_url` recebe `receipt_url, order_nsu, slug, capture_method, transaction_nsu` na query — só serve para a tela mostrar "estamos confirmando"; **não** ativa nada.

#### O que valeria para os dois (na versão por API)
- `transacao` é criada ANTES de chamar o gateway (`status='pendente'`, `gateway`, `periodo_*`, `expira_em`); a resposta do gateway preenche `gateway_id`/`checkout_url`/`pix_*`; falha na criação → tenta o outro gateway (D12) e, se os dois falharem, `status='falhou'` + 503 legível.
- Idempotência: uma transação `pendente` não expirada por empresa+plano é **reaproveitada** (o cliente que fecha o modal e volta vê o mesmo QR).
- Expirada sem pagamento → `status='cancelado'` pelo job diário da leva E.
- Nada de valor/segredo em log: `gateway_id`, `transacao.id` e `empresa_id` bastam para investigar (`billing_event_log.payload` guarda o corpo bruto, como hoje).

## 7. Validação e entrega (contrato dev-first, igual à ADR-004)
1. Branch por leva a partir de `origin/master`; nunca `git add -A`.
2. Dev: `docker compose -p chatnexus-dev -f docker-compose.yml -f docker-compose.override.yml up -d --build` (lembrar: `--build frontend` também reconstrói a api do checkout atual); `make check`; testes dirigidos com `timeout` (a suite completa trava local); E2E com `DATABASE_URL=…5434 INTERNAL_SERVICE_TOKEN=dev-token-change-in-production`.
3. Fumaça real: 402 na API com a empresa Free do dev e 200 na Enterprise (empresa 1 do dev); cadeado na tela com captura (claro/escuro, 1440/390); worker: mensagem pelo webhook mock (`e2e-docs` 901) com o plano rebaixado → degradação com o marker/bloco esperado e **zero erro** no log.
4. Capturas ao dono **antes** do merge; PR; CI verde; o dono roda `gh pr merge N --squash --delete-branch`; conferir o container NOVO por conteúdo (`grep` de texto visível no chunk do front; `grep` do símbolo na api/worker), mig em `_migrations`, 0 erros no worker, painel/API 200.
5. Só então a próxima leva.

## 8. Consequências e riscos
- **Regressão em cliente pagante** é o risco principal → D3 (grandfathering antes do merge) + consulta de uso obrigatória por leva + 1018 como âncora. Se a consulta mostrar uso acima do plano em cliente Pro, a exceção é cadastrada, não o gate afrouxado.
- Rebaixar para Free passa a ter efeito real (é o objetivo): o job da leva E só liga depois de A–D em produção e de o dono aprovar o texto dos avisos.
- Ativação manual depende de alguém conciliar o painel do gateway: os avisos D-7/D-3/D0 e a carência de 5 dias (leva E) protegem o cliente que pagou e ainda não foi registrado; o superadmin também recebe o aviso de vencimento das empresas pagantes (lista diária) para não deixar cliente pago cair para Free. F.1 (webhook do MP) reduz isso para o cartão.
- Pix na InfinitePay não é recorrente de verdade (lembrete + pagamento a cada ciclo): inadimplência passiva é possível; medir a renovação no 1º ciclo.
- Créditos/estimativas do seletor de modelos continuam estimativa; o que governa custo é o `ia_budget` com o teto do plano (D4).
- `tipo_memoria` buffer/summary/none (ADR-004 §7) segue fora desta ADR.

## 9. Rastreio — nenhuma etapa se perde (atualizar a cada PR)

| # | Etapa | Branch / PR | Status | Data | Evidência |
|---|---|---|---|---|---|
| 0 | Gate de contexto e modelos premium (ADR-004) | `feat/contexto-gate-plano` / #164 | ✅ em produção | 20/09/2026 | mig 188 em `_migrations`; api/worker/frontend conferidos por conteúdo |
| 0.1 | Levantamento recurso × plano | docs `f934ef8` | ✅ aprovado pelo dono | 20/09/2026 | `docs/PLANOS_RECURSOS.md` |
| 0.2 | Esta ADR | docs-only em master | ✅ escrita | 20/09/2026 | este arquivo |
| A | Limites existentes + `limite_agentes` + atendimentos/mês suave + teto de IA no `ia_budget` | `feat/plano-leva-a-limites` / **#165** (`d34c59d`) | ✅ em produção | 20/09/2026 | mig 189 em `_migrations` (183); api/worker-1/2/frontend recriados e conferidos por conteúdo (`assert_plano_limit`, `plano_gate.py`, "IA pausada pelo plano" no chunk); 0 erros; painel/API 200; 6 E2E + fumaça do worker no dev |
| A.0 | Consulta de uso em produção + flags de grandfathering | — | ✅ | 20/09/2026 | ninguém acima de usuários/KB/atendimentos; só a sandbox 999 (8 agentes) → flag `plano.limite_agentes=null` semeada na mig 189; `ia_budget` da 1018 = US$ 10 (consumo US$ 3,49) < teto Pro US$ 100 — sem exceção |
| B | Custo de LLM por mensagem (transcrição do operador, documentos, imagem, few-shot, catálogo completo) | `feat/plano-leva-b-llm` / **#166** (`337e91d`) | ✅ em produção | 20/09/2026 | mig 190 em `_migrations` (184); api/worker-1/2/frontend recriados e conferidos por conteúdo (`transcricao_operador`, `plano_libera`, `plano_bloqueado`, "mostra os modelos recomendados"); 0 erros; painel/API 200 |
| B.0 | Consulta de uso + grandfathering | — | ✅ | 20/09/2026 | ninguém com `transcrever_audio_sempre`; documentos/imagem/few-shot em uso só na 1 (Ent) e 1018 (Pro); modelo fora do curado só na 1; sandbox 999 → flags `plano.documentos_cliente/imagem_cliente/fewshot` na mig 190 |
| C1 | Módulos (disparador, rbac, white_label, menu_moderno, webhooks, waba — **MCP adiado**) + feature-flags superadmin | `feat/plano-leva-c1-modulos` / **#167** (`d302bd1`) | ✅ em produção | 20/09/2026 | mig 191 em `_migrations` (185); api/worker-1/2/frontend recriados e conferidos por conteúdo; flags white_label das 4 empresas; 0 erros; painel/API 200 |
| C1.0 | Consulta de uso + grandfathering | — | ✅ | 20/09/2026 | campanhas/MCP/hooks/WABA = 0 em todas; perfil custom só na 1018 (Pro, tem rbac); menu moderno só na 1; **white-label fora da matriz em 1012 (Free), 1013/1016/1018 (Pro) → flags `plano.white_label` na mig 191** |
| C2 | Quantidades e retenção (departamentos, workflows, menus, retenção, auditoria, csat, resumo, bateria, observabilidade, qualidade) | `feat/plano-leva-c2-quantidades` / **#168** (`fdac9e3`) | ✅ em produção | 20/09/2026 | mig 192 em `_migrations` (186); api/worker-1/2 recriados 21:48 e conferidos por conteúdo (`limite_numerico`, `_ROTULO_FEATURE`); flag `plano.departamentos_max` da 999; front não mudou (sem arquivo do front na PR); 0 erros; API/painel 200; `test_plano_leva_c2_endpoints.py` (13 verdes); mensagens de 402 reescritas para usuário final (regra do dono) |
| C2.0 | Consulta de uso + grandfathering | — | ✅ | 20/09/2026 | só a sandbox 999 fora da matriz (7 departamentos) → flag `plano.departamentos_max`; workflows só na 1 (Ent); retenção NULL; CSAT/resumo desligados em todas |
| C2.1 | **Correção**: gate de retenção só quando o valor muda (salvar o cadastro da empresa com retenção NULL dava 402 em Free/Pessoal/Pro — regressão da C2 em produção por ~4 h) | `fix/plano-retencao-so-na-mudanca` / **#169** (`6447a91`) | ✅ em produção | 21/09/2026 | api recriada 01:35 e conferida por conteúdo (`atual=` em `empresa_admin.py` e `agente.py`); 0 erros; E2E da C2 cobre save sem mudança (200) e volta para 0 (402) |
| D | Painel: `usePlano`, cadeados no menu e nas telas, `/billing` com as chaves reais | `feat/plano-leva-d-painel` / **#170** (`d7c0d91`) | ✅ em produção | 21/09/2026 | api/worker-1/2/frontend recriados 01:50 e conferidos por conteúdo (`resumo_para_painel`, rota `/plano`, "Comparação de planos" e "Não está no seu plano" no chunk); 0 erros; API/painel 200; sem migração; `GET /api/empresas/{id}/plano`; cadeados no menu (sidebar + ⌘K) e em 10 interruptores; `/billing` com tabela pelas chaves reais e destaque de `?feature=`; `test_plano_leva_d_endpoints.py` (4 E2E verdes); capturas claro/escuro 1440/390 |
| D10 | Reprecificação do Pro (número do dono → migration de dados) | — | ⬜ decisão do dono | | |
| E | Vigência: `plano_valido_ate`, avisos D-7/D-3/D0 (cliente + superadmin), carência 5 dias, rebaixamento automático, `transacao.periodo_*` | `feat/plano-leva-e-vigencia` / **#171** (`42d28c7`) | ✅ em produção | 21/09/2026 | mig 193 em `_migrations` (187); api/worker-1/2/frontend recriados 02:38 e conferidos por conteúdo (`plano_vigencia.py`, `set_vigencia_endpoint`, `_plano_vigencia_loop`, banner no chunk); 0 empresas com data; 0 erros; API/painel 200; mig 193 (DATE); `test_plano_vigencia.py` (6 unit) + `test_plano_leva_e_endpoints.py` (5 E2E: 403, dias no painel, aviso uma vez por etapa + janela, renovação zera + rebaixamento com auditoria, cortesia); banner e seção do superadmin validados pela tela (claro/escuro, 1440/390) |
| E.1 | Texto dos avisos de vencimento aprovado pelo dono | — | ⬜ dono (textos na seção "Leva E" acima) | | mudar texto = mudar `texto_aviso_*` em `plano_vigencia.py` (sem migration) |
| F | Cobrança por planos hospedados: links por plano, "Registrar pagamento" (superadmin), `/billing` com links + vigência + histórico | `feat/billing-planos-hospedados` / **#172** (`396cc44`) | ✅ em produção | 21/09/2026 | api/worker-1/2/frontend recriados 03:10 UTC e conferidos por conteúdo (`plano_pagamento.py` nos 3 Python, "Assinar ou renovar" no chunk); `_migrations` = 188 com `194_plano_links_gateway.sql`; `plano`: pessoal/pro/enterprise com os 2 links, free sem; fumaça como superadmin: `GET /api/billing/planos` 200 (links + `limite_agentes` 1/1/5/∞), `GET /api/empresas/1/pagamentos` 200 (histórico vazio, sugestão 20/09→19/10), `GET …/plano` 200. No dev: mig 194 (links semeados); `test_plano_pagamento.py` (4 unit) + `test_plano_leva_f_endpoints.py` (5 E2E: 403, links + catálogo, registrar sobe o plano e estende a vigência com auditoria, 409/400, renovação zera o aviso); fumaça pela tela: registro → Pessoal até 19/10 → "Renovar" no /billing (claro/escuro, 1440/390) |
| F.0 | Dono cria os planos na InfinitePay (Cobrança Recorrente — padrão) e no Mercado Pago (Assinaturas — alternativa), passa os links, confere as taxas de cartão dos dois e fixa o preço do Pro (D10) | — | ✅ links entregues 21/09 (Pessoal R$97 · Pro R$299 · Enterprise R$1.499, nos dois gateways — semeados na mig 194); taxas de cartão e D10 seguem com o dono | 21/09/2026 | InfinitePay `invoice.infinitepay.io/plans/vinicius-souza-z92/…` · MP `mpago.la/…` → checkout de assinatura (`preapproval_plan_id`) |
| F.0.1 | Links da InfinitePay migrados pelo dono para a conta `vsa-tecnologia` (Pessoal com id novo `y3lpTMjINF`; Pro/Enterprise mesmo id) — aplicados em produção e no dev por `PUT /api/billing/planos/{slug}/links` (MP preservado); **mig 195** corrige o seed para instalação nova (só substitui o prefixo antigo; link posto à mão fica) | `fix/plano-links-infinitepay-seed` | ⏳ PR | 21/09/2026 | validação: transação revertida no dev (seed antigo → trocado; link à mão → intocado); no dev/prod a migration é no-op |
| F.1 | (opcional) Webhook de assinatura do Mercado Pago estendendo a vigência (`x-signature` + `GET /preapproval/{id}`) | `feat/billing-webhook-mercadopago` | ⬜ | | |
| F.2 | 1º ciclo real de cobrança acompanhado (renovação, aviso, rebaixamento) | — | ⬜ | | |
| ~~G~~ | ~~InfinitePay por API (Checkout Integrado)~~ | — | ✖ descartada 20/09 | | planos hospedados (D7) |
| ~~H~~ | ~~Checkout Pix no `/billing` (QR, polling)~~ | — | ✖ descartada 20/09 | | planos hospedados (D7) |
| I | Remoção do Asaas (após F ≥ 1 ciclo em produção) | `chore/remover-asaas` | ⬜ | | |

Legenda: ✅ em produção conferido por conteúdo · 🟢 mergeado, aguardando conferência · 🔍 no dev, aguardando o dono · ⏳ em andamento · ⬜ não iniciado.
