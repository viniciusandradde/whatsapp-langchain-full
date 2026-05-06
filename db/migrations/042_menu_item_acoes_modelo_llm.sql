-- Sub-fase B+ — Paridade ZigChat (ações expandidas + catálogo LLM).
--
-- Documentação: docs/zigchat/depara/03_gap_grande.md + 04_pendentes_criar.md
--
-- Adiciona ao menu_item:
--   - comando: alias texto da escolha (ex: "vendas" funciona como "1")
--   - acao_atendente_id: transferir pra atendente específico (FK auth.user)
--   - acao_modelo_mensagem_id: disparar template de resposta rápida
--   - webhook_url + hook_id: chamar URL externa
--   - link_url: enviar link/URL pro cliente
--   - nota_min + nota_max + nota_pergunta: pesquisa CSAT (escala 1-5, 1-10, etc)
--   - grupo: agrupador visual no editor
--
-- Expande CHECK acao_tipo de 5 → 12 valores:
--   MVP (mig 040): submenu, transferir_dep, chamar_agente, enviar_msg, fechar
--   B+ (mig 042): transferir_atendente, enviar_template, chamar_webhook,
--                 enviar_link, pesquisa_csat, mudar_manual, setar_nome
--
-- Cria modelo_llm: catálogo de modelos LLM com custo (governança).

-- ---- Expand menu_item ----
ALTER TABLE menu_item
    ADD COLUMN IF NOT EXISTS comando TEXT,
    -- TEXT pq Better Auth user IDs são string
    ADD COLUMN IF NOT EXISTS acao_atendente_id TEXT,
    ADD COLUMN IF NOT EXISTS acao_modelo_mensagem_id BIGINT,
    ADD COLUMN IF NOT EXISTS webhook_url TEXT,
    ADD COLUMN IF NOT EXISTS hook_id BIGINT,
    ADD COLUMN IF NOT EXISTS link_url TEXT,
    ADD COLUMN IF NOT EXISTS nota_min INT,
    ADD COLUMN IF NOT EXISTS nota_max INT,
    ADD COLUMN IF NOT EXISTS nota_pergunta TEXT,
    ADD COLUMN IF NOT EXISTS grupo TEXT;

-- FKs (nomeadas pra evitar duplicação)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
         WHERE constraint_name = 'fk_menu_item_modelo_mensagem'
    ) THEN
        ALTER TABLE menu_item
            ADD CONSTRAINT fk_menu_item_modelo_mensagem
            FOREIGN KEY (acao_modelo_mensagem_id)
            REFERENCES modelo_mensagem(id) ON DELETE SET NULL;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
         WHERE constraint_name = 'fk_menu_item_hook'
    ) THEN
        ALTER TABLE menu_item
            ADD CONSTRAINT fk_menu_item_hook
            FOREIGN KEY (hook_id)
            REFERENCES hook(id) ON DELETE SET NULL;
    END IF;
END $$;

-- Expandir CHECK acao_tipo de 5 → 12
ALTER TABLE menu_item DROP CONSTRAINT IF EXISTS menu_item_acao_tipo_check;
ALTER TABLE menu_item ADD CONSTRAINT menu_item_acao_tipo_check CHECK (
    acao_tipo IN (
        -- MVP (mig 040)
        'submenu',
        'transferir_dep',
        'chamar_agente',
        'enviar_msg',
        'fechar',
        -- Sub-fase B+ paridade ZigChat (mig 042)
        'transferir_atendente',
        'enviar_template',
        'chamar_webhook',
        'enviar_link',
        'pesquisa_csat',
        'mudar_manual',
        'setar_nome'
    )
);


-- ---- ModeloLLM catálogo ----
-- Catálogo de modelos LLM disponíveis com custo (USD por 1M tokens).
-- empresa_id NULL = modelo global (todas empresas usam).
CREATE TABLE IF NOT EXISTS modelo_llm (
    id BIGSERIAL PRIMARY KEY,
    -- NULL = global; preenchido = customização por empresa (override custo, etc)
    empresa_id BIGINT REFERENCES empresa(id) ON DELETE CASCADE,
    provedor TEXT NOT NULL,                     -- openai/anthropic/google/openrouter/...
    nome TEXT NOT NULL,                         -- gpt-4o-mini, claude-haiku-4-5, etc
    descricao TEXT,
    tipo TEXT NOT NULL
        CHECK (tipo IN ('chat', 'embedding', 'midia', 'audio', 'imagem')),
    -- Custo em USD por 1 milhão de tokens
    custo_input_mtok NUMERIC(10,4),
    custo_output_mtok NUMERIC(10,4),
    janela_contexto INT,                        -- max tokens contexto
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- COALESCE pra unique permitir 1 row global + N rows por empresa
CREATE UNIQUE INDEX IF NOT EXISTS uq_modelo_llm
    ON modelo_llm (COALESCE(empresa_id, 0), provedor, nome);

CREATE INDEX IF NOT EXISTS idx_modelo_llm_empresa
    ON modelo_llm (empresa_id) WHERE ativo;

-- Seed inicial: modelos comuns globais (empresa_id NULL).
-- Custos baseados em pricing público em 2026-05.
INSERT INTO modelo_llm
    (empresa_id, provedor, nome, descricao, tipo, custo_input_mtok, custo_output_mtok, janela_contexto)
VALUES
    -- OpenAI
    (NULL, 'openai', 'gpt-4o-mini',
     'GPT-4o mini — barato, rápido, multimodal', 'chat', 0.15, 0.60, 128000),
    (NULL, 'openai', 'gpt-4o',
     'GPT-4o — multimodal flagship', 'chat', 2.50, 10.00, 128000),
    (NULL, 'openai', 'whisper-1',
     'Whisper — STT (speech-to-text)', 'audio', 0, 6.00, NULL),
    (NULL, 'openai', 'text-embedding-3-small',
     'Embedding 1536 dim, barato', 'embedding', 0.02, 0, 8191),
    (NULL, 'openai', 'text-embedding-3-large',
     'Embedding 3072 dim, melhor qualidade', 'embedding', 0.13, 0, 8191),
    -- Google
    (NULL, 'google', 'gemini-2.5-flash',
     'Gemini 2.5 Flash — rápido + 1M contexto', 'chat', 0.075, 0.30, 1000000),
    (NULL, 'google', 'gemini-2.5-pro',
     'Gemini 2.5 Pro — top tier + 2M contexto', 'chat', 1.25, 5.00, 2000000),
    -- Anthropic
    (NULL, 'anthropic', 'claude-haiku-4-5',
     'Claude Haiku 4.5 — rápido + custo médio', 'chat', 1.00, 5.00, 200000),
    (NULL, 'anthropic', 'claude-sonnet-4-6',
     'Claude Sonnet 4.6 — equilíbrio qualidade/custo', 'chat', 3.00, 15.00, 200000),
    (NULL, 'anthropic', 'claude-opus-4-7',
     'Claude Opus 4.7 — máxima qualidade + 1M contexto', 'chat', 15.00, 75.00, 1000000)
ON CONFLICT DO NOTHING;
