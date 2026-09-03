# Prospecção Enterprise — Fase 0: descoberta e relatório de gaps

**Data:** 2026-09-01 · **Branch:** `master` (`4297332`) · **Autor:** Claude (Opus 5)
**Insumo:** `docs/ADR/prospeccao_enterprise.md` (spec de 8 fases)
**Status:** relatório entregue — **nenhuma linha de código de produção alterada**. Aguarda OK do dono antes da Fase 1.

---

## 1. Método

Levantamento feito contra três fontes, nesta ordem de autoridade: **banco de dev**
(`localhost:5434`, migrations 001→181 aplicadas) > **código-fonte** > documentação.
Onde o spec e o código divergiram, **o código venceu** e a divergência está na §3.

Baseline de testes rodado localmente com `-m "not docker_demo and not twilio_real"`
(a suíte completa trava em máquina local — gotcha conhecido do CLAUDE.md).

---

## 2. Inventário confirmado (nomes reais)

### 2.1 Motor de disparo

| Peça | Arquivo | Linhas | Fato |
|---|---|---|---|
| Loop de envio | `shared/campanha.py::_dispatch_loop` | 773–1105 | roda **na API**, via `asyncio.create_task` |
| Agendador | `shared/campanha.py::run_scheduled_poller` | 1208 | task no **lifespan da API** (`server/main.py:224`) |
| Claim de agendadas | `claim_scheduled_due` | 1179 | `FOR UPDATE SKIP LOCKED` ✓ (correto) |
| Retry de envio | `_send_com_retry` | 736 | 3 tentativas, backoff 1,5s·n, **em memória** |
| Kill-switch | `_should_kill_switch` | 717 | só taxa de falha, amostra mín. 20 |
| Rodízio de números | `_proxima_conexao` | 757 | round-robin sobre `conexao_ids` (mig 130) |
| Teto/aquecimento | `shared/conexao_quota.py` | 112 | `WARMUP_BASE=20`, `FACTOR=1.8`, `DIAS=8` — **hard-coded** |
| Reagendar por teto | `_reagendar_warmup` | 1130 | vira `scheduled` p/ meia-noite seguinte ✓ |

Disparo é acionado em 2 pontos: `routes/campanha.py:392` (painel) e
`routes/disparador.py:262` (extensão/WABA template).

### 2.2 Schema real (verificado no banco, não no spec)

**`campanha_destinatario` — 9 colunas, e nada além disso:**
```
id, campanha_id, telefone, cliente_id, status, mensagem_id_externo, erro, sent_at, variaveis
CHECK status IN ('pendente','enviado','falhou')
UNIQUE (campanha_id, telefone) · INDEX parcial WHERE status='pendente'
```

**`campanha` — 34 colunas:**
```
status IN ('draft','scheduled','running','done','partial','aborted')
tipo   IN ('broadcast','transactional','reativacao')
origem_envio IN ('backend','extensao')
```

**`conexao`, colunas anti-ban existentes:** apenas `daily_send_cap` e `warmup_started_at`.
Não existe `quality_rating`, `messaging_limit_tier`, `throughput_level`, `risco_score`.

**Tabelas do §4 do spec que NÃO existem:** `funil`, `funil_etapa`, `funil_conversa`,
`funil_conversa_log`, `funil_regra`, `lista_contato`, `lista_dinamica`,
`contato_consentimento`, `politica_envio`, `conexao_saude`, `campanha_variante`,
`campanha_evento`, `tarifa_meta`, `importacao_lote`, `importacao_linha`,
`grupo_convite`, `grupo_adicao_lote`. **17 tabelas novas** — o spec não subestimou.

**Existem:** `campanha`, `campanha_destinatario`, `conexao`, `conexao_envio_diario`,
`grupo`, `grupo_membro`, `contato_capturado`, `captura_lote`, `disparador_opt_out`,
`empresa_api_key`, `waba_template`, `cliente`.

### 2.3 Frontend

