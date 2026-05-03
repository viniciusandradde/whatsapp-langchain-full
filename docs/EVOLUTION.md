# Integração Evolution API

Provider WhatsApp não-oficial baseada em Baileys (open-source). Útil
quando WABA oficial não é viável (custo, número antigo, BYO-instance).
Implementado em **M2.b** (commits `dbcded5`..`bc719be` na branch
`feat/m2b-evolution-provider`).

> **Não-oficial** — a Evolution usa engenharia reversa do WhatsApp Web
> via Baileys. Pode quebrar a qualquer release do WhatsApp e violar os
> ToS deles. Use com consciência do risco. WABA oficial continua sendo
> a opção production-grade.

---

## Como funciona

```text
WhatsApp ⇆ Evolution server ⇆ webhook POST → API (/webhook/evolution)
                                          → fila Postgres
                                          → Worker resolve provider
                                          → EvolutionClient.send_message
                                          → Evolution → WhatsApp
```

A abstração `OutboundClient` (`worker/outbound_client.py`) define o
contrato comum a Twilio e Evolution. O worker monta um dict
`{provider: cliente}` e roteia cada mensagem por
`MessageQueue.conexao_provider` (resolvido no `claim_next` via subquery
em `conexao.provider`).

Multi-instância: cada conexão Evolution carrega seu `instance_name` em
`conexao.payload_json` — o webhook resolve a conexão via
`get_conexao_by_evolution_instance(payload.instance)` e o
EvolutionClient correspondente envia outbound pra essa instância.

---

## Setup

### 1. Variáveis de ambiente

```bash
EVOLUTION_API_URL=https://evolutionapi.exemplo.com.br
EVOLUTION_API_KEY=xxxxxxxx
EVOLUTION_INSTANCE_NAME=minha-empresa
EVOLUTION_PHONE_NUMBER=+5511999999999
EVOLUTION_OUTBOUND_MODE=real           # ou mock em dev
EVOLUTION_VALIDATE_APIKEY=false        # true em prod (se Evolution mandar header)
```

`EVOLUTION_OUTBOUND_MODE=mock` simula envios sem chamar HTTP — bom em dev.

### 2. Migration

```bash
make migrate
```

`db/migrations/020_evolution_provider.sql` relaxa o CHECK de
`conexao.provider` pra aceitar `'evolution'` além dos providers Twilio.

### 3. Cadastrar conexão

Painel → **Conexões** → Nova conexão:

| Campo | Valor |
|---|---|
| Provider | Evolution API (não-oficial) |
| From number | `+5511999999999` (E.164) |
| Default agent | `vsa_tech` (ou outro do catálogo) |
| Instance name | `minha-empresa` |
| API URL/key (testar) | só para clicar em "Testar conexão" — não persiste |

O botão **Testar conexão** chama
`POST /api/conexoes/test-evolution` que faz `GET
/instance/connectionState/{instance}` na Evolution e retorna `state`
(deve ser `open` ou `connecting`).

### 4. Configurar webhook na Evolution

A Evolution só dispara `MESSAGES_UPSERT` se o webhook estiver registrado
**na instância**. Use a API oficial:

```bash
curl -X POST "$EVOLUTION_API_URL/webhook/set/$INSTANCE" \
  -H "apikey: $EVOLUTION_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "webhook": {
      "enabled": true,
      "url": "https://chat.exemplo.com/webhook/evolution",
      "events": ["MESSAGES_UPSERT"],
      "webhookByEvents": false,
      "webhookBase64": false
    }
  }'
```

Validar:

```bash
curl "$EVOLUTION_API_URL/webhook/find/$INSTANCE" -H "apikey: $EVOLUTION_API_KEY"
```

> ⚠️ **Eventos só em UPPERCASE_UNDERSCORED** (`MESSAGES_UPSERT`,
> `SEND_MESSAGE`, `CONNECTION_UPDATE`). A Evolution v2 rejeita
> `messages.upsert` minúsculo com 400.

### 5. Smoke test

Mande mensagem real do seu WhatsApp pessoal pro número da instância.
Logs esperados (worker + api):

```
webhook_evolution_received  phone=+55... instance=...
processing_message          agent_id=vsa_tech
evolution_message_sent      message_id=BAE5...
message_processed
```

E o cliente recebe a resposta no WhatsApp.

---

## Webhook payload (referência)

```json
{
  "event": "messages.upsert",
  "instance": "minha-empresa",
  "data": {
    "key": {
      "remoteJid": "5511999999999@s.whatsapp.net",
      "fromMe": false,
      "id": "BAE5..."
    },
    "message": { "conversation": "Olá!" },
    "pushName": "Cliente",
    "messageTimestamp": "1730000000"
  }
}
```

### LID (Linked Identity)

WhatsApp recente envia `key.remoteJid` em formato `<id>@lid` (id opaco
interno) e o número real em `key.remoteJidAlt`:

