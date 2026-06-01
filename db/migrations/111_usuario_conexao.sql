-- Sprint U (gestão de usuários) — conexão padrão + conexões permitidas por
-- usuário. Paridade ZigChat (`Usuario.padrao_conexao_id` / `conexoes`).
--
-- Hoje o outbound manual roteia por `atendimento.conexao_id`; esta tabela é
-- atribuição/metadado por atendente + fallback de conexão default do
-- compositor. NÃO reescreve o roteamento do worker.
--
-- 1 usuário pode ter N conexões (M:N) numa empresa; no máximo 1 marcada
-- como default (partial unique index).

CREATE TABLE IF NOT EXISTS usuario_conexao (
    user_id TEXT NOT NULL,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    conexao_id BIGINT NOT NULL REFERENCES conexao(id) ON DELETE CASCADE,
    is_default BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, conexao_id, empresa_id)
);

CREATE INDEX IF NOT EXISTS idx_usuario_conexao_user
    ON usuario_conexao (user_id, empresa_id);

CREATE INDEX IF NOT EXISTS idx_usuario_conexao_conexao
    ON usuario_conexao (conexao_id);

-- No máximo 1 conexão default por usuário/empresa (defesa em profundidade —
-- o app também limpa o flag antigo ao marcar um novo default).
CREATE UNIQUE INDEX IF NOT EXISTS uq_usuario_conexao_default
    ON usuario_conexao (user_id, empresa_id) WHERE is_default;

-- RLS uniforme (Sprint A.2 STRICT): toda tabela com empresa_id tem
-- ENABLE + FORCE + policy tenant_isolation via _rls_tenant_match.
ALTER TABLE usuario_conexao ENABLE ROW LEVEL SECURITY;
ALTER TABLE usuario_conexao FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON usuario_conexao;
CREATE POLICY tenant_isolation ON usuario_conexao
    USING (_rls_tenant_match(empresa_id))
    WITH CHECK (_rls_tenant_match(empresa_id));
