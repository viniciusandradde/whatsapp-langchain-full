# Chatvolt — API e integrações

> Coleta: 2026-07-28. Superfície extraída dos specs OpenAPI publicados em
> `docs.chatvolt.ai` e validada com chamadas de leitura contra conta real.

## Autenticação

```
Authorization: Bearer <API_KEY>
```

Base: `https://api.chatvolt.ai`

Chave gerada em `app.chatvolt.ai/settings/api-keys`. Uma única chave por
organização, sem escopo, sem expiração documentada, sem rotação automática.

Recursos marcados `visibility: public` (agentes e datastores) são acessíveis
**sem autenticação** — é o mecanismo que viabiliza o widget anônimo.

### O que não existe

- **Sem escopos.** A chave é tudo-ou-nada: quem tem a chave lê contatos, dispara
  campanha e deleta datastore.
- **Sem rate limit documentado.** Nenhum header `X-RateLimit-*`, nenhuma menção
  a limite de requisições. (O "rate limit" da doc é outra coisa: limite de
  mensagens do usuário final no widget.)
- **Sem versionamento.** Não há `/v1/`. Path `/api/agents/{id}/tools` convive
  com `/agents/{id}` — inconsistência que sugere serviços de épocas diferentes.
- **Sem paginação uniforme.** Datastores usam `{offset, limit, total, count}`;
  contatos usam cursor (`hasMore`, `nextCursor`); conversas retornam array puro.

## Superfície completa — 112 endpoints

### Agentes (6)

| Método | Path |
|---|---|
| `POST` | `/agents` — criar |
| `GET` | `/agents/{id}` |
| `PATCH` | `/agents/{id}` |
| `DELETE` | `/agents/{id}` |
| `POST` | `/agents/{id}/query` — **perguntar ao agente** |
| `PATCH` | `/agents/{id}/webhook` — liga/desliga webhook por provider |

Não há `GET /agents` (listagem). Para descobrir agentes é preciso conhecer o ID.

### Ferramentas do agente (4)

`GET` `POST` `/api/agents/{agentId}/tools` · `PATCH` `DELETE` `/api/agents/{agentId}/tools/{toolId}`

### Listas de controle (8)

| Método | Path |
|---|---|
| `GET` `POST` | `/agent-whitelist-whatsapp` · `/agent-whitelist-whatsapp/{id}` |
| `PATCH` `DELETE` | `/agent-whitelist-whatsapp/{id}` |
| `GET` `POST` | `/agent-blacklist` |
| `GET` `DELETE` | `/agent-blacklist/{agentId}` |

### Conversas (14)

| Método | Path | Nota |
|---|---|---|
| `GET` | `/conversation` | Lista com filtros: data, status, prioridade, IA |
| `GET` `DELETE` | `/conversation/{conversationId}` | |
| `GET` | `/conversation/{conversationId}/messages/{count}` | |
| `GET` | `/messages/{messageId}` | |
| `POST` | `/conversation/message/{type}/{value}` | Envia por identificador flexível |
| `POST` | `/conversations/{id}/assign` | **409 se já atribuída**, salvo `force: true` |
| `POST` | `/conversations/{id}/message-register` | **Registra sem enviar ao cliente** |
| `POST` | `/conversations/{id}/set-ai-enabled` | |
| `POST` | `/conversations/{id}/set-priority` | |
| `POST` | `/conversations/{id}/set-status` | |
| `GET` `POST` | `/conversations/{id}/notes` | |
| `PUT` `DELETE` | `/conversations/{id}/notes/{noteId}` | |

Dois detalhes de contrato que valem imitar:

- **`assign` com 409 + `force`** — trata conflito de atribuição explicitamente,
  em vez de sobrescrever em silêncio.
- **`message-register`** — grava mensagem no histórico sem entregar ao cliente.
  Serve para injetar contexto de sistema externo na timeline.

### Variáveis de conversa (4)

`POST /variables` (upsert) · `GET /variables/{conversationId}` ·
`GET` `DELETE` `/variables/{conversationId}/{varName}`

### Contatos (6)

`GET` `POST` `/contacts` · `GET` `POST` `PUT` `DELETE` `/contacts/variables`

