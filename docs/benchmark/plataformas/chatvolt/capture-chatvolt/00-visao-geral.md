# Chatvolt — visão geral

> Coleta: 2026-07-28. Fontes em [`05-fontes.md`](05-fontes.md).

## O que é

Plataforma SaaS brasileira de agentes de IA conversacionais, com foco declarado
em WhatsApp. Vende automação de atendimento 24h e "CRM integrado", operada por
painel no-code em `app.chatvolt.ai`.

Posicionamento da própria empresa (meta description da home):

> "O melhor Agente de IA para WhatsApp que automatiza seu atendimento 24h.
> Chatbot inteligente para WhatsApp, Instagram e Site com 50+ modelos de IA e
> CRM integrado."

## Linhagem técnica — a leitura mais importante deste documento

O núcleo do Chatvolt é, com altíssima probabilidade, **um fork do Chaindesk**
(ex-Databerry), projeto open source. As evidências são estruturais, não
circunstanciais:

| Evidência | Onde aparece |
|---|---|
| Tagline literal do Chaindesk: *"Connect custom data to large language models"* | `<title>` de todas as páginas de `docs.chatvolt.ai` |
| Vocabulário **Datastore / Datasource** | Doc e API — nomenclatura própria do Chaindesk |
| Campos `pluginIconUrl`, `pluginName`, `pluginDescriptionForHumans`, `pluginDescriptionForModel` | Resposta real de `GET /datastores/list` |
| `visibility: public\|private` + `handle` (slug) no agente | Schema de `POST /agents` |
| IDs `cuid` (`cms4tfltf03h8uopj5rgadjfq_v3`) | Resposta real da API |
| Vector store Qdrant declarado como `type` do datastore | Resposta real da API |

Os campos `plugin*` são resquício da era de **ChatGPT Plugins** (2023) — herança
morta que sobreviveu no schema. Isso data o núcleo e explica por que "Datastore"
e "Datasource" convivem com módulos de nome comercial ("Flux CRM", "VoltAPI").

### Por que isso importa para nós

Separa o que é **commodity** do que é **produto real** deles:

**Herdado do open source** (replicável por qualquer concorrente, inclusive nós,
sem vantagem competitiva): agentes + datastores + datasources, widget de chat,
API de query, integrações Telegram/Slack, estrutura de tools.

**Construído pelo Chatvolt** (é aqui que está o produto): Flux CRM, Dispatches,
Artifacts, VoltAPI, integrações Z-API/Zapper/Mercado Livre, atribuição CTWA,
frustration score, NPS, permissões granulares por agente, áudio ElevenLabs.

Conclusão operacional: **não faz sentido nos compararmos ao núcleo Chaindesk.**
A comparação relevante é contra o que eles construíram em cima — e é exatamente
aí que estão os gaps reais, catalogados em [`backlog-gaps.md`](../../backlog-gaps.md).

## ICP e modelo de negócio

### Perfil de cliente

O desenho dos planos revela o alvo: **PME brasileira e agências/revendas**, não
enterprise. Sinais:

- Preços em BRL, sem cotação em dólar
- Plano gratuito com agente **só para site** — WhatsApp é o gancho de upgrade
- "Créditos de mensagens" como unidade de cobrança (previsível para PME)
- White-label parcial ("remover a marca Chatvolt da janela de chat") só a partir
  do Pro — típico de captura de agência
- Curso gratuito em vídeo e comunidade — aquisição por conteúdo/infoproduto
- Integração Mercado Livre — e-commerce brasileiro pequeno e médio

### Planos

| Plano | Preço | Agentes | Datastores | Mensagens/mês | Usuários | Storage |
|---|---|---|---|---|---|---|
| **Discover** | Grátis, para sempre | 1 (só Website) | 1 | 200 créditos | 2 | 20.000 palavras |
| **Basic** | R$ 237/mês | 2 multicanais | 4 | 7.500 créditos | 5 | 30.000.000 palavras |
| **Pro** | R$ 549/mês | 5 multicanais | 10 | 30.000 créditos | 20 | 60.000.000 palavras |
| **Pro-Max** | R$ 997/mês | 15 multicanais | 30 | 60.000 créditos | 40 | 120.000.000 palavras |
| **Avançado** | Sob consulta | Ilimitado | — | — | — | — |

### O que cada degrau destrava

