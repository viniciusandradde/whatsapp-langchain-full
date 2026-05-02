-- M4.b Quick replies: textos reutilizáveis pelo operador no painel.
-- Operador insere via dropdown no composer do AtendimentoDrawer; rota
-- /modelos serve a UI de CRUD pra cadastrar e manter os textos.

CREATE TABLE IF NOT EXISTS modelo_mensagem (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    titulo TEXT NOT NULL,
    conteudo TEXT NOT NULL,
    atalho TEXT,
    created_by_user_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Mesma empresa não pode ter dois modelos com o mesmo título (evita
    -- ambiguidade no dropdown).
    UNIQUE (empresa_id, titulo)
);

CREATE INDEX IF NOT EXISTS idx_modelo_mensagem_empresa
    ON modelo_mensagem (empresa_id, titulo);