```json
"key": {
  "remoteJid": "264067625254915@lid",
  "remoteJidAlt": "5511999999999@s.whatsapp.net",
  "addressingMode": "lid",
  "id": "...",
  "fromMe": false
}
```

`_resolve_sender_phone` (em `evolution_webhook.py`) prefere
`remoteJidAlt` quando `addressingMode == "lid"` ou
`remoteJid.endswith("@lid")`. Sem esse fix, mensagens via LID criariam
clientes com números fantasma.

### Tipos de mensagem suportados (MVP)

- `data.message.conversation` — texto curto
- `data.message.extendedTextMessage.text` — texto com link/preview

Mídia (`imageMessage`, `audioMessage`, `videoMessage`, `stickerMessage`)
ainda não suportada — webhook responde 200 e ignora silently. **TODO
M2.b.1**.

---

## Outbound client

`worker/evolution_client.py::EvolutionClient`:

| Método | Endpoint | Body |
|---|---|---|
| `send_message(to, body)` | `POST /message/sendText/{instance}` | `{number, text}` |
| `send_typing(to)` | `POST /chat/sendPresence/{instance}` | `{number, options:{delay,presence:composing,number}}` |

- Header `apikey` em todas as chamadas
- Mock mode (`delivery_mode=mock`) retorna `mock-evo-<uuid>` sem HTTP
- 4xx/5xx → `EvolutionSendError` → entra no fluxo de retry do worker
- send_typing é best-effort — exceções viram `False` sem derrubar pipeline

Número destino é normalizado em `normalize_to_number`: aceita
`+5511...`, `whatsapp:+5511...` ou já dígitos puros, devolve só
dígitos (formato exigido pela Evolution).

Splitting universal de 1600 chars (mesmo do Twilio) — defensivo contra
truncamento da Evolution server-side.

---

## Pegadinhas em produção

### IP privado do destino

Se o seu domínio público (ex: `chat.empresa.com.br`) resolve pra IP
**RFC1918** (`10.x`, `172.16-31.x`, `192.168.x`), a Evolution server
hospedada externamente **não consegue alcançar**. Webhook nunca
chega — sem erro, só silêncio.

Diagnóstico:

```bash
host chat.empresa.com.br 1.1.1.1
# Se retornar 10.x.x.x ou 192.168.x.x → DNS público aponta pra IP privado, BUG
```

Solução: o domínio público tem que resolver pra IP **público** + reverse
proxy nesse IP encaminhando pra rede interna. Ou use um tunnel
(Cloudflare Tunnel, ngrok, frp).

### Reverse proxy roteando por path

`/webhook/evolution` precisa cair na **API** (porta 8000), não no
frontend (3000). No Nginx Proxy Manager: aba **Custom Locations** do
host:

- Location: `/webhook/evolution` → `http://api-host:8000`
- Location: `/webhook/twilio` → `http://api-host:8000`

Sem isso, o frontend Next.js intercepta e retorna `307 → /login`.

### Webhook silenciosamente sobrescrito

Algumas instalações da Evolution rodam com `WEBHOOK_GLOBAL_*` env vars
ativas — quando uma URL global está configurada, ela pode coexistir
com per-instance ou suprimir dependendo da versão. Se webhook
configurado via `/webhook/set/{instance}` não dispara:

1. Confirma no `webhook/find/{instance}` que a config persistiu
2. Aponta temporariamente pra `https://webhook.site/<uuid>` e dispara
   um `SEND_MESSAGE` (envia uma mensagem da instância pra ela mesma) —
   se chega no webhook.site, a Evolution está disparando OK e o
   problema é alcançabilidade do destino real.

### Envios travados em retry

Quando `send_message` falha (ex: número não existe), o worker faz
backoff progressivo (5s, 10s, 15s) até `MAX_ATTEMPTS=3` e marca como
`failed`. Se quiser cancelar manualmente:

```sql
UPDATE message_queue
   SET status='failed', attempts=99, error='canceled'
 WHERE id = <id>;
```

---

## Tests

| Arquivo | Cobertura |
|---|---|
| `tests/unit/test_evolution_client.py` (28) | init validation, payload format, 4xx/5xx → erro, splitting, mock, typing best-effort |
| `tests/unit/test_evolution_webhook.py` (15) | happy path, fromMe, eventos não-upsert, instance unknown, LID com/sem addressingMode, validação apikey |
| `tests/unit/test_processor_twilio.py::TestProviderRouting` (4) | roteamento por `conexao_provider` + fallback default |

Total **+47 testes** introduzidos em M2.b. Suite global passa de 495 →
542 passed (6 failures pré-existentes não relacionados).

```bash
uv run pytest tests/unit/test_evolution_client.py tests/unit/test_evolution_webhook.py -v
```
