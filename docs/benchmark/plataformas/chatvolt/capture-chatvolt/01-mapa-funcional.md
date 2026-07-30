# Chatvolt — mapa funcional

> Árvore de funcionalidades por domínio. Coleta: 2026-07-28.
> Cada item marca a fonte: **[API]** spec OpenAPI, **[DOC]** documentação,
> **[LIVE]** resposta real da API, **[APP]** rota do `_buildManifest.js` do painel,
> **[MKT]** material de marketing (não confirmado).

---

## 1. Agentes

### 1.1 Criação e configuração `[API]`

Campos de `POST /agents` — a superfície de configuração é enxuta (13 campos):

| Campo | Tipo | Nota |
|---|---|---|
| `name` | string | Nome gerado automaticamente se omitido |
| `description` | string | |
| `modelName` | string | Modelo LLM; lista de disponíveis em endpoint não documentado |
| `temperature` | number | 0.0–1.0 |
| `systemPrompt` | string | Prompt único, sem versionamento exposto |
| `visibility` | enum | `public` \| `private` — público dispensa autenticação |
| `handle` | string | Slug para URL amigável |
| `interfaceConfig` | object | Cores, mensagens iniciais do widget |
| `configUrlExternal` | object | URLs externas |
| `configUrlInfosSystemExternal` | object | URLs de sistema externo |
| `enableInactiveHours` | boolean | |
| `inactiveHours` | object | **Horários de inatividade por canal** |
| `tools` | array | Ferramentas associadas |

Observações relevantes:

- **Não há campo de departamento/fila no agente.** Roteamento organizacional é
  responsabilidade do Flux CRM, não do agente.
- `temperature` limitada a 1.0 (não 2.0).
- Horário de inatividade é **por canal** — o mesmo agente pode estar ativo no
  WhatsApp e inativo no Instagram no mesmo horário.

### 1.2 Ferramentas do agente `[API]`

Apenas **6 tipos nativos**, enum de `POST /api/agents/{agentId}/tools`:

| Tipo | O que faz |
|---|---|
| `http` | **Chama qualquer API HTTP** durante a conversa, via function calling |
| `datastore` | Busca semântica na base de conhecimento |
| `request_human` | Transfere para operador humano |
| `mark_as_resolved` | Marca conversa como resolvida |
| `delayed_responses` | Respostas com atraso deliberado |
| `follow_up_messages` | Mensagens de follow-up automáticas |

O conjunto é pequeno **por desenho**: `http` é a escotilha universal. Em vez de
catalogar dezenas de ações, deixam o cliente construir a sua chamando a própria
API. Isso é decisão de arquitetura, não pobreza de recurso.

#### HTTP Tool em detalhe `[DOC]`

- Nome + descrição da tool guiam o modelo sobre quando ativar
- Flag **"Provided By User"** por parâmetro: sinaliza ao modelo que ele deve
  extrair aquele dado da conversa
- **Raw Mode** — desliga a validação tipada e permite payload arbitrário com
  `string`, `number`, `integer`, `object`, `array`; suporta `enum`, `value` fixo,
  `items`, `properties` aninhadas
- Trade-off documentado: ativar Raw Mode converte todos os parâmetros para
  string e a tipagem anterior é perdida

### 1.3 Handoff humano `[DOC]`

- Botão **"Reply"** na Inbox assume a conversa e **desabilita a IA**
- Botão **"Enable AI"** devolve o controle
- Tool `request_human` faz o mesmo por decisão do agente
- Estado exposto na API: `POST /conversations/{id}/set-ai-enabled` e o campo
  `isAiEnabled`
- Funciona em Chat Bubble, IFrame e página standalone

O modelo é **binário e explícito**: IA ligada ou desligada por conversa, com
estado persistido e manipulável por API. Não há gate implícito por status.

### 1.4 Variáveis de prompt `[DOC]`

25 variáveis interpoláveis no system prompt:

**Contato** — `{user-phone-number}`, `{user-name}`, `{user-email}`

**Conversa** — `{conversation-id}`, `{conversation-channel}`, `{created-at}`,
`{status}`, `{priority}`, `{assignee-email}`, `{total-messages}`,
`{frustration-level}`, `{conversation-tags}`, `{summary}`, `{scenario-id}`,
`{scenario-name}`, `{step-id}`, `{step-name}`

