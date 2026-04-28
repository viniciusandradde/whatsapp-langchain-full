# Guia: Testando e Debugando o Sistema Manualmente

Este guia ensina como usar a interface Swagger (`/docs`) para enviar mensagens
e depois verificar o resultado diretamente no banco de dados.

## Passo 0: Subir a Stack

```bash
make up
```

Aguarde todos os serviços ficarem saudáveis:

```bash
curl http://localhost:8000/health
# {"status":"ok","database":"connected","version":"0.1.0"}
```

---

## Passo 1: Abrir o Swagger UI

Acesse no navegador:

```
http://localhost:8000/docs
```

Você verá todos os endpoints documentados com formulários interativos.

---

## Passo 2: Enviar uma Mensagem via Webhook

1. No Swagger, localize **POST /webhook/twilio**
2. Clique em **Try it out**
3. No campo `agent` (query param), digite: `rhawk_assistant`
4. No corpo (form data), preencha:

| Campo | Valor |
|---|---|
| `MessageSid` | `SM_TESTE_001` |
| `From` | `whatsapp:+5511999990001` |
| `To` | `whatsapp:+14155238886` |
| `Body` | `Olá! O que vocês fazem?` |
| `NumMedia` | `0` |

5. Clique em **Execute**
6. A resposta deve ser **200** com TwiML vazio:
   ```xml
   <?xml version="1.0" encoding="UTF-8"?><Response></Response>
   ```

> O 200 significa apenas que a mensagem foi **enfileirada**. O processamento
> acontece no Worker em background.

---

## Passo 3: Verificar no Banco de Dados

Conecte ao PostgreSQL:

```bash
docker compose exec db psql -U postgres -d whatsapp_langchain
```

### 3.1 — Ver a mensagem na fila

```sql
SELECT id, phone_number, agent_id, status, incoming_message, response, error
FROM message_queue
WHERE message_id = 'SM_TESTE_001';
```

**O que observar:**

| `status` | Significado |
|---|---|
| `queued` | Na fila, aguardando o Worker |
| `processing` | Worker pegou, está processando |
| `done` | Processado com sucesso — `response` tem a resposta da IA |
| `failed` | Erro — `error` tem o motivo |

> Rode a query mais de uma vez para acompanhar a transição de status em tempo real.

### 3.2 — Ver a resposta da IA

```sql
SELECT incoming_message, response, processed_at
FROM message_queue
WHERE message_id = 'SM_TESTE_001' AND status = 'done';
```

### 3.3 — Ver a conversa criada

```sql
SELECT phone_number, agent_id, message_count, last_message, last_message_at
FROM conversations
WHERE phone_number = '+5511999990001';
```

`message_count` incrementa a cada mensagem processada.

---

## Passo 4: Enviar Follow-up (Conversa Multi-turno)

Volte ao Swagger e envie outra mensagem do **mesmo telefone**:

| Campo | Valor |
|---|---|
| `MessageSid` | `SM_TESTE_002` |
| `From` | `whatsapp:+5511999990001` |
| `Body` | `Como posso aprender mais sobre agentes?` |

Depois verifique:

```sql
-- A resposta deve considerar o contexto da conversa anterior
SELECT incoming_message, response
FROM message_queue
WHERE phone_number = '+5511999990001' AND status = 'done'
ORDER BY created_at;

-- message_count deve ter incrementado para 2
SELECT message_count FROM conversations WHERE phone_number = '+5511999990001';
```

---

## Passo 5: Testar o Debounce

Envie **3 mensagens rápidas** (uma atrás da outra, sem esperar) com o mesmo telefone
e **MessageSids diferentes**:

1. `SM_DEB_01` — Body: `Oi`
2. `SM_DEB_02` — Body: `Tudo bem?`
3. `SM_DEB_03` — Body: `Quero saber sobre LangGraph`

Depois verifique:

```sql
-- Quantas entradas na fila? Se o debounce funcionou, deve ser 1 (não 3)
SELECT COUNT(*) FROM message_queue
WHERE phone_number = '+5511999990002' AND agent_id = 'rhawk_assistant';

-- O texto ficou concatenado?
SELECT incoming_message FROM message_queue
WHERE phone_number = '+5511999990002'
ORDER BY created_at DESC LIMIT 1;
```

O `incoming_message` deve conter as 3 mensagens separadas por `\n`:

```
Oi
Tudo bem?
Quero saber sobre LangGraph
```

---

## Passo 6: Testar Memória Semântica

### 6.1 — Salvar uma memória

Envie via Swagger:

| Campo | Valor |
|---|---|
| `MessageSid` | `SM_MEM_01` |
| `From` | `whatsapp:+5511999990003` |
| `Body` | `Use save_memory e salve: meu código secreto é ALPHA-7742` |

Aguarde `status = done`, depois verifique no store:

```sql
SELECT key, value->>'memory' AS memoria
FROM store
WHERE prefix = '+5511999990003.memories';
```

### 6.2 — Recuperar sem histórico

Limpe os checkpoints para simular uma nova sessão:

```sql
DELETE FROM checkpoint_writes WHERE thread_id = '+5511999990003:rhawk_assistant';
DELETE FROM checkpoints WHERE thread_id = '+5511999990003:rhawk_assistant';
```

Envie nova mensagem pedindo recall:

| Campo | Valor |
|---|---|
| `MessageSid` | `SM_MEM_02` |
| `From` | `whatsapp:+5511999990003` |
| `Body` | `Use read_memory e me diga qual é meu código secreto` |

Verifique se a resposta contém `ALPHA-7742`:

```sql
SELECT response FROM message_queue
WHERE message_id = 'SM_MEM_02' AND status = 'done';
```

---

## Passo 7: Verificar via API Admin

Sem sair do Swagger, teste os endpoints admin:

| Endpoint | O que mostra |
|---|---|
| `GET /api/agents` | Agentes disponíveis (`rhawk_assistant`) |
| `GET /api/chats` | Lista de conversas com `message_count` |
| `GET /api/chats/+5511999990001` | Mensagens de um telefone específico |
| `GET /api/metrics` | `total_today`, `queue_size`, `failures_today` |

---

## Queries Úteis para Debug

```sql
-- Mensagens com erro (por que falharam?)
SELECT phone_number, incoming_message, error, attempts
FROM message_queue WHERE status = 'failed';

-- Mensagens presas em processing (worker morreu?)
SELECT id, phone_number, lease_until, attempts
FROM message_queue WHERE status = 'processing';

-- Todas as memórias salvas
SELECT prefix, key, value->>'memory' AS memoria
FROM store ORDER BY updated_at DESC LIMIT 10;

-- Checkpoints ativos (threads com histórico)
SELECT DISTINCT thread_id FROM checkpoints;

-- Fila em tempo real (rode várias vezes para acompanhar)
SELECT status, COUNT(*) FROM message_queue GROUP BY status;
```

---

## Limpeza

Para resetar tudo e começar do zero:

```bash
make reset
```

Isso destrói volumes, rebuilda containers e reaplica migrações.
