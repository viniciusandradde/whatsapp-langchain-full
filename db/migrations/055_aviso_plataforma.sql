-- Sprint 6 — Paridade ZigChat (Aviso — notificações da plataforma + tracking).
--
-- Documentação: docs/zigchat/depara/04_pendentes_criar.md
--
-- Banner sistema (manutenção, novidades, billing pendente) com:
--   - empresa_id NULL = aviso global (todas empresas)
--   - empresa_id preenchido = aviso específico
--   - tracking quem leu via aviso_usuario_leitura

CREATE TABLE IF NOT EXISTS aviso (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT REFERENCES empresa(id) ON DELETE CASCADE,
    titulo TEXT NOT NULL,
    conteudo TEXT NOT NULL,
    tipo TEXT NOT NULL DEFAULT 'info'
        CHECK (tipo IN ('info', 'warning', 'critical', 'feature')),
    link_url TEXT,                         -- "saiba mais" / CTA
    ativo_de TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ativo_ate TIMESTAMPTZ,
    obrigatorio BOOLEAN NOT NULL DEFAULT FALSE,  -- bloqueia uso até confirmar leitura
    created_by_user_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_aviso_ativos_global
    ON aviso (ativo_de DESC) WHERE empresa_id IS NULL;
CREATE INDEX IF NOT EXISTS idx_aviso_ativos_empresa
    ON aviso (empresa_id, ativo_de DESC) WHERE empresa_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS aviso_usuario_leitura (
    aviso_id BIGINT NOT NULL REFERENCES aviso(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    lido_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (aviso_id, user_id)
);