**Atribuição de anúncio (CTWA — exclusivo WhatsApp)** — `{ad-headline}`,
`{ad-body}`, `{ad-source-url}`, `{ad-source-type}`, `{ad-clicked-at}`,
`{ad-clid}`, `{ad-source-id}`

**Outras** — `{today}`

Detalhes de implementação que valem copiar: valores de anúncio são **truncados**
(headline 100 chars, body 200) e têm quebras de linha removidas, explicitamente
"para não poluir o prompt".

`{frustration-level}` (0–100) e `{summary}` implicam pipeline de análise da
conversa rodando em background.

### 1.5 Variáveis de conversa `[DOC]` `[API]`

KV arbitrário por conversa, manipulado **pelo próprio agente** via tool template:

- `varName` ≤ 20 chars, `varValue` ≤ 100 chars
- Semântica de upsert
- **O agente só enxerga variáveis criadas/atualizadas nos últimos 3 dias** —
  janela de frescor que evita contaminar o prompt com estado velho
- API completa: `GET/POST/DELETE /variables/{conversationId}[/{varName}]`

É memória estruturada de curto prazo, distinta da base de conhecimento.

### 1.6 Qualidade de resposta

- **Fine-tuning por correção** `[DOC]` — botão "improve" na Inbox quando o agente
  erra; operador escreve a resposta certa e o sistema **gera automaticamente um
  datasource Q&A** no datastore ligado. Loop de melhoria operado por quem atende,
  sem passar por engenharia.
- **Answer sources** `[DOC]` — links para os datasources usados na resposta;
  desligável nas configurações globais do agente.
- **Message suggestions** `[DOC]` — mensagens de exemplo clicáveis para o usuário.
- **Guia anti-alucinação** `[DOC]` — evitar conteúdo duplicado (mesmo traduzido),
  usar modelo mais forte. Conteúdo raso e datado (fala em GPT-4 vs GPT-3.5).
- **Debug** `[DOC]` — checklist de reprodução. Sem ferramenta real de trace.

### 1.7 Áudio e transcrição `[DOC]`

- Usuário manda texto → agente responde texto. Usuário manda **áudio** → agente
  responde **áudio gerado por IA**. Espelhamento de modalidade.
- Transcrição via **Groq** (chave própria da organização)
- Voz via **ElevenLabs** (chave própria da organização)
- Perfil de voz escolhido por integração, na aba Deploy
- Disponível em Z-API, WhatsApp Oficial e Telegram

Modelo **BYOK** — a organização traz as próprias chaves; o Chatvolt não revende
o serviço.

### 1.8 Upload de arquivo na conversa `[DOC]`

Tipos aceitos: CSV, TXT, Markdown, PDF, JSON, PPTX, DOCX, XLSX, e PNG/JPEG/GIF/WebP
(estes exigem modelo com visão).

Escopo é **a conversa**, não o agente — arquivo enviado numa conversa não vaza
para outra. Dropdown permite reusar arquivo já enviado.

### 1.9 Listas de controle `[API]`

- **Whitelist** (`/agent-whitelist-whatsapp`) — *allow-list*: o agente **só**
  envia para números da lista. Disponível em WhatsApp Oficial e Z-API. CRUD completo.
- **Blacklist** (`/agent-blacklist`) — bloqueio por agente. CRUD completo.

⚠️ **A `whitelist` deles é o oposto da nossa.** Ver README, seção "armadilhas de
vocabulário".

### 1.10 Rate limit `[DOC]`

Limite de mensagens por usuário, configurado no agente. **Só vale para widget**
(bubble, iframe, standalone) — não protege WhatsApp nem Telegram.

---

## 2. Base de conhecimento (RAG)

### 2.1 Modelo `[LIVE]` `[DOC]`

Hierarquia de dois níveis: **Datastore** (container) → **Datasource** (fonte).
O agente liga a um datastore via `datastore` tool.

Campos reais de um datastore (`GET /datastores/list`):

```
id, name, description, type ("qdrant"), autosync (bool),
visibility (private|public), pluginIconUrl, pluginName,
pluginDescriptionForHumans, pluginDescriptionForModel,
config, ownerId, organizationId, createdAt, updatedAt,
_count: { datasources }
```

