-- Disparador (Task 1) — API key por empresa para autenticar a extensão Chrome.
--
-- A extensão NÃO pode usar o INTERNAL_SERVICE_TOKEN (token global compartilhado
-- que vazaria no cliente do browser). Cada empresa gera 1+ chaves próprias,
-- escopadas (capture/dispatch/templates), revogáveis e com expiração opcional.
--
-- Segurança: guardamos apenas o SHA-256 (hex) da chave completa — NUNCA o
-- segredo. O `key_prefix` (ex: "nxs_1_a1b2c3d4") permite exibir/identificar a
-- chave na UI sem expor o hash. Formato da chave: nxs_<empresa_id>_<32hex>.
-- A resolução no request faz hash do token recebido e compara timing-safe.

CREATE TABLE IF NOT EXISTS empresa_api_key (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    label TEXT NOT NULL,                       -- nome descritivo ("Extensão Chrome - João")
    key_prefix TEXT NOT NULL,                  -- nxs_<eid>_<8hex> para lookup/exibição
    key_hash TEXT NOT NULL,                     -- sha256(chave completa) em hex; nunca o segredo
    scopes TEXT[] NOT NULL DEFAULT ARRAY['capture']::TEXT[],
    expires_at TIMESTAMPTZ,                     -- NULL = nunca expira
    revoked_at TIMESTAMPTZ,                     -- NULL = ativa
    last_used_at TIMESTAMPTZ,
    last_used_ip TEXT,
    rate_limit_per_minute INT NOT NULL DEFAULT 60,
    created_by_user_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (empresa_id, label)
);

-- Lookup por hash só entre chaves ativas (resolução no request) — uma chave
-- não-revogada por hash. Revogadas podem repetir hash teoricamente; o índice
-- parcial garante unicidade só no conjunto ativo.
CREATE UNIQUE INDEX IF NOT EXISTS uq_empresa_api_key_hash
    ON empresa_api_key (key_hash) WHERE revoked_at IS NULL;

-- Lookup auxiliar por prefixo (escopa a busca sem full-scan de hash).
CREATE INDEX IF NOT EXISTS idx_empresa_api_key_prefix
    ON empresa_api_key (key_prefix) WHERE revoked_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_empresa_api_key_empresa
    ON empresa_api_key (empresa_id, created_at DESC) WHERE revoked_at IS NULL;

-- RLS uniforme (Sprint A.2 STRICT): toda tabela com empresa_id tem
-- ENABLE + FORCE + policy tenant_isolation via _rls_tenant_match.
ALTER TABLE empresa_api_key ENABLE ROW LEVEL SECURITY;
ALTER TABLE empresa_api_key FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON empresa_api_key;
CREATE POLICY tenant_isolation ON empresa_api_key
    USING (_rls_tenant_match(empresa_id))
    WITH CHECK (_rls_tenant_match(empresa_id));
