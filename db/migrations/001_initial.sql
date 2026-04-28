-- 001_initial.sql
-- Schema inicial: fila de mensagens e conversas.
--
-- pgvector habilitado para memória semântica futura (INT-202).
-- A extensão é criada aqui mas não usada até a implementação de embeddings.

-- Extensão pgvector (requer imagem pgvector/pgvector)
CREATE EXTENSION IF NOT EXISTS vector;

-- Tabela de controle de migrações
CREATE TABLE IF NOT EXISTS _migrations (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Fila de mensagens para processamento assíncrono.
-- O Worker consome mensagens com status 'queued' e process_after <= NOW().
-- Usa FOR UPDATE SKIP LOCKED para concorrência segura entre múltiplos workers.
CREATE TABLE message_queue (
    id                SERIAL PRIMARY KEY,
    message_id        TEXT,                           -- ID externo (ex: Twilio MessageSid)
    phone_number      TEXT NOT NULL,                  -- Remetente (E.164)
    to_number         TEXT,                           -- Destinatário
    agent_id          TEXT NOT NULL,                  -- Agente que vai processar
    thread_id         TEXT NOT NULL,                  -- ID do thread: phone:agent_id
    incoming_message  TEXT NOT NULL,                  -- Texto da mensagem (pode ser concatenado via debounce)
    media_url         TEXT,                           -- URL de mídia anexada
    media_type        TEXT,                           -- MIME type da mídia
    status            TEXT NOT NULL DEFAULT 'queued', -- queued | processing | done | failed
    process_after     TIMESTAMPTZ NOT NULL DEFAULT NOW(), -- Debounce: só processar após este timestamp
    attempts          INTEGER NOT NULL DEFAULT 0,     -- Tentativas de processamento
    max_attempts      INTEGER NOT NULL DEFAULT 3,     -- Máximo de tentativas
    lease_until       TIMESTAMPTZ,                    -- Lock: worker tem até este momento para processar
    response          TEXT,                           -- Resposta do agente (preenchida no done)
    error             TEXT,                           -- Erro (preenchido no failed)
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at      TIMESTAMPTZ                     -- Quando foi processada
);

-- Índice principal para polling do Worker:
-- Busca mensagens prontas para processar, ordenadas por criação.
CREATE INDEX idx_queue_polling
    ON message_queue (status, process_after, created_at)
    WHERE status = 'queued';

-- Índice para buscar mensagens de um telefone+agente (debounce e admin)
CREATE INDEX idx_queue_phone_agent
    ON message_queue (phone_number, agent_id, status);

-- Índice para ordenação cronológica (admin)
CREATE INDEX idx_queue_created
    ON message_queue (created_at DESC);

-- Tabela de conversas: agrega dados de cada par telefone+agente.
-- Atualizada a cada mensagem processada via UPSERT.
CREATE TABLE conversations (
    id                SERIAL PRIMARY KEY,
    phone_number      TEXT NOT NULL,
    agent_id          TEXT NOT NULL,
    thread_id         TEXT NOT NULL,
    last_message      TEXT NOT NULL,
    last_message_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    message_count     INTEGER NOT NULL DEFAULT 0,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (phone_number, agent_id)
);
