-- empresa: tenant root pra multi-tenancy do Nexus Chat AI.
CREATE TABLE IF NOT EXISTS empresa (
    id BIGSERIAL PRIMARY KEY,
    nome TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,
    doc TEXT,
    plano TEXT NOT NULL DEFAULT 'free',
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'suspended', 'archived')),
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- empresa_membro: associa user (Better Auth, schema "auth") a uma empresa.
-- is_default=TRUE marca a empresa que entra automático na sessão.
CREATE TABLE IF NOT EXISTS empresa_membro (
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'operator'
        CHECK (role IN ('admin', 'operator', 'viewer')),
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (empresa_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_empresa_membro_user
    ON empresa_membro (user_id, is_default DESC);

-- Flag de superadmin (cross-tenant access). Better Auth permite colunas extras
-- na tabela auth."user" — Drizzle/Better Auth ignora o que não conhece.
ALTER TABLE auth."user"
    ADD COLUMN IF NOT EXISTS is_superadmin BOOLEAN NOT NULL DEFAULT FALSE;

-- Bootstrap: empresa default id=1 "VSA Tech".
INSERT INTO empresa (id, nome, slug, plano)
    VALUES (1, 'VSA Tech', 'vsa-tech', 'enterprise')
    ON CONFLICT (id) DO NOTHING;

-- Avança o serial pra além de qualquer id já inserido (1).
SELECT setval('empresa_id_seq', GREATEST(1, (SELECT COALESCE(MAX(id), 1) FROM empresa)));

-- Promove TODOS os users existentes a admin da empresa 1, marcando essa
-- como sua empresa default. Sem isso, login pós-deploy retorna 403 no
-- get_empresa_context.
INSERT INTO empresa_membro (empresa_id, user_id, role, is_default)
    SELECT 1, id, 'admin', TRUE FROM auth."user"
    ON CONFLICT (empresa_id, user_id) DO NOTHING;

-- Marca todos os admins da empresa 1 como superadmin (acesso cross-tenant).
UPDATE auth."user"
    SET is_superadmin = TRUE
    WHERE id IN (
        SELECT user_id FROM empresa_membro
        WHERE empresa_id = 1 AND role = 'admin'
    );
