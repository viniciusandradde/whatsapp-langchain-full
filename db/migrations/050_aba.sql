-- Sprint 5 — Paridade ZigChat (Aba — quadros custom de atendimentos).
--
-- Documentação: docs/zigchat/depara/04_pendentes_criar.md
--
-- Filtro nomeado salvo (ex: "Vendas Q1", "Suporte VIP", "Aguardando 24h+").
-- Estilo Trello — cada operador pode ter abas pessoais E abas compartilhadas.
--
-- O JSONB filtro guarda critérios livres:
--   {departamento_ids: [1,3], tag_ids: [5], status: ["aguardando"], ...}

CREATE TABLE IF NOT EXISTS aba (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    nome TEXT NOT NULL,
    descricao TEXT,
    filtro JSONB NOT NULL DEFAULT '{}'::jsonb,
    cor TEXT,                              -- hex "#FF5733" pra UI
    ordem INT,                             -- ordem de exibição na barra
    -- NULL = aba compartilhada (visível pra toda equipe)
    -- preenchido = aba pessoal do user
    user_id TEXT,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    created_by_user_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_aba_empresa
    ON aba (empresa_id, COALESCE(user_id, '_shared'), ordem) WHERE ativo;
