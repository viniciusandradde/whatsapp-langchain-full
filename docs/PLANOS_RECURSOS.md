# Recursos × Plano — levantamento para planejar a liberação

- **Status:** levantamento pronto para decisão do dono (20/09/2026). Nada aqui está implementado além do que a coluna "Hoje" diz.
- **Pedido:** "Faça levantamento de todos os recursos para planejar a liberação de acordo com os planos contratados" — antes de partir para a cobrança (Mercado Pago + InfinitePay, Pix).
- **Método:** inventário do menu do painel (`frontend/src/components/nav-catalog.ts`, 43 itens), das chaves de `plano.features` semeadas nas migrations (059, 122, 134, 177, 188) e de **onde o código de fato aplica** cada gate (`require_plano_feature`, `assert_plano_feature`, `require_plano_limit`, `tem_feature`, `checar_gate_plano`). O que não aparece em código está marcado como **não aplicado** — mesmo que a migration tenha semeado a chave.

## 1. Os planos hoje (dados de produção, `plano`)

| | Free | Pessoal | Pro | Enterprise |
|---|---|---|---|---|
| Preço/mês | R$ 0 | R$ 97 | R$ 299 | R$ 1.499 |
| Usuários | 2 | 2 | 10 | ilimitado |
| Conexões (números) | 1 | 1 | 3 | ilimitado |
| Atendimentos/mês | 100 | 500 | 5.000 | ilimitado |
| Orçamento de IA (US$/mês) | 5 | 10 | 100 | 500 |
| Documentos (KB) | 5 | 20 | 100 | ilimitado |
| Empresas em produção | 2 (1012, 999-sandbox) | 0 | 5 (1000, 1013, 1016, 1017, **1018**) | 2 (1, 1024) |

Chaves em `features` hoje: `calendar`, `mcp`, `rbac`, `menu_moderno`, `disparador`, `disparador_media`, `disparador_max_contatos`, `voz`, `white_label`, `contexto_max`, `modelos_premium`.

> ⚠️ Lembrete do raio-X comercial (28/08): **o Pro a R$ 299 com teto de IA US$ 100 é margem negativa** no cliente IA-pesado (a 1018 consome ~US$ 104/mês de LLM). A liberação por plano abaixo não resolve isso — é a reprecificação (Pro → R$ 397–497 com teto US$ 25–30 + excedente) que resolve, e ela precisa vir **junto** com a cobrança.

## 2. O que já é gateado de verdade (e onde)

| Recurso | Chave | Onde aplica | Tipo |
|---|---|---|---|
| Google Calendar (conectar) | `calendar` | `routes/calendar_integration.py::oauth_init` | 402 |
| Voz do agente (ligar) | `voz` | `routes/empresa_admin.py` (PUT) + worker (`get_empresa_voz_config`) | 402 + desliga no worker |
| Disparo: teto de contatos e mídia | `disparador_max_contatos`, `disparador_media` | `shared/disparo.py` (preview + caminho HARD da extensão) | 402 |
| Número de conexões | `limite_conexoes` | `routes/conexao.py` (4 rotas de criação, `require_plano_limit("conexoes")`) | 402 |
| Tamanho do contexto do agente | `contexto_max` | PUT do agente (402) · tela (trava) · loader (rebaixa) — mig 188, PR #164 | 402 + rebaixa |
| Modelos premium (> US$ 5/Mtok) | `modelos_premium` | PUT do agente (402) · tela (trava) — mig 188, PR #164 | 402 |

Só isso. Tudo o mais abaixo é **liberado para todo plano**, inclusive o Free.

## 3. Chaves semeadas que o código IGNORA (gotcha "UI promete o que o backend ignora")

