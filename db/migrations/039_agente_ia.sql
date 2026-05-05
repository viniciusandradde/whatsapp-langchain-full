-- Sub-fase A: Multi-agente cadastrável (mapeamento ZigChat docs/agente).
--
-- Antes: agente_ia_config (mig 014) só permitia override de prompt/temperatura
--   pra agentes hardcoded no catálogo Python (vsa_tech). Não era possível
--   criar agente novo via UI.
--
-- Depois: agente_ia é instância completa cadastrável. Catálogo Python (vsa_tech)
--   passa a ser TEMPLATE — agente_ia.template_catalog escolhe qual graph rodar,
--   e overrides aplicam-se em cima (prompt, modelo, temperatura via estilo_resposta,
--   tools subset, KB ids, MCP ids, limite_custo_acao).
--
-- Backfill idempotente no fim: 1 row "Agente Padrão" por empresa que tinha
-- agente_ia_config ativo. Slug = agent_id legacy.

CREATE TABLE IF NOT EXISTS agente_ia (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    slug TEXT NOT NULL,                                          -- usado em conexao.default_agent_id
    nome TEXT NOT NULL,
    descricao TEXT,
    template_catalog TEXT NOT NULL DEFAULT 'vsa_tech',           -- agents/catalog/<x>
    prompt_override TEXT,
    modelo TEXT,                                                 -- 'google/gemini-2.5-flash' etc
    -- Estilo de respostas — atalho mapeado pra (temperatura, top_p) no loader.
    -- Decisão fixada: user prefere preset semântico em vez de slider técnico.
    --   preciso          → temperatura 0.1, top_p 0.6
    --   equilibrado      → temperatura 0.5, top_p 0.85   (default)
    --   criativo         → temperatura 0.9, top_p 0.95
    --   muito_criativo   → temperatura 1.3, top_p 0.99
    estilo_resposta TEXT NOT NULL DEFAULT 'equilibrado'
        CHECK (estilo_resposta IN ('preciso','equilibrado','criativo','muito_criativo')),
    -- Override fino se admin quiser ignorar o preset:
    temperatura_override NUMERIC(3,2)
        CHECK (temperatura_override IS NULL OR (temperatura_override >= 0 AND temperatura_override <= 2)),
    max_tokens INT,
    top_p_override NUMERIC(3,2)
        CHECK (top_p_override IS NULL OR (top_p_override >= 0 AND top_p_override <= 1)),
    -- Subset de tools que esse agente pode executar. Slugs canônicos
    -- definidos em agents/tools/__init__.py — ex: ['cliente.read',
    -- 'cliente.write', 'search_knowledge_base', 'calendar.create',
    -- 'transferir_dep', 'abrir_menu', 'encerrar_atendimento', ...]
    tools_enabled TEXT[] NOT NULL DEFAULT ARRAY[]::TEXT[],
    -- Sub-config por tool (JSONB pra flexibilidade):
    --   {transferir_dep: {modo: 'todos'|'selecionados', ids: [1,2]}}
    --   {abrir_menu: {menu_id: 5}}
    --   {chamar_webhook: {url: '...', headers: {...}}}
    tools_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- Tipos de mídia que o agente processa
    aceita_imagem BOOLEAN NOT NULL DEFAULT TRUE,
    aceita_audio BOOLEAN NOT NULL DEFAULT TRUE,
    aceita_documento BOOLEAN NOT NULL DEFAULT TRUE,
    -- Bases de Conhecimento liberadas (subset dos docs ativos da empresa).
    -- Vazio = todas (compat com comportamento atual).
    base_conhecimento_ids BIGINT[] NOT NULL DEFAULT ARRAY[]::BIGINT[],
    -- Variáveis ambiente injetáveis no prompt (subset)
    variavel_ids BIGINT[] NOT NULL DEFAULT ARRAY[]::BIGINT[],
    -- MCP servers liberados (preparação Fase 2 plano enterprise — coluna pronta,
    -- tabela mcp_server vem na mig 042 do plano)
    mcp_server_ids BIGINT[] NOT NULL DEFAULT ARRAY[]::BIGINT[],
    -- Limite de custo: ação executada quando empresa atinge limite mensal
    limite_custo_acao TEXT NOT NULL DEFAULT 'solicitar_humano'
        CHECK (limite_custo_acao IN
               ('solicitar_humano','encerrar','continuar','bloquear')),
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_by_user_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (empresa_id, slug)
);

CREATE INDEX IF NOT EXISTS idx_agente_ia_empresa
    ON agente_ia (empresa_id) WHERE ativo;

-- 1 default por empresa (PARTIAL unique pra permitir múltiplos non-default)
CREATE UNIQUE INDEX IF NOT EXISTS uq_agente_ia_default
    ON agente_ia (empresa_id) WHERE is_default;

-- ---- Backfill: migra agente_ia_config existente ----
-- Idempotente via ON CONFLICT — re-rodar a migration não duplica.
INSERT INTO agente_ia (
    empresa_id, slug, nome, descricao, template_catalog,
    prompt_override, ativo, is_default
)
SELECT
    empresa_id,
    agent_id,
    'Agente Padrão',
    'Migrado automaticamente de agente_ia_config (mig 014).',
    agent_id,            -- usa agent_id legacy como template_catalog
    system_prompt_override,
    ativo,
    TRUE                 -- 1º agente da empresa vira default
FROM agente_ia_config
ON CONFLICT (empresa_id, slug) DO NOTHING;
