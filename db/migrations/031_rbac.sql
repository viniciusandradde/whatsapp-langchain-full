-- E2.A: RBAC granular — permissões customizáveis por empresa.
--
-- Design:
-- - `permissao` é catálogo GLOBAL (sem empresa_id): codes fixos no código
--   (shared/permissoes.py) sincronizados via UPSERT no boot.
-- - `perfil_acesso` é POR empresa (admin pode criar perfis custom).
--   `is_system=true` marca perfis seed (Admin/Gestor/Operador/Leitura)
--   que não podem ser editados/deletados — só atribuídos.
-- - `perfil_permissao` (M:N) materializa quais permissões cada perfil tem.
-- - `usuario_perfil` (M:N) liga auth.user a perfil_acesso. Substitui
--   `empresa_membro.role` (TEXT) gradualmente; coluna role mantida com
--   depreciação anunciada.
--
-- Migração suave (em endpoint admin one-shot, não nesta migration):
--   admin → perfil "Admin", operator → "Operador", viewer → "Leitura".

CREATE TABLE IF NOT EXISTS permissao (
    codigo TEXT PRIMARY KEY,                       -- ex 'cliente.read', 'agendamento.approve'
    descricao TEXT NOT NULL,
    modulo TEXT NOT NULL,                          -- ex 'cliente', 'agendamento'
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_permissao_modulo ON permissao (modulo);


CREATE TABLE IF NOT EXISTS perfil_acesso (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    nome TEXT NOT NULL,
    descricao TEXT,
    is_system BOOLEAN NOT NULL DEFAULT FALSE,      -- TRUE pra seeds (não editáveis)
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (empresa_id, nome)
);

CREATE INDEX IF NOT EXISTS idx_perfil_acesso_empresa
    ON perfil_acesso (empresa_id);


CREATE TABLE IF NOT EXISTS perfil_permissao (
    perfil_id BIGINT NOT NULL REFERENCES perfil_acesso(id) ON DELETE CASCADE,
    permissao_codigo TEXT NOT NULL REFERENCES permissao(codigo) ON DELETE CASCADE,
    PRIMARY KEY (perfil_id, permissao_codigo)
);


CREATE TABLE IF NOT EXISTS usuario_perfil (
    user_id TEXT NOT NULL,                         -- auth.user.id
    perfil_id BIGINT NOT NULL REFERENCES perfil_acesso(id) ON DELETE CASCADE,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    assigned_by_user_id TEXT,
    PRIMARY KEY (user_id, perfil_id, empresa_id)
);

CREATE INDEX IF NOT EXISTS idx_usuario_perfil_user_empresa
    ON usuario_perfil (user_id, empresa_id);