| Chave | Semeada como | Realidade |
|---|---|---|
| `mcp` | só Enterprise | `/catalog/mcp` e `mcp_server_ids` do agente funcionam em qualquer plano |
| `rbac` | Pro/Enterprise | `/settings/perfis` e perfis customizados funcionam em qualquer plano |
| `menu_moderno` | Pro/Enterprise | `menu_chatbot.menu_moderno` (botões nativos) salva em qualquer plano |
| `disparador` | Free `true`, Pessoal `false`, Pro/Ent `true` | módulo inteiro (campanhas, contatos, grupos, extensão) abre para todos; só o teto/mídia é aplicado |
| `white_label` | só Enterprise | logo + cores por empresa (`/companies`) salvam em qualquer plano |
| `limite_usuarios` | 2/2/10/∞ | **contado** no `/billing` (quota snapshot), **não bloqueia** criar usuário |
| `limite_atendimentos_mes` | 100/500/5.000/∞ | contado, não bloqueia (nem avisa) |
| `limite_documentos_kb` | 5/20/100/∞ | contado, não bloqueia upload na base de conhecimento |
| `limite_orcamento_ia_usd` | 5/10/100/500 | **não alimenta o `ia_budget`** — o teto de IA que vale é o que o admin digita em `/governanca/ia-budget`; um Free pode configurar US$ 1.000 |

O painel também **não esconde nem marca** nada por plano: o menu é gateado só por permissão (`requires:`), e o `/billing` mostra listas de features de marketing (`billing-page-client.tsx`) que não batem com as chaves acima.

## 4. Inventário completo — recurso a recurso

Legenda das colunas: **Hoje** = quem tem acesso na prática · **Custo** = o que o recurso custa à plataforma (LLM/infra/risco) · **Proposta** = liberação sugerida (✅ liberado · 🔒 bloqueado · número = limite) · **Esforço** = S (rota + chave), M (rota + tela + worker), L (mexe em fluxo). A coluna **Decisão** é sua.

### 4.1 Atendimento (Operação)

| Recurso | Hoje | Custo | Free | Pessoal | Pro | Enterprise | Esforço | Decisão |
|---|---|---|---|---|---|---|---|---|
| Fila de atendimento, conversa, composer (texto/mídia/nota de voz) | todos | infra | ✅ | ✅ | ✅ | ✅ | — | |
| Atendimentos/mês | contado, não aplicado | infra + Meta (R$ 0,035/msg a partir de 1º/10) | 100 | 500 | 5.000 | ∞ | M (aviso em 80 % + bloqueio suave: IA para, humano continua) | |
| Histórico de conversas + export CSV/XLSX | todos | — | ✅ (30 dias) | ✅ (90 dias) | ✅ | ✅ | M (usa `retencao_dias` já existente) | |
| Retenção de dados (dias) por empresa/agente | todos escolhem | storage | fixo 30 | até 90 | até 365 | ilimitado | S (validar no PUT) | |
| Transcrição de áudio para o operador (`transcrever_audio_sempre`) | todos | **LLM por áudio** | 🔒 | 🔒 | ✅ | ✅ | S (chave `transcricao_operador`; mesmo padrão da voz) | |
| Transferência entre departamentos/atendentes, turnos e jornada | todos | — | ✅ | ✅ | ✅ | ✅ | — | |
| Departamentos | todos | — | 1 | 2 | 10 | ∞ | S | |
| Tags, clientes (CRM light), anotações | todos | — | ✅ | ✅ | ✅ | ✅ | — | |
| Agendamentos (tela) | todos | — | 🔒 (depende do Calendar) | 🔒 | ✅ | ✅ | S (segue `calendar`) | |
| NPS / CSAT | todos | 1 msg WhatsApp por atendimento | 🔒 | ✅ | ✅ | ✅ | S (`csat`) | |
| App Android + push | todos | FCM (grátis) | ✅ | ✅ | ✅ | ✅ | — | |
| Resumo diário por WhatsApp (`resumo_diario_ativo`) | todos | 1 msg/dia | 🔒 | ✅ | ✅ | ✅ | S (`resumo_diario`) | |

### 4.2 IA & Conteúdo