`app/campanhas/{page,campanhas-page-client}.tsx`, `app/campanhas/[id]/campanha-detail-client.tsx`,
`app/disparador/{contatos,grupos,api-keys}/`. Não existe `/funil` nem `/disparador/listas`.
Polling confirmado: `campanha-detail-client.tsx:135` (`setInterval`).

Navegação (`nav-catalog.ts:84-87`): 4 itens sob "Prospecção", gated por
`disparador.disparar` / `disparador.capturar` / `disparador.api_key.manage`.

### 2.4 Endpoints atuais de campanha (12)

`GET ""`, `GET /{id}`, `GET /{id}/destinatarios`, `POST ""`, `PATCH /{id}`,
`POST /{id}/destinatarios`, `POST /{id}/clonar`, `DELETE /{id}/destinatarios/{did}`,
`POST /preview-crm`, `POST /upload-media`, `POST /{id}/dispatch`, `POST /{id}/abort`.

**Não existe:** `pause`, `resume`, `cancel`, `stream`, `relatorio`, `custo`, `variantes`, `teste`.

---

## 3. Divergências entre o spec e o código (o código vence)

| # | Spec diz | Realidade | Impacto no plano |
|---|---|---|---|
| D1 | "última migration hoje: 175" | **181** (`181_openrouter_evento.sql`); 174 arquivos, gaps cronológicos | numerar a partir de **182** |
| D2 | "próximo ADR: ADR-017" | ✓ correto (existem 001–016 em `docs/obsidian-vault/03-Resources/ADRs/`) | manter |
| D3 | "toda tabela nova com `empresa_id` recebe RLS" — implica que o módulo já é coberto | **`campanha_destinatario` NÃO tem `empresa_id` e NÃO tem RLS** (`relrowsecurity=f`) | ver §4.1 — vira item de Fase 2 |
| D4 | Fase 3: "parsear `statuses[]` em `integrations/waba/webhook.py`" | O webhook **descarta status de propósito** (`webhook.py:76`: "Ignora updates de status") | não é "estender", é **implementar** |
| D5 | Fase 3: "consumir `MESSAGES_UPDATE` já entregue ao `evolution_webhook.py`" | **Zero ocorrências** de `MESSAGES_UPDATE`/`DELIVERY_ACK`/`SERVER_ACK` no arquivo | idem — do zero |
| D6 | Fase 4: "mover defaults hard-coded de `conexao_quota.py`" | Confirmado: `WARMUP_BASE/FACTOR/DIAS` são constantes de módulo | ✓ spec certo |
| D7 | Fase 7: "gating por plano (`plano_limits.py`, mig 122/134)" | `plano_limits.py` **não menciona disparo**; o gating vive em `shared/disparo.py::checar_limite_plano_disparo` e lê `features['disparador_max_contatos']` | mexer em `disparo.py`, não em `plano_limits.py` |
| D8 | Fase 3: "reutilize a infraestrutura SSE do app Android" | ✓ existe: `GET /api/atendimentos/events` (`atendimento.py:527`), canal PG `atendimento_event` | reuso confirmado, baixo risco |
| D9 | "docs/DISPARADOR.md: o resolver de disparo filtra opt-out" | Filtra **só no preview**; o caminho de criação/disparo não filtra | ver §4.2 — **bug de produção** |
| D10 | Fase 5 assume `grupo`/`grupo_membro` como base | ✓ existem (mig 119) e **têm RLS** | ✓ |

---

## 4. Achados críticos (não estavam no spec, ou estavam subdimensionados)

### 4.1 🔴 `campanha_destinatario` está fora da RLS

```
campanha              | rls=t force=t
campanha_destinatario | rls=f force=f   ← única tabela do módulo sem RLS
```

