-- Adiciona empresa_id (FK pra empresa) em todas as entidades operacionais
-- existentes. Default 1 (VSA Tech) durante backfill — uma migration futura
-- pode dropar o DEFAULT depois que o ingresso de novas empresas estabilizar.

ALTER TABLE conversations
    ADD COLUMN IF NOT EXISTS empresa_id BIGINT NOT NULL DEFAULT 1
    REFERENCES empresa(id) ON DELETE RESTRICT;

ALTER TABLE message_queue
    ADD COLUMN IF NOT EXISTS empresa_id BIGINT NOT NULL DEFAULT 1
    REFERENCES empresa(id) ON DELETE RESTRICT;

ALTER TABLE agent_llm_config
    ADD COLUMN IF NOT EXISTS empresa_id BIGINT NOT NULL DEFAULT 1
    REFERENCES empresa(id) ON DELETE RESTRICT;

-- Reescreve PK do agent_llm_config pra (empresa_id, agent_id) — agora cada
-- empresa tem suas próprias overrides de modelo por agente.
ALTER TABLE agent_llm_config DROP CONSTRAINT IF EXISTS agent_llm_config_pkey;
ALTER TABLE agent_llm_config ADD PRIMARY KEY (empresa_id, agent_id);

-- Indexes pra perf das queries hot path:
-- - listagem de chats em /api/chats (ORDER BY last_message_at)
-- - claim do worker (WHERE status='queued' ORDER BY process_after)
CREATE INDEX IF NOT EXISTS idx_conversations_empresa
    ON conversations (empresa_id, last_message_at DESC);

CREATE INDEX IF NOT EXISTS idx_message_queue_empresa_status
    ON message_queue (empresa_id, status, process_after);