| Plano | Destrava |
|---|---|
| **Discover** | Upload até 1MB. **Sem WhatsApp, sem leitura de site.** |
| **Basic** | **Integração WhatsApp Oficial**, leitura de site até 100 páginas, upload 5MB, suporte por e-mail |
| **Pro** | Google Drive + YouTube como fonte, sincronização automática, **Flux CRM** (máx. 5 cenários × 20 etapas), **400 disparos grátis**, remoção da marca, leitura de site até 1.000 páginas, upload 10MB, suporte humano |
| **Pro-Max** | 15 cenários Flux × 30 etapas, 800 disparos grátis, upload 25MB |
| **Avançado** | Arquitetura sob medida, integrações customizadas, SLA dedicado, consultoria |

### Como monetizam — três alavancas

1. **Créditos de mensagem** — consumo, sobe com o uso.
2. **Assentos** — 2 → 5 → 20 → 40. Puxa upgrade quando o time de atendimento cresce.
3. **Módulos por degrau** — Flux CRM e disparos só no Pro. São as funcionalidades
   de maior valor percebido, deliberadamente colocadas acima do ticket de entrada.

O storage é generoso a ponto de ser decorativo (30 milhões de palavras no Basic)
— não é gargalo real, é número grande para a tabela comparativa. **O gargalo de
verdade é crédito de mensagem e assento.**

### Comparação com o nosso modelo

O Chat Nexus cobra por limites de recurso — `limite_usuarios`, `limite_conexoes`,
`limite_atendimentos_mes`, `limite_orcamento_ia_usd`, `limite_documentos_kb`
(`shared/plano_limits.py`) — com billing via Asaas.

Duas diferenças estruturais:

- **Cobramos por conexão; eles não.** O Chatvolt não limita números de WhatsApp
  explicitamente — limita agentes. Nosso `limite_conexoes` é uma alavanca que
  eles não usam, e faz sentido no nosso posicionamento (multi-número real).
- **Temos teto de custo de IA em dólar** (`limite_orcamento_ia_usd`), eles usam
  "créditos". Crédito é mais legível para o cliente; dólar é mais honesto para a
  margem. Vale considerar expor crédito na UI mantendo dólar no backend.

## Canais suportados

| Canal | Como |
|---|---|
| WhatsApp Oficial (Cloud API) | Embedded Signup via Facebook |
| WhatsApp não-oficial | Z-API e Zapper HUB |
| Instagram | DM + comentários em posts |
| Telegram | Bot via BotFather |
| Slack | DM + menção em canal |
| Mercado Livre | Perguntas de produto + pós-venda |
| Twilio | SMS |
| Site | Widget bubble, standard, iframe, página standalone |
| API / Dashboard | Canais internos |

Nove canais contra **um** nosso (WhatsApp, em quatro providers). É a maior
assimetria do benchmark inteiro — analisada em detalhe na matriz e no backlog,
onde argumento que **paridade de canal não é o objetivo certo para nós**.

## Modelos de LLM

Alegam "50+ modelos" e citam ChatGPT, Gemini, Gemma, WizardLM 2, Phi 3,
Command-R, Claude 3, Mistral, Dolphin, OpenChat, Llama 3. Vendem também
"Volt-Networks", descrito como síntese de múltiplos modelos numa resposta — sem
documentação técnica que permita avaliar o que de fato faz.

A lista citada está **datada** (Claude 3, Llama 3, WizardLM 2 são de 2024). O
schema da API expõe `modelName` como string livre, remetendo a um endpoint de
modelos disponíveis que não está documentado.

Chave de LLM é configurável pela organização (permissão "Llm Keys"), então o
cliente pode usar a própria conta — modelo BYOK.

## Estado de maturidade

Sinais de produto em construção acelerada, colhidos da própria documentação:

- **VoltAPI marcada como "Experimental Feature"** pelos próprios autores
- Doc de `datastore/get-started` tem só ~10 linhas e um typo ("fhe following steps")
- `api-reference/authentication` contém "This demonstes how to..."
- Screenshots com nome de arquivo `Xnapper-2023-09-07-...` — telas de 2023 ainda em uso
- Módulos recentes (Artifacts, Dispatches, Flux CRM) têm doc muito mais cuidada
  que os herdados

Leitura: o time investe onde está construindo, e a documentação do núcleo
herdado ficou parada. Não é sinal de fragilidade do produto — é sinal de **onde
está o foco deles**, o que é informação estratégica útil.