- Vector store: **Qdrant**
- `pluginDescriptionForModel` é gerado automaticamente e descreve ao LLM quando
  usar aquele datastore — relevante quando o agente tem vários

### 2.2 Fontes suportadas `[MKT]` `[DOC]`

Arquivos (DOC, CSV, XLS, PDF, JSON), leitura de site com limite de páginas por
plano (100 → 1.000), **Google Drive** com sincronização automática, **YouTube**
com transcrição de vídeo, Q&A manual (gerado pelo fine-tuning).

### 2.3 Limites por plano

Tamanho de upload (1MB → 25MB), páginas de site (100 → 1.000), número de
datastores (1 → 30), storage em "palavras" (20 mil → 120 milhões).

Google Drive e YouTube só a partir do **Pro**.

### 2.4 Busca `[API]`

`POST /datastores/{id}/query` retorna fragmentos similares. Filtrável por IDs de
datasource. Chunking, estratégia de embedding e reindexação **não são
documentados nem configuráveis** pela API.

---

## 3. Canais

| Canal | Mecanismo | Notas |
|---|---|---|
| **WhatsApp Oficial** | Embedded Signup (Facebook) | Permite **manter o app WhatsApp Business no celular funcionando em paralelo**, com sincronização em tempo real |
| **Z-API** | Provider não-oficial | Suporta grupos (evento `GROUP_MESSAGE_RECEIVED` quando o agente não é mencionado) |
| **Zapper HUB** | Provider não-oficial | `POST /zapper/instances/{id}/message` |
| **Instagram** | App Meta Business próprio do cliente | DM **e comentários** em posts |
| **Telegram** | Token do BotFather | Suporta canal com bot como admin |
| **Slack** | OAuth | DM + menção em canal |
| **Mercado Livre** | OAuth | Perguntas de produto e pós-venda, **com liga/desliga por produto** e ação em massa |
| **Twilio** | SID + Auth Token + Phone SID | **SMS**, não WhatsApp |
| **Site** | Widget | Bubble, standard, iframe, página standalone |
| **API / Dashboard / internal_chats** | — | Canais internos, aparecem no enum `{conversation-channel}` |

Enum completo de canal, extraído das variáveis de prompt: `mercadolivre`,
`mercadolivreDm`, `instagram`, `instagramDm`, `zapi`, `whatsapp`, `chatbox`,
`website`, `dashboard`, `telegram`, `api`, `internal_chats`.

### Mensagens interativas WhatsApp `[API]`

Seis tipos, todos via API: `send-buttons`, `send-lists`, `send-cta`,
`send-location`, `location-request`, `send-contact`.

### Templates HSM `[API]`

`GET/POST /whatsapp/templates` (listar e **criar** template Meta),
`POST /whatsapp/{phoneNumberId}/template-message` (enviar).

---

## 4. CRM / funil — "Flux CRM"

O módulo próprio mais elaborado do produto.

### 4.1 Conceitos `[DOC]`

- **Scenario** — fluxo de interação; container de steps
- **Step** — estágio dentro do cenário
- **Conversation** — caminha pelos steps
- Interface **kanban com drag-and-drop**: reordena steps, move conversas
- **Uma conversa só pode estar ativa em um cenário por vez.** Adicionar ao
  cenário Y desativa no X. Opção "Show Inactive Conversations" mostra o histórico.

### 4.2 Configuração de step `[DOC]`

**Básico:**

| Campo | Função |
|---|---|
| Nome | Exibido no board |
| Agente responsável | Quem responde neste step; vazio mantém o agente atual |
| Condição de entrada | Texto livre em linguagem natural — "mova quando o usuário perguntar sobre preço". **Avaliada por LLM.** Não se aplica ao step 0 |
| Prompt extra | Anexado ao prompt principal do agente **só neste step** |
| Mensagem de entrada | Enviada automaticamente ao entrar no step |

**Avançado:**

