-- Sprint Conector de APIs — armazenamento genérico de credenciais.
--
-- Mantém `wareline_credentials` (mig 090) intocada por estabilidade — o
-- código continua usando a tabela específica pro Wareline. Novos
-- providers (Asaas, Custom, etc.) entram em `api_connection`.
--
-- 1 empresa pode ter N conexões do mesmo provider distinguidas por `label`
-- (ex: "Asaas Produção" + "Asaas Sandbox"). UNIQUE composto evita
-- duplicata exata.

CREATE TABLE IF NOT EXISTS api_connection (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    -- Catálogo Python valida (asaas, custom, etc.). VARCHAR pra evoluir
    -- sem migration nova.
    provider_slug TEXT NOT NULL,
    label TEXT NOT NULL,
    base_url TEXT,
    -- api_key | bearer | basic | oauth2_password | oauth2_client_credentials
    auth_type TEXT NOT NULL,
    -- JSON Fernet ciphertext com TODOS os campos sensíveis num blob
    -- (vs colunas separadas — flexível pra cada provider ter shape próprio)
    credentials_encrypted TEXT NOT NULL,
    extra_config JSONB NOT NULL DEFAULT '{}'::jsonb,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    ultimo_teste_at TIMESTAMPTZ,
    ultimo_teste_ok BOOLEAN,
    ultimo_teste_erro TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by_user_id TEXT,
    UNIQUE (empresa_id, provider_slug, label)
);

CREATE INDEX IF NOT EXISTS idx_api_connection_empresa_provider
    ON api_connection (empresa_id, provider_slug) WHERE ativo;

-- Cache de access_token (OAuth) por connection. Não-OAuth providers
-- (api_key/bearer/basic) não usam essa tabela.
CREATE TABLE IF NOT EXISTS api_connection_token_cache (
    connection_id BIGINT PRIMARY KEY
        REFERENCES api_connection(id) ON DELETE CASCADE,
    access_token TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    refresh_token TEXT,
    refreshed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_api_connection_token_expires
    ON api_connection_token_cache (expires_at);

-- Perm genérica (mantém também a antiga integracao.wareline.manage)
INSERT INTO permissao (codigo, descricao, modulo) VALUES
    (
        'integracao.manage',
        'Gerenciar integrações de API (cadastrar/testar/remover)',
        'integracao'
    )
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO perfil_permissao (perfil_id, permissao_codigo)
SELECT pa.id, 'integracao.manage'
  FROM perfil_acesso pa
 WHERE pa.is_system AND pa.nome IN ('Admin', 'Gestor')
ON CONFLICT DO NOTHING;
