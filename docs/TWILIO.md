# Integração Twilio — Sandbox, Produção e Cutover

Guia completo para configurar envio e recebimento de mensagens WhatsApp via Twilio.
Dividido em duas trilhas: **Parte A** (sandbox/desenvolvimento local) e **Parte B** (número real/produção).

## Visão geral

```
Usuário WhatsApp
       │
       ▼
Twilio (nuvem)
       │  POST /webhook/twilio?agent=rhawk_assistant
       │  X-Twilio-Signature: <HMAC-SHA1>
       ▼
cloudflared tunnel ──► API (localhost:8000)       [Parte A — sandbox/local]
       ou
Domínio Railway ──► API (api-*.up.railway.app)    [Parte B — produção]
                              │
                              ▼
                       PostgreSQL (fila)
                              │
                              ▼
                       Worker ──► TwilioClient.send_typing()
                              │
                              ▼
                       graph.ainvoke()
                              │
                              ▼
                       TwilioClient.send_message() ──► WhatsApp
```

---

# Parte A — Sandbox + Desenvolvimento Local

Tudo o que você precisa para rodar localmente com o sandbox do Twilio.
Nenhuma dependência de número real ou aprovação da Meta.

## A.1 Criar conta Twilio (do zero)

1. Acesse [Twilio Console](https://console.twilio.com/) e clique em **Sign up**.
2. Confirme e-mail e telefone.
3. No onboarding, siga o fluxo padrão até chegar no dashboard.
4. Se sua conta estiver em trial, mantenha o trial ativo (é suficiente para sandbox).

> Dica (Brasil): se a confirmação por SMS falhar, tente validação por ligação de voz.

## A.2 Obter credenciais no Console (SID, Token e API Key)

1. No Dashboard, copie:
   - `Account SID` (começa com `AC`)
   - `Auth Token` (clique em **Show** para revelar)
2. Vá em **Account → API keys & tokens** e clique em **Create API Key**.
3. Preencha:
   - **Friendly name**: ex. `tophawks-whatsapp-worker`
   - **Region**: `United States - Default`
   - **Key type**: prefira `Standard`/`Main` quando disponível.
4. Se só aparecer `Restricted`, selecione permissões mínimas de envio:
   - Produto `Messaging`
   - Recurso `Messages` com permissão `Create` (opcional `Read` para debug)
5. Crie a key e copie:
   - `API Key SID` (começa com `SK`)
   - `API Key Secret`

> O `API Key Secret` aparece apenas uma vez. Guarde imediatamente.

**Onde encontrar cada credencial:**

| Credencial | Onde | Formato |
|---|---|---|
| `Account SID` | [Console → Account Info](https://console.twilio.com/) | `ACxxxxxxxx` |
| `Auth Token` | [Console → Account Info](https://console.twilio.com/) (clique em Show) | 32 chars hex |
| `API Key SID` | Console → Account → API keys & tokens | `SKxxxxxxxx` |
| `API Key Secret` | Exibido ao criar a API Key (única vez) | 32 chars |

## A.3 Variáveis de ambiente (.env para local)

A autenticação Twilio é dividida em dois contextos:

- **Outbound** (Worker → Twilio): usa API Key (`TWILIO_API_KEY_SID` + `TWILIO_API_KEY_SECRET`)
- **Inbound** (validação de assinatura): usa `TWILIO_AUTH_TOKEN`

Configure no `.env`:

```bash
# === Twilio ===
# Account SID (Console → Account Info)
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# --- Outbound (Worker → Twilio Messages API) ---
# mock em dev local / real para envio de verdade
TWILIO_OUTBOUND_MODE=mock

# API Key: Console → Account → API keys & tokens → Create API Key
TWILIO_API_KEY_SID=SKxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_API_KEY_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Número WhatsApp do sandbox (Console → Messaging → Try it out → WhatsApp)
TWILIO_FROM_NUMBER=whatsapp:+14155238886

# --- Inbound (validação de assinatura no webhook) ---
# Auth Token: Console → Account Info (para HMAC-SHA1)
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Habilitar validação de assinatura (false para sandbox local)
VALIDATE_TWILIO_SIGNATURE=false

# URL pública base do túnel — apenas o domínio, sem path
TWILIO_WEBHOOK_URL=
```

Em desenvolvimento local, `TWILIO_OUTBOUND_MODE=mock` permite validar fila,
worker, admin panel e E2E sem consumir cota do sandbox. Para testes reais de
WhatsApp, mude para `TWILIO_OUTBOUND_MODE=real`.

## A.4 Ativar sandbox WhatsApp

1. Acesse [Twilio Console → WhatsApp Sandbox](https://console.twilio.com/us1/develop/sms/try-it-out/whatsapp-learn)
2. Envie a mensagem de ativação (ex: "join \<código\>") do seu celular para o número do sandbox
3. Confirme que o sandbox está ativo (status "Connected")
4. Copie o número do sandbox exibido na tela (ex: `+1 415 523 8886`) e configure:
   - `TWILIO_FROM_NUMBER=whatsapp:+14155238886`

> O sandbox tem validade de 72h. Se parar de funcionar, reenvie a mensagem de ativação.

## A.5 Túnel local com cloudflared

Cloudflared cria um túnel público → localhost sem necessidade de conta Cloudflare.

```bash
# Iniciar túnel (porta da API)
cloudflared tunnel --url http://localhost:8000
```

Saída esperada:
```
INF +----------------------------+
INF |  Your quick Tunnel has been created! Visit it at:
INF |  https://random-name.trycloudflare.com
INF +----------------------------+
```

Copie a URL gerada e configure no `.env`:

```bash
TWILIO_WEBHOOK_URL=https://random-name.trycloudflare.com
```

> A URL muda a cada reinício do cloudflared. Se reiniciar, atualize `.env` e o webhook no Twilio Console.

### Por que cloudflared e não ngrok?

- Zero config: não precisa de conta, token ou login
- Sem limites de rate no free tier
- Mesmo protocolo (HTTPS com cert válido)
- Suporte nativo a HTTP/2

## A.6 Configurar webhook no Twilio (sandbox)

1. Acesse [Twilio Console → WhatsApp Sandbox Settings](https://console.twilio.com/us1/develop/sms/settings/whatsapp-sandbox)
2. Em "When a message comes in", configure:
   ```
   https://random-name.trycloudflare.com/webhook/twilio?agent=rhawk_assistant
   ```
   Metodo: **HTTP POST**
3. Salve

### Validar que o tunnel está funcionando

```bash
curl https://random-name.trycloudflare.com/health
# {"status":"ok","database":"connected","version":"0.1.0"}
```

## A.7 Teste ponta a ponta (sandbox)

### A.7.1 Fluxo simulado (sem Twilio real)

```bash
# Simula o que o Twilio enviaria
curl -X POST "http://localhost:8000/webhook/twilio?agent=rhawk_assistant" \
  -d "MessageSid=SMTEST001" \
  -d "From=whatsapp:+5511999999999" \
  -d "To=whatsapp:+14155238886" \
  -d "Body=Olá, teste local" \
  -d "NumMedia=0"
```

Verifique:
```bash
curl http://localhost:8000/api/chats/+5511999999999
```

> Neste modo, `VALIDATE_TWILIO_SIGNATURE` deve estar `false` (padrão).

### A.7.2 Fluxo real (Twilio + WhatsApp via sandbox)

1. Confirme que todos os serviços estão rodando:
   ```bash
   make logs
   # api, worker e db devem estar healthy
   ```

2. Confirme o túnel:
   ```bash
   curl https://random-name.trycloudflare.com/health
   ```

3. Envie uma mensagem do WhatsApp para o número do sandbox

4. Verifique nos logs:
   ```bash
   make logs
   # Procure por: webhook_twilio_received, message_claimed, twilio_typing_sent, message_processed
   ```

5. A resposta do agente deve chegar no WhatsApp (se as credenciais outbound estiverem configuradas e `TWILIO_OUTBOUND_MODE=real`)

### A.7.3 Habilitar validação de assinatura (opcional no sandbox)

Para testar com validação real:

```bash
VALIDATE_TWILIO_SIGNATURE=true
TWILIO_AUTH_TOKEN=<seu-auth-token>
TWILIO_WEBHOOK_URL=https://random-name.trycloudflare.com
```

Reinicie a API (`make api` ou `docker compose restart api`).

Teste que assinatura inválida é rejeitada:
```bash
curl -X POST "https://random-name.trycloudflare.com/webhook/twilio?agent=rhawk_assistant" \
  -d "MessageSid=SMFAKE" \
  -d "From=whatsapp:+5511999999999" \
  -d "Body=Teste sem assinatura" \
  -d "NumMedia=0"
# Deve retornar 403 (Missing Twilio signature)
```

---

# Parte B — Número Real + Produção

Tudo o que você precisa para operar com número WhatsApp Business real.
Requer aprovação da Meta e deploy em ambiente publicado (Railway).

## B.1 Adquirir número WhatsApp Business

### Pré-requisitos

- Conta Twilio **upgraded** com billing ativo (trial não é suficiente para sender real)
- Conta Meta Business verificada
- Usuário com **controle total / admin** no Meta Business Portfolio que será usado no onboarding
- Número de telefone dedicado (não pode estar registrado em outro WhatsApp)

### Como validar os pré-requisitos antes de começar

#### 1. Confirmar que a conta Twilio saiu de trial

No Twilio Console:
- se ainda aparecer o badge `Trial`, a conta ainda não está pronta para número real
- o upgrade deve ser concluído antes de seguir com `WhatsApp Senders`

#### 2. Confirmar acesso administrativo no Meta Business Portfolio

Na Meta Business Suite:
1. Abra **Configurações**
2. Vá em **Usuários → Pessoas**
3. Localize seu usuário
4. Confirme que o acesso aparece como **Controle total** ou equivalente de admin

Sem esse nível de acesso, o fluxo de self sign-up do Twilio pode travar ao tentar:
- vincular o Business Portfolio
- acessar ativos do negócio
- concluir a configuração do sender

#### 3. Confirmar que o número está livre para a plataforma

O número que será usado no sender real:
- não deve estar ativo no app **WhatsApp**
- não deve estar ativo no app **WhatsApp Business**
- deve conseguir receber OTP por SMS ou ligação durante o onboarding

Se o número já estiver registrado no app, a ativação no Twilio/Meta pode falhar.

### Passo a passo

1. No Twilio Console, vá em **Messaging → Senders → WhatsApp Senders**
2. Clique em **Add WhatsApp Sender**
3. Siga o fluxo de aprovação:
   - Vincular Meta Business Account
   - Informar detalhes do negócio (nome, endereço, site)
   - Submeter o número de telefone para verificação
4. Aguarde aprovação (pode levar de horas a dias dependendo da Meta)

### WhatsApp Business Profile

Após aprovação, configure o perfil do negócio:
- **Display name**: nome que aparece para o usuário no WhatsApp
- **About**: descrição curta do serviço
- **Profile photo**: logo da marca (recomendado 640x640)

### Message Templates (obrigatório para primeira mensagem)

O WhatsApp Business API tem uma regra importante: **você só pode enviar mensagem
proativa (fora da janela de 24h) usando templates pré-aprovados**.

Para o fluxo de webhook (usuário envia primeiro), isso não é blocker — a resposta
do agente cai dentro da janela de 24h. Mas se você precisar enviar a primeira
mensagem, será necessário:

1. Criar templates no Twilio Console → Messaging → Content Template Builder
2. Submeter para aprovação da Meta
3. Usar o template ID no envio

> Para o fluxo padrão deste projeto (webhook inbound → resposta), templates não
> são necessários. O usuário sempre inicia a conversa.

## B.2 Variáveis de ambiente (produção)

Diferenças em relação ao sandbox:

```bash
# Número real no formato whatsapp:+55XXXXXXXXXXX
TWILIO_FROM_NUMBER=whatsapp:+5511999999999

# Envio real obrigatório
TWILIO_OUTBOUND_MODE=real

# Validação de assinatura obrigatória em produção
VALIDATE_TWILIO_SIGNATURE=true

# URL pública da API no Railway (sem path)
TWILIO_WEBHOOK_URL=https://api-production.up.railway.app

# Ambiente
ENVIRONMENT=production
```

Variáveis que **não mudam** entre sandbox e produção:
- `TWILIO_ACCOUNT_SID` (mesmo account)
- `TWILIO_API_KEY_SID` e `TWILIO_API_KEY_SECRET` (mesmas keys)
- `TWILIO_AUTH_TOKEN` (mesmo token, do mesmo account)

## B.3 Configurar webhook (produção / Railway)

Diferente do sandbox, o webhook de produção é configurado em outro lugar do Console:

1. Acesse **Twilio Console → Messaging → WhatsApp Senders**
2. Selecione o número real
3. Em **Webhook URL for incoming messages**, configure:
   ```
   https://api-production.up.railway.app/webhook/twilio?agent=rhawk_assistant
   ```
   Metodo: **HTTP POST**
4. Salve

> No sandbox, o webhook fica em "Sandbox Settings". Em produção, fica nas configurações do sender específico.
> Importante: no Console da Twilio, o sender usa a **URL completa** com
> `/webhook/twilio?agent=...`. Ja a env `TWILIO_WEBHOOK_URL` na API deve conter
> **apenas a base publica** (`https://api-production.up.railway.app`), sem path
> e sem barra final. Misturar esses dois valores quebra a validacao de assinatura.

### Validar o webhook

```bash
# Health check da API em produção
curl https://api-production.up.railway.app/health
# {"status":"ok","database":"connected","version":"0.1.0"}
```

## B.4 Checklist de cutover (sandbox → produção)

### Pré-cutover

- [ ] Número WhatsApp Business aprovado pela Meta
- [ ] WhatsApp Business Profile configurado (nome, foto, about)
- [ ] Conta Twilio com billing ativo (não trial)
- [ ] Deploy no Railway funcionando (API, Worker, Frontend, DB)
- [ ] `GET /health` retornando 200 em produção
- [ ] Admin panel acessível via `/login` em produção
- [ ] `INTERNAL_SERVICE_TOKEN` configurado com valor forte em produção
- [ ] `BETTER_AUTH_SECRET` configurado com valor forte em produção
- [ ] `ADMIN_EMAIL` e `ADMIN_PASSWORD` definidos no Frontend, primeiro login validado e senha trocada em `/settings`

### Execução do cutover

- [ ] Atualizar `TWILIO_FROM_NUMBER` no Worker (Railway) com o número real
- [ ] Atualizar `TWILIO_WEBHOOK_URL` na API (Railway) com o domínio público
- [ ] Habilitar `VALIDATE_TWILIO_SIGNATURE=true` na API (Railway)
- [ ] Confirmar `TWILIO_AUTH_TOKEN` configurado na API (Railway)
- [ ] Configurar webhook no Twilio Console → WhatsApp Senders → número real
- [ ] Redeploy da API e do Worker no Railway

### Pós-cutover (smoke test)

- [ ] Enviar mensagem do WhatsApp para o número real
- [ ] Verificar nos logs do Worker: `webhook_twilio_received` → `message_claimed` → `message_processed`
- [ ] Confirmar resposta do agente no WhatsApp
- [ ] Verificar no admin panel que a conversa aparece em `/chats`
- [ ] Testar assinatura inválida (curl direto sem header) → deve retornar 403
- [ ] Verificar métricas em `/api/metrics`

---

# Referência

## Variáveis por serviço

| Variável | API | Worker | Obrigatória |
|---|---|---|---|
| `DATABASE_URL` | sim | sim | sim |
| `OPENROUTER_API_KEY` | não | sim | sim (para agente) |
| `TWILIO_ACCOUNT_SID` | não | sim | **sim** |
| `TWILIO_API_KEY_SID` | não | sim | **sim** |
| `TWILIO_API_KEY_SECRET` | não | sim | **sim** |
| `TWILIO_FROM_NUMBER` | não | sim | **sim** |
| `TWILIO_AUTH_TOKEN` | sim* | não | se validação ativa |
| `TWILIO_WEBHOOK_URL` | sim* | não | se validação ativa |
| `VALIDATE_TWILIO_SIGNATURE` | sim | não | não (default: false) |

\* Usada pela dependency de validação de assinatura no webhook.

> Em `TWILIO_OUTBOUND_MODE=real`, o Worker faz fail-fast se `TWILIO_ACCOUNT_SID`,
> `TWILIO_API_KEY_SID`, `TWILIO_API_KEY_SECRET` ou `TWILIO_FROM_NUMBER`
> estiverem vazios. Em `mock`, o fluxo assíncrono continua funcional, mas o
> envio outbound é apenas simulado.

## Debounce e mídia

Regras de debounce:

- **Texto**: mensagens rápidas do mesmo phone+agent são agrupadas (concatenadas) dentro da janela de `MESSAGE_BUFFER_SECONDS` (padrão: 2s)
- **Mídia**: entra imediatamente (sem debounce). Antes de inserir mídia, textos pendentes do mesmo phone+agent são "flushed" (processados imediatamente)
- **Ordem**: o worker processa por `created_at ASC`, então texto flushed sai antes da mídia
- **Concorrência**: `pg_advisory_xact_lock(hash(phone+agent))` serializa operações do mesmo remetente/agente, impedindo race conditions entre webhooks simultâneos

Exemplo de fluxo:
```
T=0.0s  Texto "Oi"           → enfileira, process_after=T+2s
T=0.5s  Texto "Olha isso"    → debounce: "Oi\nOlha isso", process_after=T+2.5s
T=1.0s  Imagem (foto.jpg)    → flush texto (process_after=NOW), insere mídia (NOW)
T=1.1s  Worker pega texto    → processa "Oi\nOlha isso"
T=1.2s  Worker pega imagem   → processa foto.jpg
```

### Download de mídia

O worker autentica o download de mídia do Twilio com API Key (`TWILIO_API_KEY_SID` + `TWILIO_API_KEY_SECRET`). Sem autenticação, o download retorna 401 Unauthorized.

## Como a validação de assinatura funciona

O `TWILIO_AUTH_TOKEN` **não é gerado por você** --- é criado pelo Twilio e aparece no
[Console → Account Info](https://console.twilio.com/). É um segredo que só você e o
Twilio conhecem.

A cada POST no webhook, o Twilio calcula um HMAC-SHA1 usando:

1. O `Auth Token` (segredo compartilhado)
2. A URL completa do webhook (incluindo query params como `?agent=rhawk_assistant`)
3. Os parâmetros POST ordenados alfabeticamente (`Body`, `From`, `MessageSid`, etc.)

O resultado vai no header `X-Twilio-Signature` do request.

```
Twilio                                      Sua API
  │                                            │
  │  POST /webhook/twilio?agent=rhawk_assistant │
  │  X-Twilio-Signature: "abc123..."           │
  │  Body=Ola&From=whatsapp:+5511...           │
  │────────────────────────────────────────────>│
  │                                            │
  │                         1. Extrai X-Twilio-Signature do header
  │                         2. Reconstroi a URL pública via TWILIO_WEBHOOK_URL
  │                            (necessário porque atrás de proxy a URL interna
  │                             é http://0.0.0.0:8000, não a URL pública)
  │                         3. Recalcula o HMAC-SHA1 com:
  │                            - TWILIO_AUTH_TOKEN (mesmo segredo)
  │                            - URL reconstruída
  │                            - parâmetros POST
  │                         4. Compara os dois hashes:
  │                            match → 200 (aceita)
  │                            não match → 403 (rejeita)
```

**Por que é seguro?** Sem o `Auth Token`, ninguém consegue forjar a assinatura. Se alguém
tentar fazer POST direto no seu webhook (ex: bot malicioso), o HMAC não vai bater e a API
retorna 403. O token nunca trafega na rede --- só o hash derivado dele.

**Por que `TWILIO_WEBHOOK_URL` é obrigatório em produção?** Atrás de proxy (Railway,
cloudflared), o `request.url` interno mostra `http://0.0.0.0:8000/...`, mas o Twilio
assinou usando a URL pública `https://api-*.up.railway.app/...`. Se a URL não bater na
reconstrução, o HMAC diverge e a validação falha com 403 --- mesmo sendo um request
legítimo do Twilio.

## Limitações conhecidas

### NumMedia > 1

Se o Twilio enviar um webhook com `NumMedia > 1` (múltiplas mídias no mesmo webhook), apenas a primeira mídia (`MediaUrl0`, `MediaContentType0`) é processada. As demais são ignoradas.

Este é um tradeoff consciente --- o template educacional foca em clareza do fluxo single-media. Suporte a multi-media pode ser adicionado em fases futuras.

### Typing indicator

O `TwilioClient.send_typing()` usa o endpoint **Public Beta** do Twilio (lançado out/2025):

```
POST https://messaging.twilio.com/v2/Indicators/Typing.json
```

Parâmetros: `messageId` (SID da mensagem inbound) + `channel=whatsapp`.

Efeitos no WhatsApp do usuário:
- Mensagem marcada como lida (blue checkmarks)
- Indicador "digitando..." exibido por até 25 segundos

O typing é **best-effort**: chamado antes de `graph.ainvoke()`, falha não interrompe processamento. Auth via API Key (mesmas credenciais do envio de mensagens).

> Public Beta: endpoint pode mudar antes do GA. Não é coberto pelo SLA do Twilio.

### Sandbox WhatsApp

- Validade de 72h (requer reativação periódica)
- Apenas números previamente cadastrados recebem mensagens
- Rate limits mais restritivos que produção

### Janela de 24h (produção)

Em produção com número real, o WhatsApp Business API impõe uma **janela de 24 horas**:
- Após o usuário enviar uma mensagem, você pode responder livremente por 24h
- Após 24h sem interação, só pode enviar mensagens usando **templates pré-aprovados**
- Para o fluxo webhook deste projeto (usuário inicia), isso raramente é um problema
- Mas se o processamento demorar mais de 24h (ex: fila congestionada), a resposta pode falhar

---

# Troubleshooting

## Sandbox

### Mensagem não chega no WhatsApp

1. Verifique credenciais Twilio no `.env`
2. Confirme que o sandbox está ativo (reenvie "join \<código\>")
3. Verifique logs do worker: `make logs | grep twilio`
4. Confirme que `TWILIO_ACCOUNT_SID`, `TWILIO_API_KEY_SID`, `TWILIO_API_KEY_SECRET` e `TWILIO_FROM_NUMBER` estão preenchidos

### 403 no webhook

- `VALIDATE_TWILIO_SIGNATURE=true` mas `TWILIO_AUTH_TOKEN` vazio → configure o token
- `TWILIO_WEBHOOK_URL` não bate com a URL real do cloudflared → atualize após reiniciar túnel

### cloudflared desconecta

O tunnel efêmero do cloudflared pode cair. Reinicie e atualize:
1. `cloudflared tunnel --url http://localhost:8000`
2. Copie a nova URL para `TWILIO_WEBHOOK_URL` no `.env`
3. Atualize o webhook no Twilio Console
4. Reinicie a API

### Worker não inicia (fail-fast)

O worker faz fail-fast se credenciais outbound estiverem faltando. Verifique:
```bash
grep -E '^TWILIO_(ACCOUNT_SID|API_KEY_SID|API_KEY_SECRET|FROM_NUMBER)' .env
```

### Identidade inbound

O webhook usa `From` (formato `whatsapp:+55...`) como identidade primária, com fallback para `WaId` (normalizado para `+E.164`). Se o phone_number chega incorreto, verifique o payload do Twilio nos logs.

## Produção

### 403 em produção (assinatura inválida)

Causas mais comuns:
1. **TWILIO_WEBHOOK_URL incorreta**: deve ser a URL pública exata da API (sem path, sem barra final)
   - Correto: `https://api-production.up.railway.app`
   - Errado: `https://api-production.up.railway.app/` (barra final)
   - Errado: `https://api-production.up.railway.app/webhook/twilio` (com path)
2. **Webhook salvo no sender com URL divergente**: no Twilio Console, o campo
   **Webhook URL for incoming messages** precisa apontar para a URL completa do
   sender:
   - Correto: `https://api-production.up.railway.app/webhook/twilio?agent=rhawk_assistant`
   - Errado: deixar vazio, usar outro dominio ou esquecer o query param `agent=...`
3. **Redeploy alterou o domínio**: se o Railway gerou novo domínio, atualize
   tanto `TWILIO_WEBHOOK_URL` na API quanto o webhook salvo no sender da Twilio
4. **Auth Token desatualizado**: se você regenerou o Auth Token no Twilio Console,
   atualize no Railway

### Mensagem não chega em produção

1. Verifique se o número real está aprovado e ativo no Twilio Console
2. Confirme que o webhook está configurado em **WhatsApp Senders** (não em Sandbox Settings)
3. Verifique logs no Railway: `railway logs --service worker`
4. Confirme que `TWILIO_OUTBOUND_MODE=real` no Worker

### Resposta demora ou não chega

1. Verifique o LLM rate limit (`LLM_RATE_LIMIT_REQUESTS_PER_SECOND`)
2. Verifique se o Worker está healthy no Railway
3. Confira se a fila está congestionada: `curl -H "Authorization: Bearer $TOKEN" https://api/api/queue`

### Template rejection (mensagem fora da janela)

Se tentar enviar mensagem após 24h sem interação do usuário:
- O Twilio retorna erro 63016 ("Message failed to send because more than 24 hours have passed since the customer last replied")
- Solução: usar templates pré-aprovados ou aguardar o usuário iniciar nova conversa

## Rollback: produção → sandbox

Se precisar reverter para o sandbox após ativar produção:

1. **Twilio Console**: reconfigurar webhook em **Sandbox Settings** (não em WhatsApp Senders)
   ```
   https://random-name.trycloudflare.com/webhook/twilio?agent=rhawk_assistant
   ```
2. **Railway (Worker)**: reverter variáveis
   ```bash
   TWILIO_FROM_NUMBER=whatsapp:+14155238886
   TWILIO_OUTBOUND_MODE=mock  # ou real se quiser testar envio pelo sandbox
   ```
3. **Railway (API)**: reverter validação
   ```bash
   VALIDATE_TWILIO_SIGNATURE=false
   TWILIO_WEBHOOK_URL=  # limpar ou apontar para cloudflared
   ```
4. Redeploy API e Worker no Railway
5. Reativar sandbox no celular (enviar "join \<código\>" novamente se expirou)

> O rollback não afeta dados. Mensagens já processadas permanecem no banco.
> Conversas existentes continuam acessíveis no admin panel.
