-- Sprint Wareline — integração ConecteHub (Hospital Mackenzie).
--
-- 1) wareline_credentials: 1 set de credenciais por empresa (multi-tenant).
--    Campos sensíveis (password, client_secret) salvos como Fernet ciphertext
--    em coluna TEXT. Chave de cripto vem de settings.wareline_encryption_key.
--
-- 2) wareline_token_cache: cache do JWT OAuth (TTL 5min real, mas guardamos
--    com 30s de margem pra evitar race condition no expirar). Race-safe via
--    INSERT ON CONFLICT DO UPDATE quando refrescamos.
--
-- 3) Permissão `integracao.wareline.manage` (Admin/Gestor).

CREATE TABLE IF NOT EXISTS wareline_credentials (
    empresa_id BIGINT PRIMARY KEY REFERENCES empresa(id) ON DELETE CASCADE,
    base_url TEXT NOT NULL DEFAULT 'https://modulos.conectew.com.br',
    pacientes_base_url TEXT NOT NULL DEFAULT 'https://services.conectew.com.br',
    username TEXT NOT NULL,
    password_encrypted TEXT NOT NULL,
    client_id TEXT NOT NULL,
    client_secret_encrypted TEXT NOT NULL,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    ultimo_teste_at TIMESTAMPTZ,
    ultimo_teste_ok BOOLEAN,
    ultimo_teste_erro TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by_user_id TEXT
);

CREATE TABLE IF NOT EXISTS wareline_token_cache (
    empresa_id BIGINT PRIMARY KEY REFERENCES empresa(id) ON DELETE CASCADE,
    access_token TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    refresh_token TEXT,
    refreshed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_wareline_token_expires
    ON wareline_token_cache (expires_at);

-- RBAC
INSERT INTO permissao (codigo, descricao, modulo) VALUES
    (
        'integracao.wareline.manage',
        'Gerenciar integração Wareline (credenciais, testar)',
        'integracao'
    )
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO perfil_permissao (perfil_id, permissao_codigo)
SELECT pa.id, 'integracao.wareline.manage'
  FROM perfil_acesso pa
 WHERE pa.is_system AND pa.nome IN ('Admin', 'Gestor')
ON CONFLICT DO NOTHING;