A mig 101 é um `DO` block dinâmico sobre `information_schema.columns WHERE
column_name='empresa_id'` — a tabela ficou de fora porque só tem FK para `campanha`.
A própria mig 101 documenta essa classe como dívida ("Pra cobrir FK-indirect tables…
sprint futura precisa adicionar coluna `empresa_id`").

Hoje o isolamento entre empresas nos destinatários depende **inteiramente** de o
código sempre filtrar por `campanha_id` de uma campanha já validada. É correto no
código atual, mas é uma invariante sem rede de proteção — e a Fase 2 vai multiplicar
os call sites (claim, lease, webhook de status, worker). **Recomendo tratar como
pré-requisito da Fase 2, não como item da Fase 8.**

### 4.2 🔴 Opt-out não é aplicado no disparo por campanha

Call sites de `telefones_suprimidos()` em todo o `src/`:
- `shared/conversa_ativa.py:94` — conversa manual ✓
- `shared/disparo.py:164` — **`preview_disparo`** (informativo)

`create_campanha` (`campanha.py:267-274`) normaliza e deduplica, mas **não consulta
a lista de supressão**. `_dispatch_loop` lê `WHERE cd.status='pendente'` — também não.
Ambos os callers (`routes/campanha.py:168`, `routes/disparador.py:105,242`) passam
`telefones_brutos` direto.

Consequência: uma campanha criada pelo painel `/campanhas` **envia para quem pediu
descadastro**. O preview filtra, mas é o cliente que decide mandar a lista filtrada —
o servidor não impõe. `docs/DISPARADOR.md:108-111` afirma que o filtro existe (D9).

Isso é exposição LGPD em produção hoje, independente deste projeto. **Sugiro corrigir
como hotfix isolado (~1 dia, 1 filtro em `create_campanha` + teste), antes e fora da
Fase 1** — não é razoável deixar rodando durante 8 fases.

### 4.3 🔴 Campanha `running` órfã não tem quem retome

`claim_scheduled_due` só reivindica `status='scheduled'`. Se a API reiniciar com uma
campanha em `running`, a task morre e os destinatários ficam `pendente` **para sempre**:
nenhum poller, lease ou varredura os recupera. Não há endpoint de "reenviar pendentes"
(o próprio código admite: `routes/campanha.py:378` — *"Pra reenviar pendentes/falhos,
use endpoint dedicado (TODO)"*).

`docs/DISPARADOR.md:119-123` registra a dívida, mas subdimensiona: não é só "perde o
loop", é **estado terminal irrecuperável sem SQL manual**. É exatamente a meta G2 do spec.

### 4.4 🟠 A meta G1 (10k em <20 min) é inalcançável por 1–2 ordens de grandeza

O loop é **estritamente sequencial**: 1 destinatário por vez, `await asyncio.sleep(jitter)`
entre cada um, sem concorrência nenhuma. Com os defaults reais:

| Caminho | Intervalo | 10.000 destinatários |
|---|---|---|
| Painel (`campanhas-page-client.tsx:92`) | 3.000–8.000 ms (média 5,5 s) | **≈ 15 h 17 min** |
| Extensão/WABA (`disparador.py:249`) | `intervalo_ms=500` fixo | **≈ 83 min** |
| Meta G1 do spec | — | **< 20 min** |

Mesmo zerando o jitter, o teto é a latência serial da chamada HTTP ao provider
(~200–400 ms) → ~55–110 min. **G1 exige concorrência real (N workers em paralelo por
número, token bucket), não ajuste de parâmetro.** Isso confirma que a Fase 2 é
reescrita do motor, não refactor — e justifica a estimativa alta na §7.

### 4.5 🟠 Nenhum dado de saúde WABA é lido da Meta

`integrations/waba/client.py` expõe exatamente 3 operações: `send_message`,
`send_typing`, `download_media`. Não há leitura de `messaging_limit`, quality rating,
throughput level nem assinatura de `phone_number_quality_update`. Toda a Fase 4 na
parte oficial é greenfield.

### 4.6 🟡 Drift: o banco de dev está à frente do master

Comparação `_migrations` (dev) × `db/migrations/` (master):

```
no banco mas NÃO no master:  153_drop_twilio_provider.sql
no master mas não aplicada:  (nenhuma)
```

Esse arquivo veio da branch de remoção do Twilio, **nunca mergeada**. Efeito colateral
imediato: `conexao_provider_check` no dev aceita só `('waba','evolution')`, e
`tests/integration/test_campanha_antiban.py` insere conexões `'twilio_prod'` →
**falha no dev, passaria num banco limpo criado a partir do master**. Ver §5.

Recomendação: decidir o destino da mig 153 (mergear ou reverter no dev) antes da
Fase 2, senão todo baseline de teste do módulo fica ambíguo.

---

## 5. Baseline de testes (2026-09-01)

Unit — **42 passed**, 0 failed (61 s):
```
tests/unit/test_campanha_jitter.py · test_conexao_quota.py · test_opt_out.py
```

Integração (contra banco de dev) — **50 passed, 1 failed, 3 errors** (81 s):
```
tests/integration/test_disparo.py · test_campanha_antiban.py
tests/integration/test_captura.py · test_disparador_endpoints.py
```

As 4 quebras são **pré-existentes e têm causa única**, a do §4.6:
`CheckViolation: conexao_provider_check` ao inserir `provider='twilio_prod'`.
- `TestCampanhaAntiBanPersistencia::test_grava_pool_conexoes` (failed)
- `TestTetoDiario::{test_quota_conta_e_incrementa, test_warmup_limita_abaixo_do_manual, test_reagenda_warmup_vira_scheduled}` (errors, fixture)

Working tree limpo em `src/`, `db/` e no arquivo de teste — nada disso foi introduzido
por este levantamento.

**Cobertura de teste do módulo hoje:** anti-ban e jitter estão bem cobertos (23 testes
em `test_campanha_jitter.py`, 23 em `test_campanha_antiban.py`, 12 em `test_conexao_quota.py`).
Não há **nenhum** teste de: crash-recovery, idempotência de envio, concorrência entre
workers, parser de status de provider, RLS de `campanha_destinatario`.

---

## 6. Riscos do projeto como especificado

| # | Risco | Severidade | Mitigação sugerida |
|---|---|---|---|
| R1 | Reescrever o motor com campanhas reais rodando em produção | Alta | Feature flag `disparador_v2` por empresa (é a pergunta 1 do spec — **recomendo sim**) |
| R2 | `CHECK` de `status` bloqueia os 13 novos estados; ampliar CHECK numa tabela grande trava a tabela | Média | `ALTER … DROP CONSTRAINT` + `ADD … NOT VALID` e `VALIDATE` depois |
| R3 | 17 tabelas novas × RLS × testes de isolamento = superfície enorme | Alta | Fatiar: Fase 2 (motor) e Fase 6 (funil) são projetos independentes; não emendar |
| R4 | Migrar o poller da API pro worker muda quem detém a campanha; janela de dupla execução no deploy | Média | Lease + claim por destinatário torna dupla execução inofensiva — fazer nessa ordem |
| R5 | Spec assume paridade Chatvolt como meta; o benchmark do repo (G13, score 1,7) prioriza o funil por dependência, não por demanda medida | Média | Confirmar com o dono se há cliente pedindo funil (pergunta P2 abaixo) |
| R6 | Meta G4 (import 50k) e G1 (10k/20min) implicam carga que a instância atual nunca viu | Média | Medir `pg_stat_activity` e pool antes; a VPS é compartilhada com produção |
| R7 | Extensão Chrome "em quarentena" mas ainda é um caminho de disparo vivo (`origem_envio='extensao'`) | Média | Pergunta P4 do spec — decidir antes da Fase 2, muda o desenho do claim |

---

## 7. Plano de fases ajustado (com estimativas)

Ordem alterada em dois pontos, justificados acima. Estimativas em dias de trabalho
efetivo, assumindo o contrato dev-first (branch → dev → dono → PR → merge).

| Fase | Escopo | Est. | Mudança vs. spec |
|---|---|---|---|
| **H0** | 🔴 **Hotfix opt-out** (§4.2): filtrar supressão em `create_campanha` + teste E2E | **1 d** | **NOVA** — não esperar 8 fases |
| **H1** | 🟡 Resolver o drift da mig 153 (§4.6) para destravar o baseline | **0,5 d** | **NOVA** |
| **F2a** | 🔴 `empresa_id` + RLS em `campanha_destinatario` (§4.1) + teste de isolamento | **1,5 d** | **promovido** da Fase 8 |
| **F2b** | Motor durável no worker: claim/lease/idempotência, 13 estados, `campanha_evento`, pausar/retomar/cancelar, poller sai da API, ADR-017 | **10–14 d** | = Fase 2 do spec |
| **F3** | Status de entrega (WABA `statuses[]` + acks Evolution, **do zero** — D4/D5), `respondeu`, SSE, métricas | **5–7 d** | = Fase 3 |
| **F1** | Contatos, listas, consentimento, import 50k | **8–10 d** | **rebaixada** de 1ª para 4ª |
| **F4** | Anti-ban v2, `politica_envio`, `conexao_saude`, saúde WABA via Graph (greenfield — §4.5), spintax/variantes | **8–10 d** | = Fase 4 |
| **F7** | Templates no wizard, custo, `tarifa_meta`, gating por plano (em `disparo.py`, não `plano_limits.py` — D7) | **5–6 d** | = Fase 7 |
| **F6** | Funil/CRM + automações | **10–12 d** | = Fase 6 |
| **F5** | Grupos (Evolution + Groups API) | **7–9 d** | = Fase 5 |
| **F8** | Dashboard, relatórios, carga, runbooks, endurecimento | **5–6 d** | = Fase 8 |

**Total: ≈ 62–79 dias** de trabalho efetivo (≈ 3 a 4 meses de calendário).

### Por que essa ordem

1. **H0/H1/F2a antes de tudo.** Um bug de LGPD ativo e uma tabela sem RLS não devem
   sobreviver a um projeto de 3 meses. São 3 dias somados.
2. **Motor (F2b) e status (F3) antes de contatos (F1).** O spec põe Contatos primeiro
   porque fecha o G8 do benchmark, mas *importar 50 mil contatos para alimentar um
   motor que perde a campanha no restart* (§4.3) inverte a ordem de valor. Com F2b+F3
   prontos, cada campanha existente já fica confiável e observável — ganho imediato
   sem depender de mais nada.
3. **F5 (Grupos) por último.** É a fase de maior risco de ban e menor demanda
   confirmada, e a Groups API oficial ainda exige OBA (pergunta P3).

---

## 8. Perguntas ao dono (bloqueiam a Fase 1)

As 6 do §7 do spec continuam válidas. Estas 4 são novas, vindas dos achados:

- **P-A (§4.2):** autoriza o hotfix de opt-out (H0) já, fora do escopo do projeto,
  como correção isolada em produção? *Recomendação: sim.*
- **P-B (§4.6):** a mig `153_drop_twilio_provider.sql` deve ser **mergeada no master**
  (o dev já a aplicou) ou **revertida no dev**? O baseline do módulo depende disso.
- **P-C (§4.4):** a meta G1 (10k em <20 min) vale para o canal **oficial WABA apenas**,
  certo? No canal Evolution, respeitar anti-ban e bater 20 min são objetivos
  mutuamente exclusivos — quero deixar isso explícito na ADR-017.
- **P-D (§7):** confirma a inversão de ordem (motor antes de contatos)? É a única
  mudança estrutural que estou propondo sobre o plano do spec.

E reforço a **P1 do spec**, que considero a decisão mais importante do projeto:
feature flag `disparador_v2` por empresa, default off, com o motor antigo coexistindo
durante a migração. *Recomendação: sim* — R1 é o maior risco do projeto.

---

## 9. Decisões do dono (2026-09-02)

| # | Decisão | Consequência |
|---|---|---|
| **P-A** | **Sim** — hotfix de opt-out autorizado fora do escopo | H0 entregue (branch `fix/opt-out-no-disparo`) |
| **P-B** | **Master** — a mig 153 vai pro master | H1 entregue como remoção completa do Twilio |
| **P-C** | **Quebrar o G1** conforme a análise abaixo | substitui a meta única por três |
| **P-D** | **Sim** — motor antes de contatos | ordem do §7 confirmada |
| **P1** (do spec) | **Sim** — feature flag `disparador_v2` por empresa | motor antigo coexiste durante a migração |

### 9.1 G1 substituído por G1a / G1b / G1c

**Por que a meta original não se sustenta.** A checagem contra produção (2026-09-02)
mostrou o seguinte: `campanha` e `campanha_destinatario` estão **vazias** na base
atual (que começa em 2026-08-20, pós-incidente), enquanto a captura é usada de
verdade — 3.239 contatos capturados, 497 grupos, 6.233 membros, 11 lotes e 5
chaves da extensão em uso. O funil captura e para no último passo.

E o número "10.000" não vem de demanda: é o **tier 3 da Meta — 10 mil clientes
únicos por 24 horas**. É uma cota diária, não um alvo de rajada; transformá-la
numa janela de 20 minutos inverte o sentido do tier. Do lado da API o alvo
também não é ambicioso: a Cloud API entrega ~80 msg/s por padrão, o que faria
10 mil em ~2 minutos. O gargalo nunca foi o relógio — é o laço sequencial (§4.4).

**As três metas que substituem G1:**

- **G1a — WABA, capacidade.** O motor sustenta o ritmo que o *número* permite:
  token bucket alimentado pelo `messaging_limit` lido do Graph, concorrência N,
  sem `130429`, com backoff no primeiro sinal de saturação. *Aceite:* 10.000
  destinatários concluem **dentro da janela comercial (≤ 4 h)**, com ≥ 99 % em
  estado final em 1 h após o fim do envio.
- **G1b — Evolution, segurança. Não é meta de velocidade.** 10 mil pelo canal
  não-oficial *deve* levar dias, por desenho. *Aceite:* com relógio simulado,
  nenhuma hora excede `teto_hora`, nenhum dia excede o teto efetivo, e pausas,
  janela de envio e curva de aquecimento são respeitadas — exatamente o G6 do spec.
- **G1c — durabilidade.** É o G2 do spec e a razão real de reescrever o motor:
  reiniciar API e worker no meio de uma campanha `running` não perde nem duplica
  destinatário. Hoje isso não existe (§4.3) e nenhum poller reivindica `running`.

**O que isso muda no projeto:** a ADR-017 deixa de prometer velocidade no canal
não-oficial (onde velocidade e anti-ban são objetivos opostos) e passa a
prometer *ritmo adaptativo no oficial* + *durabilidade nos dois*. Se velocidade
fosse o objetivo único, o projeto não se justificaria em 62–79 dias.

### 9.2 Pergunta que ficou aberta — **respondida em 2026-09-03**

A pergunta era: por que 3.239 contatos capturados nunca viraram campanha? As
hipóteses eram (a) a UX do disparo trava, (b) as pessoas exportam e disparam
fora, (c) receio de ban depois do incidente da campanha 9.

**Nenhuma das três.** O dono respondeu: *"porque eu não fiz ainda a campanha"*.
O disparo nunca foi exercitado — não há usuário travado, evasão nem trauma.

Consequências para o plano:

- **A ordem acordada em §9 fica de pé.** Não entra fase corretiva de
  "captura → campanha": não há defeito medido nesse hand-off.
- **Mas o zero deixa de ser evidência.** A ausência de campanhas não valida
  nada do caminho de disparo — só significa que ele nunca rodou com dados
  reais. Todo achado sobre o dispatcher continua vindo de leitura de código,
  não de produção. O motor da F2b tem que ser construído assumindo que o
  primeiro disparo real é também o primeiro teste real.
- **O primeiro disparo de verdade vira marco.** Vale tratá-lo como evento
  observado (lote pequeno, acompanhamento ao vivo), não como uso rotineiro —
  é a primeira vez que `campanha_destinatario` sai do zero em produção.

---

## 10. Estado da entrega

- ✅ Documentos lidos, código mapeado, schema extraído do banco de dev, baseline rodado.
- ✅ Relatório entregue. **Nenhum código de produção alterado.**
- ⏸️ **Fase 1 (ou H0) aguarda o OK do dono**, conforme §2.5 do spec.