### Flux CRM (15)

| Recurso | Endpoints |
|---|---|
| Cenários | `GET` `POST` `PUT` `DELETE` `/crm/scenario` |
| Conversas do cenário | `GET` `DELETE` `/crm/scenario/{scenarioId}/conversation` |
| Steps | `GET` `POST` `PUT` `DELETE` `/crm/step` |
| Conversa no step | `POST /crm/step/conversation` · `POST /crm/step/move` |
| Logs | `GET` `/crm/conversationLog` · `GET` `PUT` `PATCH` `DELETE` `/crm/conversationLog/{logId}` |

CRUD de cenário e step opera no **path da coleção** com ID no corpo — padrão
incomum (`PUT /crm/scenario` em vez de `PUT /crm/scenario/{id}`).

### Datastores e datasources (10)

`GET /datastores/list` · `POST /datastores` · `GET` `PATCH` `DELETE` `/datastores/{id}` ·
`POST /datastores/{id}/query` · `GET /datasources/list` · `POST /datasources` ·
`GET` `DELETE` `/datasources/{id}`

### Dispatches (11)

`GET` `POST` `DELETE` `/dispatches` · `POST /dispatches/{id}/populate-queue` ·
`GET` `POST` `PUT` `DELETE` `/dispatches/contacts/lists` ·
`GET` `POST` `DELETE` `/dispatches/contacts/link` ·
`GET /dispatches/contacts/{contactId}`

### Artifacts (17)

`GET` `POST` `DELETE` `/artifacts` (bulk delete no verbo da coleção) ·
`GET /artifacts/search` · `GET` `PUT` `DELETE` `/artifacts/{id}` ·
`GET /artifacts/media` · `POST /artifacts/media/upload` ·
`PATCH` `DELETE` `/artifacts/media/{id}` ·
`GET` `POST` `/artifact-categories` · `GET` `PUT` `DELETE` `/artifact-categories/{id}`

### WhatsApp (9)

| Método | Path |
|---|---|
| `GET` `POST` | `/whatsapp/templates` — listar e **criar** template Meta |
| `POST` | `/whatsapp/{phoneNumberId}/template-message` |
| `POST` | `/messages/interactive/send-buttons` |
| `POST` | `/messages/interactive/send-lists` |
| `POST` | `/messages/interactive/send-cta` |
| `POST` | `/messages/interactive/send-location` |
| `POST` | `/messages/interactive/location-request` |
| `POST` | `/messages/interactive/send-contact` |

### Providers não-oficiais e outros (4)

`POST /zapi/{instanceId}/{contactPhone}/message` ·
`POST /zapper/instances/{id}/message` ·
`POST /twilio/{ownerPhone}/{contactPhone}/message` (SMS) ·
`GET /mercadolivre/get-products`

Endpoints com credencial/instância **no path** — acopla o roteamento de provider
à URL, em vez de resolver por configuração da conexão.

## Webhooks de saída