| Recurso | Hoje | Custo | Free | Pessoal | Pro | Enterprise | Esforço | Decisão |
|---|---|---|---|---|---|---|---|---|
| Agentes de IA (quantidade) | ilimitado (há `count_agentes`, sem limite no plano) | LLM | 1 | 1 | 5 | ∞ | S (coluna `limite_agentes` + `require_plano_limit`) | |
| Tamanho do contexto | mig 188 | LLM (tokens de entrada) | Lite | Regular | Large | Extended | ✅ feito (#164) | |
| Modelos premium (> US$ 5/Mtok) | mig 188 | LLM | 🔒 | 🔒 | ✅ | ✅ | ✅ feito (#164) | |
| Catálogo completo de modelos (447) vs só curados | todos veem tudo | — | curados | curados | todos | todos | S (a tela já recebe `plano`; filtrar `curado` quando a chave estiver off) | |
| Orçamento de IA (`ia_budget`) — teto do plano como **máximo** do que o admin pode digitar | admin digita qualquer valor | **LLM — o maior risco de margem** | ≤ US$ 5 | ≤ US$ 10 | ≤ US$ 25–30 (reprecificar) | ≤ US$ 150 + excedente | M (PUT do budget valida contra `limite_orcamento_ia_usd`; criação do mês herda o teto do plano) | |
| Estilo/temperatura/top-p/max tokens | todos | — | ✅ | ✅ | ✅ | ✅ | — | |
| Ferramentas do agente (tools: calendar, KB, mídia, transfer…) | todos (calendar já gateado) | — | básicas | básicas | ✅ | ✅ | S | |
| Voz do agente (resposta em áudio) | Pro/Ent | TTS + verificação (2 chamadas) | 🔒 | 🔒 | ✅ | ✅ | ✅ feito (mig 177) | |
| Leitura de documentos do cliente (PDF/DOCX/XLSX/DOC) | todos | LLM (extração) | 🔒 | ✅ | ✅ | ✅ | S (`documentos_cliente`, gate no `preprocess` — cai no bloco "[Arquivo recebido — não lido]") | |
| Leitura de imagem (visão) e áudio (transcrição para o agente) | todos (`agente_ia.aceita_*`) | LLM multimodal | áudio ✅ · imagem 🔒 | ✅ | ✅ | ✅ | S | |
| Menu chatbot | todos | — | ✅ (1 menu) | ✅ | ✅ | ✅ | S | |
| Menu moderno (botões nativos WhatsApp) | todos (chave ignorada) | — | 🔒 | 🔒 | ✅ | ✅ | S (aplicar `menu_moderno` no PUT do menu) | |
| Workflows (LangGraph visual) | todos | LLM | 🔒 | 🔒 | 3 | ∞ | S | |
| Números sem IA (whitelist/bloqueio) | todos | — | ✅ | ✅ | ✅ | ✅ | — | |
| Base de conhecimento (RAG) | todos; KB contado, não aplicado | embeddings + storage | 5 KB | 20 KB | 100 KB | ∞ | S (`require_plano_limit("documentos_kb")` no upload) | |
| Respostas rápidas (templates) e variáveis | todos | — | ✅ | ✅ | ✅ | ✅ | — | |
| Few-shot automático (dataset Langfuse) | todos (opt-in por agente) | embedding + tokens por msg | 🔒 | 🔒 | ✅ | ✅ | S | |
| Versionamento de prompt + bateria de regressão (Testar) | todos | LLM por bateria | ✅ (sem bateria) | ✅ | ✅ | ✅ | S | |
| Servidores MCP | todos (chave `mcp` ignorada) | risco/suporte | 🔒 | 🔒 | 🔒 | ✅ | S (aplicar `mcp` no POST de mcp_server e no PUT do agente) | |
| Catálogo OpenRouter / Saúde de IA / alertas | superadmin | — | — | — | — | — | plataforma, fora do plano | |

### 4.3 Conectividade

| Recurso | Hoje | Custo | Free | Pessoal | Pro | Enterprise | Esforço | Decisão |
|---|---|---|---|---|---|---|---|---|
| Conexões (números) | limite aplicado | risco de ban / infra Evolution | 1 | 1 | 3 | ∞ | ✅ feito | |
| Provedor WABA (API oficial da Meta) | todos | Meta cobra por msg | 🔒 | 🔒 | ✅ | ✅ | S (`waba` no POST de conexão) | |
| Provedor Evolution (não oficial) | todos | risco de ban | ✅ | ✅ | ✅ | ✅ | — (contrato deve declarar) | |
| Templates HSM (WABA) | todos | Meta | segue WABA | | ✅ | ✅ | — | |
| Webhooks de saída (hooks + DLQ) | todos | — | 🔒 | 🔒 | ✅ | ✅ | S (`webhooks`) | |
| Integrações externas (Google Calendar, Asaas) | Calendar gateado | — | 🔒 | 🔒 | ✅ | ✅ | ✅ (calendar) | |
| Chaves de API da extensão (Disparador) | todos | — | segue Disparador | | | | — | |

### 4.4 Disparador (campanhas) — decisão anterior: **não é foco de venda** (memória `decisao_foco_atendimento_nao_disparo`)

| Recurso | Hoje | Custo | Free | Pessoal | Pro | Enterprise | Esforço | Decisão |
|---|---|---|---|---|---|---|---|---|
| Módulo Disparador (campanhas, contatos, grupos, extensão) | todos (chave `disparador` ignorada) | risco de ban + ToS | 🔒 (hoje `true` no seed!) | 🔒 | ✅ | ✅ | S (aplicar `disparador` nas rotas `/api/campanhas*`, `/api/disparador*` + esconder no menu) | |
| Teto de contatos por disparo | aplicado (Free 25) | — | 25 | — | 500 | ∞ | ✅ feito | |
| Mídia na campanha | aplicado | — | 🔒 | 🔒 | ✅ | ✅ | ✅ feito | |
| Anti-ban: teto diário + aquecimento por conexão | todos | — | ✅ | ✅ | ✅ | ✅ | — (proteção, não feature) | |

### 4.5 Governança e segurança

| Recurso | Hoje | Custo | Free | Pessoal | Pro | Enterprise | Esforço | Decisão |
|---|---|---|---|---|---|---|---|---|
| Usuários | contado, não aplicado | — | 2 | 2 | 10 | ∞ | S (`require_plano_limit("usuarios")` no POST `/api/usuarios` e no legado `/membros`) | |
| Perfis de acesso customizados (RBAC granular) | todos (chave `rbac` ignorada) | suporte | 🔒 (só os perfis system) | 🔒 | ✅ | ✅ | S (aplicar `rbac` no POST/PUT de perfil) | |
| Convite de acesso por WhatsApp, reset sem SMTP, histórico de login | todos | — | ✅ | ✅ | ✅ | ✅ | — | |
| Google SSO | todos (env) | — | ✅ | ✅ | ✅ | ✅ | — | |
| reCAPTCHA | global (env) | — | plataforma | | | | — | |
| Auditoria (audit_log) e governança de dados | todos | — | 30 dias | 90 | ✅ | ✅ | M | |
| White-label (logo + cores + nome) | todos (chave ignorada) | — | 🔒 | 🔒 | 🔒 | ✅ | S (aplicar `white_label` no PUT/logo da empresa) | |
| Feature flags por empresa (`/settings/feature-flags`) | admin da empresa | — | superadmin | superadmin | superadmin | superadmin | S (é ferramenta de plataforma, não de cliente) | |
| Horário de atendimento, regras de agendamento | todos | — | ✅ | ✅ | ✅ | ✅ | — | |

### 4.6 Observabilidade e relatórios

| Recurso | Hoje | Custo | Free | Pessoal | Pro | Enterprise | Esforço | Decisão |
|---|---|---|---|---|---|---|---|---|
| Dashboard de atendimentos, meu desempenho | todos | — | ✅ | ✅ | ✅ | ✅ | — | |
| Painel de IA (custo por agente/modelo), uso por cliente | todos | — | ✅ | ✅ | ✅ | ✅ | — | |
| Fila de mensagens, traces | todos | — | 🔒 | 🔒 | ✅ | ✅ | S | |
| Qualidade das respostas (RAG), sandbox de testes, relatórios Allure | todos | LLM (judge) | 🔒 | 🔒 | ✅ | ✅ | S | |
| Saúde da produção, catálogo OpenRouter | superadmin | — | plataforma | | | | — | |

## 5. Onde a liberação ganha dinheiro ou evita prejuízo (prioridade sugerida)

1. **Teto de IA do plano como máximo do `ia_budget`** — hoje o Free pode configurar US$ 1.000 e a plataforma paga. É o único item que **protege margem** de verdade; deve entrar junto com a reprecificação do Pro.
2. **Transcrição para o operador, documentos do cliente, few-shot, imagem no Free** — cada um é chamada de LLM paga pela plataforma em plano que não paga.
3. **Limites que já existem e não valem** (usuários, atendimentos/mês, KB) — o cliente compra "10 usuários" e recebe ilimitado.
4. **Disparador no Free = risco de ban + ToS** com quem não assinou contrato.
5. `mcp`, `rbac`, `white_label`, `menu_moderno` — diferenciação de plano prometida no seed e não entregue. Baixo risco, baixo esforço, mas só faz sentido depois dos itens 1–4.

## 6. Como implementar (padrão único, já existe)

- **Uma chave por recurso em `plano.features`** (boolean ou número) — semeada por migration, sem código novo de leitura: `PlanoInfo.tem_feature` / `limite_de`.
- **Backend**: `require_plano_feature("chave")` como `Depends` na rota (empresa do header) ou `assert_plano_feature(empresa_id, "chave")` quando a empresa vem do path; `require_plano_limit("recurso")` para contagens (falta acrescentar `usuarios`, `atendimentos_mes`, `documentos_kb`, `agentes`). Todos devolvem **402** com `detail{feature, plano_atual, upgrade_to, message}` — a UI já traduz (`api-error-shared.ts`).
- **Worker** (recursos que rodam por mensagem: transcrição, documentos, imagem, few-shot, voz): ler `get_plano_info` (cache 30 s) no ponto de decisão e **degradar**, nunca falhar o turno — o padrão da voz (mig 177) e do contexto (mig 188).
- **Painel**: um `plano` no `layout.tsx` (já resolve a empresa ativa para o white-label) → `nav-catalog.ts` ganha `feature?: "chave"` ao lado de `requires:`; item bloqueado aparece com cadeado e leva ao `/billing` (não some, para o cliente ver o que existe). As telas de toggle (transcrição, resumo diário, white-label…) mostram o mesmo cadeado que o seletor de modelos mostra hoje.
- **Antes de aplicar qualquer gate em produção**: rodar a consulta de uso por empresa (quem usa MCP, workflows, perfis custom, transcrição, quantos usuários/agentes/KB) e decidir **grandfathering** caso a caso — regra da casa: validar a regra contra produção antes de ligar. A 1018 (Pro) é o cliente-âncora; nada pode regredir nela sem aviso.
- **Levas sugeridas (uma PR cada, dev primeiro)**: (A) limites que já existem: usuários, atendimentos/mês, KB, agentes + teto de IA do plano no `ia_budget`; (B) custo de LLM por mensagem: transcrição do operador, documentos, imagem, few-shot; (C) módulos: disparador, MCP, RBAC, white-label, menu moderno, webhooks, WABA; (D) painel: cadeados no menu e nas telas + `/billing` refletindo as chaves reais (hoje é texto de marketing).

## 7. O que precisa existir antes dos gateways (Mercado Pago + InfinitePay, Pix)

- Tabela `plano`/`transacao` (mig 059) e os campos Asaas em `empresa` (mig 105) existem e nunca foram usados de verdade; `routes/billing.py` tem `checkout`/`status`/`cancel` apontando para o Asaas. A integração nova deve **reaproveitar `transacao`** e trocar o provedor — não criar outra tabela.
- Decidir: ciclo (mensal/anual), o que acontece no atraso (rebaixar para Free = os gates acima passam a valer sozinhos — por isso eles vêm antes), período de carência, e quem troca o plano (hoje só superadmin, à mão).
- Reprecificar o Pro (raio-X: R$ 397–497, teto US$ 25–30 + excedente) **antes** de publicar preço.