| Campo | Função |
|---|---|
| Step obrigatório | Conversa não pode pular este step |
| Step de remoção | Conversa que entra sai do board (finalização/arquivamento) |
| Solicitar contato | Agente pede nome / e-mail / telefone (selecionável) |
| Auto next step | Move sozinho após tempo definido (min/horas/dias) para step destino |
| Status padrão | `Resolved` \| `Unresolved` \| `Human Requested` |
| Prioridade padrão | `Low` \| `Medium` \| `High` |
| Controle de IA | Liga, desliga, ou mantém |
| Tags padrão | Adicionar **e remover** tags automaticamente |
| Lógica de atribuição | `None` \| usuário específico \| **aleatório entre selecionados** |
| Times/usuários elegíveis | Pool para a atribuição |
| Notificação Z-API | Manda WhatsApp para número definido ao entrar no step, com variáveis interpoladas |
| Webhook | `POST` com payload `STEP_ENTERED` |

Três coisas aqui merecem atenção especial:

1. **Condição de entrada em linguagem natural avaliada por LLM** — nosso
   `workflow` usa `branch` com condição determinística. É uma diferença de
   filosofia, não só de recurso.
2. **Prompt extra por step** — o agente muda de comportamento conforme a fase do
   funil, sem trocar de agente.
3. **Auto next step por tempo** — automação de follow-up embutida na máquina de
   estados, não numa ferramenta separada.

### 4.3 Conversas `[API]`

Estados: `RESOLVED` \| `UNRESOLVED` \| `HUMAN_REQUESTED`.
Prioridade: `LOW` \| `MEDIUM` \| `HIGH`.
IA: `enabled` \| `disabled`.

Operações: listar com filtro (data, status, prioridade, IA), obter por ID,
deletar, atribuir (com `force` para roubar conversa já atribuída — retorna 409
sem ele), definir status/prioridade/IA, enviar mensagem, **registrar mensagem sem
enviar** (`message-register`), CRUD de notas, CRUD de variáveis.

Campos derivados: `summary`, `frustration` (0–100), `tags`, `assignee`.

### 4.4 Contatos `[API]`

CRUD + **variáveis por contato** (`/contacts/variables`), distintas das variáveis
de conversa. Paginação por cursor (`hasMore`, `nextCursor`).

### 4.5 Logs de conversa CRM `[API]`

`/crm/conversationLog` — CRUD completo, incluindo `PATCH` parcial. Trilha
auditável do caminho da conversa pelo funil.

---

## 5. Disparos / campanhas — "Dispatches"

### 5.1 Listas de contato `[DOC]` `[API]`

- Criação manual ou **upload de CSV com mapeamento de colunas** para `name` e `phone`
- Revisão e edição antes de salvar
- Aba "Saved Lists" para gestão
- API: CRUD em `/dispatches/contacts/lists` + vínculo lista↔disparo

### 5.2 Disparo `[DOC]`

Configuração: nome, **uma ou mais listas**, agente responsável, **cenário CRM +
step inicial**, status padrão da conversa, agendamento (imediato ou data/hora).

Abas: Active, Scheduled, Completed, Saved Lists.

`POST /dispatches/{id}/populate-queue` sugere fila interna de envio.

### 5.3 O ponto que mais importa

**O disparo já entrega o contato dentro do funil.** Escolher cenário + step
inicial significa que a resposta ao disparo cai numa máquina de estados com
agente, prompt e automação próprios — não numa conversa solta.

É integração de módulos, não recurso isolado.

### 5.4 O que não achei

Nenhuma documentação de **opt-out**, descadastro, ou controle anti-ban
(intervalo entre envios, jitter, aquecimento, teto diário). Planos oferecem
"400/800 disparos grátis", sugerindo cobrança por volume.

---

## 6. Artifacts — catálogo de produtos

Módulo próprio. Hierarquia:

```
Categoria principal  (ex: Shorts)
└── Subcategoria      (ex: Shorts Feminino)
    └── Artifact       (ex: Shorts Modelo Y)   ← o produto
        └── Media      (fotos/vídeos)
```

Descrito na doc como "catálogo digital / inventário que seu agente pode
consultar para mostrar produtos ao cliente".

API `[API]`: CRUD de artifacts, **busca** (`/artifacts/search`), **bulk delete**,
CRUD de categorias, upload/listagem/atualização/remoção de mídia.

