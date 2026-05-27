-- Sprint Conexão Padrão — defesa em profundidade pro is_default
--
-- Antes desta mig, era teoricamente possível ter 2+ conexões da mesma empresa
-- com is_default=TRUE (rota PATCH /api/conexoes/{id} sem unset batch das
-- outras). O guard implementado em shared/conexao.py::patch_conexao /
-- upsert_conexao já faz o batch unset, mas esta UNIQUE INDEX parcial garante
-- na camada do banco: tentar persistir 2 defaults dispara erro de integridade.
--
-- Por que partial WHERE is_default=TRUE:
-- - Permite N conexões com is_default=FALSE (todas as não-padrão)
-- - Restringe APENAS 1 com TRUE por empresa_id
-- - Sem o WHERE, qualquer empresa só poderia ter 1 conexão total (errado)
--
-- Como fica:
--   empresa 1, dev=TRUE  ✅
--   empresa 1, evo=FALSE ✅
--   empresa 1, prod=TRUE ❌ → unique violation (forçando uso do path do guard)
--   empresa 2, qq=TRUE   ✅ (diferente empresa)

-- Pré-condição: nenhuma empresa pode ter >1 default agora.
-- Se houver duplicata em prod, esta mig FALHA. Resolver via SQL antes:
--   UPDATE conexao SET is_default=FALSE
--    WHERE empresa_id IN (
--      SELECT empresa_id FROM conexao
--       WHERE is_default=TRUE
--       GROUP BY empresa_id HAVING COUNT(*) > 1
--    )
--    AND id NOT IN (
--      SELECT MIN(id) FROM conexao
--       WHERE is_default=TRUE
--       GROUP BY empresa_id
--    );

CREATE UNIQUE INDEX IF NOT EXISTS idx_conexao_unique_default
    ON conexao (empresa_id)
    WHERE is_default = TRUE;

COMMENT ON INDEX idx_conexao_unique_default IS
    'Sprint conexão padrão — garante no máximo 1 conexão com is_default=TRUE '
    'por empresa. Patch helpers (shared/conexao.py) fazem unset batch antes '
    'do set; este index é defesa em profundidade caso algum path skip o guard.';
