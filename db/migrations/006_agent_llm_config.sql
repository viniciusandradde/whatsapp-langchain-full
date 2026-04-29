-- Configuração por agente do modelo LLM. NULL = usa env defaults.
CREATE TABLE IF NOT EXISTS agent_llm_config (
    agent_id TEXT PRIMARY KEY,
    chat_model TEXT,
    midia_model TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
