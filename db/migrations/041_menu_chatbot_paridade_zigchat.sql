-- Sub-fase B+ — Paridade ZigChat (UX wins do menu).
--
-- Documentação: docs/zigchat/depara/03_gap_grande.md (na branch feat/webscap)
--
-- Adiciona ao menu_chatbot:
--   - atalho: comando curto opcional (alternativa a trigger_keywords array)
--   - solicitar_nome: pede nome do cliente antes do menu
--   - menu_moderno: usa botões nativos WhatsApp em vez de "1, 2, 3"
--   - auto_navegar_para_item_id: pula direto pra item se sair por timeout
--   - qtde_acesso: counter analytics
--   - arquivo_url: anexo (PDF/imagem) na mensagem de boas-vindas
--   - mensagem_coleta + mensagem_confirmar_coleta + mensagem_final_coleta:
--     wizard de coleta de dados em 3 passos sequenciais
--   - resposta_confidencial: flag de mascarar conteúdo
--
-- Cria menu_item_arquivo: anexo (PDF/imagem) atrelado ao item.
-- Cria mcp_server: catalogo MCP servers (já referenciado por agente_ia.mcp_server_ids).

-- ---- Expand menu_chatbot ----
ALTER TABLE menu_chatbot
    ADD COLUMN IF NOT EXISTS atalho TEXT,
    ADD COLUMN IF NOT EXISTS solicitar_nome BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS menu_moderno BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS auto_navegar_para_item_id BIGINT,
    ADD COLUMN IF NOT EXISTS qtde_acesso BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS arquivo_url TEXT,
    ADD COLUMN IF NOT EXISTS mensagem_coleta TEXT,
    ADD COLUMN IF NOT EXISTS mensagem_confirmar_coleta TEXT,
    ADD COLUMN IF NOT EXISTS mensagem_final_coleta TEXT,
    ADD COLUMN IF NOT EXISTS resposta_confidencial BOOLEAN NOT NULL DEFAULT FALSE;

-- FK auto_navegar_para_item_id (definida depois pra evitar dep antes do item existir
-- — menu_item já existe via mig 040, então OK).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
         WHERE constraint_name = 'fk_menu_chatbot_auto_navegar_item'
    ) THEN
        ALTER TABLE menu_chatbot
            ADD CONSTRAINT fk_menu_chatbot_auto_navegar_item
            FOREIGN KEY (auto_navegar_para_item_id)
            REFERENCES menu_item(id) ON DELETE SET NULL;
    END IF;
END $$;


-- ---- Menu Item Arquivo ----
-- Anexo (PDF/imagem/audio) atrelado a menu OU item.
-- WhatsApp permite enviar arquivo + texto na mesma mensagem.
CREATE TABLE IF NOT EXISTS menu_item_arquivo (
    id BIGSERIAL PRIMARY KEY,
    menu_id BIGINT REFERENCES menu_chatbot(id) ON DELETE CASCADE,
    item_id BIGINT REFERENCES menu_item(id) ON DELETE CASCADE,
    arquivo_url TEXT NOT NULL,
    arquivo_nome TEXT,
    content_type TEXT,
    descricao TEXT,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Pelo menos um dos dois deve ser preenchido
    CONSTRAINT chk_menu_item_arquivo_owner CHECK (
        menu_id IS NOT NULL OR item_id IS NOT NULL
    )
);

CREATE INDEX IF NOT EXISTS idx_menu_item_arquivo_menu
    ON menu_item_arquivo (menu_id) WHERE menu_id IS NOT NULL AND ativo;
CREATE INDEX IF NOT EXISTS idx_menu_item_arquivo_item
    ON menu_item_arquivo (item_id) WHERE item_id IS NOT NULL AND ativo;


-- ---- MCP Server ----
-- Catalogo de servidores MCP (Model Context Protocol).
-- agente_ia.mcp_server_ids[] (mig 039) já referencia este id.
CREATE TABLE IF NOT EXISTS mcp_server (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    nome TEXT NOT NULL,
    descricao TEXT,
    -- Tipo de transporte do MCP server
    tipo_conexao TEXT NOT NULL
        CHECK (tipo_conexao IN ('stdio', 'sse', 'http', 'websocket')),
    -- Pra sse/http/websocket
    url TEXT,
    -- Pra stdio (process spawn)
    comando TEXT,
    args TEXT,                                    -- args do comando, JSON array serializado
    -- Headers HTTP customizados
    headers JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- Status do health check
    status TEXT NOT NULL DEFAULT 'inactive'
        CHECK (status IN ('active', 'inactive', 'error', 'testing')),
    ultimo_teste_at TIMESTAMPTZ,
    ultimo_erro TEXT,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    created_by_user_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (empresa_id, nome)
);

CREATE INDEX IF NOT EXISTS idx_mcp_server_empresa
    ON mcp_server (empresa_id) WHERE ativo;