`DELETE /artifacts/{id}` faz "Delete **or Toggle**" — permite desativar sem apagar.

É e-commerce conversacional: catálogo estruturado com imagem, consultável pelo
agente. Coisa diferente de RAG sobre documento.

---

## 7. VoltAPI — sandbox JavaScript

Marcado pelos autores como **Experimental Feature**.

- Funções JS assíncronas que recebem `input` e retornam resultado
- Executadas por serviços internos do Chatvolt, **não expostas como endpoint público**
- Utilitários: `fetch` **com proteção SSRF**, `console.*` com logs capturados
- Limites: timeout ~30s, teto de memória, **sem módulos Node**
- Gestão: criar, renomear, deletar, habilitar/desabilitar
- **Assistente de IA embutido** para escrever, explicar e depurar as funções

Extensibilidade sem deploy: o cliente escreve lógica de transformação e
integração dentro da plataforma.

---

## 8. Widget / embed

Três modos `[DOC]`: **Bubble** (balão flutuante), **Standard** (inline na
página), **Standalone page** (página hospedada) — mais iframe.

Instalação via ESM de CDN:

```html
<script type="module">
  import Chatbox from 'https://cdn.jsdelivr.net/npm/@chatvolt/embeds@latest/dist/chatbox/index.js';
  Chatbox.initBubble({ agentId: 'YOUR_AGENT_ID' });
</script>
```

Customização por `interfaceConfig` no agente (cores, mensagens iniciais).
Referência completa de atributos em `/widgets/chatbot/reference`.

Remoção da marca Chatvolt só a partir do plano **Pro**.

Agente `public` responde **sem autenticação** — é o que viabiliza o widget
anônimo.

---

## 9. API e extensibilidade

Coberto em detalhe em [`02-api-e-integracoes.md`](02-api-e-integracoes.md).
Resumo: **112 endpoints documentados**, base `https://api.chatvolt.ai`,
autenticação `Authorization: Bearer <API_KEY>`.

### Webhooks de saída `[DOC]`

Nove tipos de evento:

| Evento | Quando |
|---|---|
| `AGENT_USER_MESSAGE` | Padrão — usuário manda, agente responde |
| `USER_MESSAGE_RECEIVED` | Mensagem recebida **com IA desligada** |
| `AGENT_MESSAGE_SENDED` | Operador envia pela Inbox |
| `AGENT_MESSAGE_FOLLOW_UP` | Follow-up automático |
| `AGENT_MESSAGE_BLOCKED` | Bloqueado (ex: fora da janela de 24h) |
| `AGENT_MESSAGE_NOTED` | Registrado como nota (canal não suporta envio) |
| `GROUP_MESSAGE_RECEIVED` | Mensagem em grupo sem menção (Z-API) |
| `STEP_ENTERED` | Conversa entra em step do Flux CRM |
| `NPS_INTERACTION` | Interação ou conclusão de fluxo NPS |

**Health check antes de salvar** — o sistema faz `POST` de teste na URL:
resposta > 5s marca como "Slow", > 6s ou inalcançável marca "Unreachable".
Falhas consecutivas em uso **bloqueiam automaticamente** o webhook; desbloqueio
exige re-salvar a URL.

Payload cobre ~30 atributos, incluindo `conversation_variables`,
`ctwaAttributions` (atribuição de anúncio) e `attachments`.

### Webhook de entrada `[DOC]`

"Fetch External User Information" — URL configurável que o agente chama para
**enriquecer o perfil do contato** com dados de sistema externo, exibidos na
Inbox. Header de autenticação opcional.

---

## 10. Multi-tenant, permissões e billing

### 10.1 Organização `[LIVE]`

Unidade de tenancy é **Organization** (`organizationId` presente em todo
recurso). Usuários pertencem a organizações; recursos são `private` ou `public`.

### 10.2 Permissões `[DOC]`

Duas camadas combinadas:

**Camada 1 — flag Admin.** `true` = acesso total, ignora o resto.

**Camada 2 — por módulo:**

| Módulo | Permissões |
|---|---|
| Inbox | Manage All Messages (marcar lidas, resolver, deletar conversas e variáveis) / **Only View Human Requested** |
| Settings | Api Keys, Billing, Llm Keys |
| Agents | View, Create |
| Forms | View, Create |
| Datastores | View, Create, Settings, + Datasources: Create/Update/Delete |
| Contacts | View |
| Analytics | View |

