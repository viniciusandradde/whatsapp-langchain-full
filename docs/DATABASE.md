# Banco de Dados

Este documento explica as tabelas do projeto e traz queries de inspeção
para validação operacional (fila, conversa e memória semântica via tools).

## Visão Geral

O PostgreSQL guarda três blocos de dados:

1. Tabelas de aplicação (`message_queue`, `conversations`, `_migrations`)
2. Tabelas de checkpointer do LangGraph (`checkpoints`, `checkpoint_writes`, `checkpoint_blobs`, `checkpoint_migrations`)
3. Tabelas de memória semântica (`store`, `store_vectors`, `store_migrations`, `vector_migrations`)

## Tabelas de Aplicação

### `_migrations`

Controle das migrações SQL locais (`db/migrations/*.sql`).

### `message_queue`

Fila operacional de mensagens.

Campos principais:
- `message_id`: id externo (ex: Twilio MessageSid)
- `phone_number`, `agent_id`, `thread_id`
- `incoming_message`: entrada original
- `media_url`, `media_type`
- `normalized_input`: texto final enviado ao agente (quando houver)
- `media_processing_status`: `none | processed | disabled | failed | unsupported`
- `media_processing_error`: erro de pré-processamento de mídia
- `status`: `queued | processing | done | failed`
- `response`, `error`, `attempts`, `max_attempts`, `process_after`

### `conversations`

Resumo por conversa (`phone_number + agent_id`) para o painel/admin.

## Tabelas do LangGraph

### `checkpoints`

Snapshots do estado por `thread_id`.

### `checkpoint_writes`

Eventos incrementais por canal (inclui canal `messages`).
O payload fica em `blob` (msgpack).

### `checkpoint_blobs`

Blobs auxiliares do checkpointer.

### `checkpoint_migrations`

Controle interno de schema do checkpointer.

## Tabelas de Memória Semântica

### `store`

Memórias em JSON por namespace/prefix.
Para este projeto, padrão:
- `prefix = "<user_id>.memories"`
- sem namespaces de tenant (`tenant_user`/`tenant_shared`)

### `store_vectors`

Embeddings vetoriais da `store` (HNSW + `vector`).

### `store_migrations` e `vector_migrations`

Controle interno de schema da store vetorial.

## Queries Prontas

### 1) Quais formatos de mídia chegaram

```sql
SELECT media_type, COUNT(*) AS total
FROM message_queue
WHERE media_type IS NOT NULL
GROUP BY media_type
ORDER BY total DESC;
```

### 2) Histórico completo de uma conversa (fila + resposta)

```sql
SELECT
  id,
  message_id,
  phone_number,
  media_type,
  media_processing_status,
  status,
  incoming_message,
  normalized_input,
  response,
  media_processing_error,
  error,
  created_at,
  processed_at
FROM message_queue
WHERE phone_number = '+5511999999999'
ORDER BY id DESC;
```

### 3) Memórias salvas de um usuário

```sql
SELECT
  prefix,
  key,
  value->>'memory' AS memory,
  created_at
FROM store
WHERE prefix = '+5511999999999.memories'
ORDER BY created_at DESC;
```

### 4) Evidência de save no store (memória durável por usuário)

```sql
SELECT
  prefix,
  key,
  value->>'memory' AS memory,
  updated_at
FROM store
WHERE prefix = '+5511999999999.memories'
ORDER BY updated_at DESC
LIMIT 20;
```

### 5) Evidência de recall no output (resposta final ao usuário)

```sql
SELECT
  id,
  message_id,
  phone_number,
  status,
  left(response, 220) AS response_preview,
  created_at
FROM message_queue
WHERE phone_number = '+5511999999999'
  AND status = 'done'
ORDER BY id DESC
LIMIT 20;
```

### 6) Inspeção técnica das mensagens persistidas no checkpoint

```sql
SELECT
  checkpoint_id,
  channel,
  type,
  octet_length(blob) AS bytes,
  left(encode(blob, 'escape'), 600) AS blob_preview
FROM checkpoint_writes
WHERE thread_id = '+5511999999999:rhawk_assistant'
  AND channel = 'messages'
ORDER BY checkpoint_id DESC
LIMIT 20;
```

### 7) Conversas mais recentes (visão painel)

```sql
SELECT
  phone_number,
  agent_id,
  thread_id,
  last_message,
  last_message_at,
  message_count
FROM conversations
ORDER BY last_message_at DESC
LIMIT 50;
```

## Observações

- `conversations` mostra apenas resumo; não mostra detalhes de save/recall.
- Save de memória é observado em `store` (`prefix = "<user_id>.memories"`).
- Recall é observado no output final (`message_queue.response`) e nos logs do worker (`memory_read`).
- `message_queue.status='done'` significa ciclo encerrado com resposta ao usuário,
  inclusive respostas automáticas quando mídia está desabilitada ou falha.