Configurados em `Agents > Settings > Webhooks`. Nove eventos, listados em
[`01-mapa-funcional.md`](01-mapa-funcional.md#9-api-e-extensibilidade).

### Health check na configuração

Antes de salvar, o sistema faz `POST` de teste:

| Condição | Resultado |
|---|---|
| Resposta > 5s | Marcado **"Slow"**, pede endpoint mais rápido |
| Inalcançável ou > 6s | Marcado **"Unreachable"** |
| Falhas consecutivas em uso | **Bloqueio automático**; desbloqueio ao re-salvar a URL |

Isto é notavelmente bem pensado — valida o consumidor no momento da
configuração, em vez de descobrir na produção. Nossa DLQ resolve o mesmo
problema depois do fato; eles resolvem antes.

### Payload

~30 atributos, com inclusão condicional por tipo de evento. Sempre presentes:
`eventType`, `conversationId`, `agentId`, `agentName`, `channel`,
`conversationStatus`, `conversationPriority`, `isAiEnabled`, `organizationId`.

Condicionais notáveis:

- `conversation_variables` — objeto KV do estado da conversa
- `ctwaAttributions[]` — atribuição Click-to-WhatsApp: `ctwaClid`, `sourceId`,
  `sourceType`, `headline`, `body`, `sourceUrl`, `mediaType`, `imageUrl`,
  `videoUrl`, `thumbnailUrl`, `clickedAt`
- `attachments[]` — `id`, `url`, `mimeType`, `size`
- `frustration`, `summary`, `tags`
- `rating`, `comment`, `completionReason`, `completedAt` (só `NPS_INTERACTION`)
- `isStepAgentResponse`, `stepAgentId`, `stepAgentName`

**Não há assinatura HMAC documentada.** Autenticação do webhook é por header
estático opcional — mais fraco que assinatura por payload.

## Webhook de entrada

"Fetch External User Information": URL que o agente chama para enriquecer o
perfil do contato com dados de sistema externo, exibidos na Inbox. Header
opcional.

Padrão de integração que não temos: em vez de sincronizar dados do CRM do
cliente para dentro da plataforma, **busca sob demanda**. Elimina o problema de
sincronização e de retenção de dado de terceiro.

## Integrações nativas

| Integração | Tipo | Como autentica | Notas |
|---|---|---|---|
| **WhatsApp Oficial** | Canal | Embedded Signup (Facebook) | Coexiste com o app WhatsApp Business no celular |
| **Z-API** | Canal | Instance ID | Não-oficial; suporta grupos |
| **Zapper HUB** | Canal | Instance ID | Não-oficial |
| **Instagram** | Canal | App Meta do próprio cliente | DM + comentários |
| **Telegram** | Canal | Token BotFather | |
| **Slack** | Canal | OAuth | DM + menção |
| **Twilio** | Canal | SID + Auth Token + Phone SID | SMS |
| **Mercado Livre** | Canal + dados | OAuth | Perguntas e pós-venda, liga/desliga por produto |
| **Google Drive** | Fonte de dados | OAuth (credencial do cliente) | Sincronização automática; free tier Google = 100 conexões |
| **YouTube** | Fonte de dados | Mesma credencial do Drive | Transcrição de vídeo |
| **Make** | Automação | App custom no Make | API key |
| **Groq** | Transcrição | Chave da organização | BYOK |
| **ElevenLabs** | Voz | Chave da organização | BYOK |

### Padrão BYOK

Chaves de LLM, Groq e ElevenLabs são **do cliente**, não do Chatvolt. A
plataforma orquestra, não revende inferência. Reduz risco de margem e transfere
o custo variável.

Contrapartida: fricção de onboarding (cliente precisa criar conta em três
serviços) e suporte mais difícil.

### Ausências notáveis

- **n8n e Zapier** não têm integração nativa. Só Make.
- Nenhuma integração de e-commerce além do Mercado Livre — sem Shopify,
  WooCommerce, Nuvemshop, VTEX.
- Nenhum ERP ou CRM de mercado (Pipedrive, RD Station, HubSpot).
- Nenhum gateway de pagamento — apesar de Artifacts ser catálogo de produto,
  não há checkout.

## Comparação com a nossa superfície

| | Chatvolt | Chat Nexus |
|---|---|---|
| Endpoints | 112 documentados | **330** (`server/routes/`, 53 módulos) |
| Público para terceiros | Sim, toda a superfície | **Não** — API key só cobre Disparador (escopos `capture`/`dispatch`/`templates`) |
| Autenticação externa | Bearer, sem escopo | Bearer com **escopos** + hash, prefixo indexável, expiração opcional (`shared/api_key.py`) |
| Documentação pública | Mintlify com OpenAPI | Swagger interno, sem portal |
| Webhooks de saída | 9 eventos, health check, auto-bloqueio | **12 eventos**, **retry exponencial + DLQ** (`shared/hook.py`, `hook_dispatcher.py`) |
| Assinatura de webhook | Header estático | Header estático |

A leitura correta desses números não é "temos 3× mais endpoints". É o inverso:
**eles expõem 112 endpoints para clientes construírem em cima; nós expomos 330
para o nosso próprio painel consumir.** Superfície interna não é produto.

O nosso modelo de API key é tecnicamente superior (escopo, hash, expiração) —
está sendo subutilizado num caso de uso só.