**Camada 3 — por agente individual:** `View`, `Update`, `Delete` para **cada**
agente, com ações em massa ("set all", "disable all").

A permissão por agente é o diferencial: um usuário pode editar o agente de
Vendas e nem enxergar o de Financeiro.

Presets sugeridos na doc (não são papéis reais do sistema): ADMIN, USER, SUPPORT.

Existe um módulo **"Forms"** nas permissões que **não tem documentação nem
endpoint** em nenhum outro lugar. Funcionalidade não mapeada.

### 10.3 Billing

Ver [`00-visao-geral.md`](00-visao-geral.md). Limites por plano: agentes,
datastores, créditos de mensagem, assentos, storage, cenários/steps do Flux CRM,
tamanho de upload, páginas de leitura de site, disparos grátis.

---

## 11. Analytics

O módulo **menos documentado** do produto: nenhuma página de doc, nenhum
endpoint entre os 112 documentados, nenhuma menção a exportação.

Mas **existe** — confirmado no `_buildManifest.js` do painel `[APP]`:

| Rota | O que indica |
|---|---|
| `/analytics` | Módulo real, não só permissão |
| `/analytics/FiltersAnalytics` | Filtros — provavelmente período, agente, canal |
| `/analytics/CreditsAuditTab` | **Auditoria de consumo de crédito** |
| `/custom-dashboard` | Dashboard montável pelo cliente |
| `/contacts/components/ContactExport` | Exportação de contatos existe |

Sinais adicionais de medição no produto: `frustration` (0–100) e `summary` por
conversa, `NPS_INTERACTION` como evento de webhook, `/crm/conversationLog`.

A aba de auditoria de créditos é a mais reveladora: mostra que a **unidade de
cobrança é observável pelo cliente**, não só cobrada. É o equivalente comercial
do nosso `/governanca/ia-budget`, que mede custo real em dólar.

**Profundidade ainda não avaliável** — sem captura do painel não dá para dizer
quais métricas, granularidade ou exportação. Ver
[`04-ux-flows.md`](04-ux-flows.md#pendentes-) para a captura pendente.

## 12. Compliance

Documentação jurídica dedicada, em versões internacional e brasileira: LGPD
(`privacy/lgpd`, `privacy/br-lgpd`), política de cookies, política de
privacidade, termos de uso.

Declaram conformidade com a Google API Services User Data Policy (Limited Use)
para a integração Google Drive/YouTube.

**Não encontrei** na documentação: política de retenção configurável, residência
de dados, log de auditoria de ações administrativas, ou fluxo de exportação/
exclusão de dados do titular. A doc de permissões *recomenda* manter audit logs
como boa prática — o que sugere que a plataforma **não** os fornece.

## 13. Módulos não documentados

Encontrados no `_buildManifest.js`, ausentes da documentação pública `[APP]`:

| Rota | Leitura |
|---|---|
| `/forms`, `/forms/[formId]`, `/forms/[formId]/admin` | **Resolve o mistério**: "Forms" aparecia nas permissões sem doc nem endpoint. É módulo real, com visão de admin — provavelmente formulário de captação de lead |
| `/apps` | Catálogo ou marketplace de integrações |
| `/partner-set` | **Programa de parceiro/revenda.** Encaixa no ICP de agência e explica a estratégia de conteúdo (curso gratuito, comunidade) |
| `/integrations/crisp/config`, `/integrations/crisp/widget` | Integração **Crisp** — canal ausente da lista documentada |
| `/custom-dashboard` | Dashboard customizável |
| `/onboarding` | Onboarding guiado |
| `/join` | Fluxo de convite de time |
| `/agents/[id]/iframe`, `/agents/[id]/standalone` | Confirma os modos de widget |
| `/analytics-test` | Rota de desenvolvimento esquecida em produção |

O `/partner-set` é o achado mais relevante para estratégia: indica **canal de
revenda estruturado**, não só venda direta. Nosso white-label por empresa
(migration 115) é a peça técnica equivalente, mas não temos programa de parceiro
montado em cima dele.

---
