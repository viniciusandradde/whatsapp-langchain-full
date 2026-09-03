-- campanha_destinatario entra no RLS (F2a do projeto Prospecção Enterprise).
--
-- Era a ÚNICA tabela do módulo fora do isolamento por linha. Não foi
-- esquecimento: a mig 101 é um DO block que itera pelas tabelas COM coluna
-- `empresa_id`, e esta só tem FK pra `campanha`. A própria 101 registrou a
-- classe como dívida ("Pra cobrir FK-indirect tables ... sprint futura
-- precisa adicionar coluna empresa_id (denormalização)"). É o que esta faz.
--
-- Por que agora e não junto do motor: hoje o isolamento entre empresas
-- depende INTEIRAMENTE de o código sempre filtrar por uma `campanha_id` já
-- validada. Está correto no código atual — mas é invariante sem rede, e a
-- Fase 2 multiplica os call sites (claim, lease, webhook de status, worker
-- em paralelo). Ligar o RLS antes é mais barato que auditar depois.
--
-- Estado em produção quando esta foi escrita (2026-09-02): a tabela está
-- VAZIA, então o backfill é no-op lá. Em base de desenvolvimento pode haver
-- histórico — daí o UPDATE antes do NOT NULL.

-- 1. Coluna, ainda anulável pra permitir o backfill.
ALTER TABLE campanha_destinatario
    ADD COLUMN IF NOT EXISTS empresa_id BIGINT;

-- 2. Backfill pela campanha dona (fonte de verdade do tenant).
UPDATE campanha_destinatario cd
   SET empresa_id = c.empresa_id
  FROM campanha c
 WHERE c.id = cd.campanha_id
   AND cd.empresa_id IS NULL;

-- 3. Guard antes do NOT NULL: destinatário órfão não deveria existir (a FK
--    pra campanha é ON DELETE CASCADE), mas se existir o ALTER abaixo
--    travaria o startup com erro de constraint sem dizer o porquê. Melhor
--    falhar aqui, nomeando o problema.
DO $$
DECLARE
    n_orfaos INT;
BEGIN
    SELECT count(*) INTO n_orfaos
      FROM campanha_destinatario WHERE empresa_id IS NULL;

    IF n_orfaos > 0 THEN
        RAISE EXCEPTION
            'Migration 182: % destinatario(s) sem campanha dona — o backfill '
            'nao conseguiu resolver o empresa_id. Investigue antes de seguir '
            '(SELECT * FROM campanha_destinatario cd LEFT JOIN campanha c '
            'ON c.id = cd.campanha_id WHERE c.id IS NULL).',
            n_orfaos;
    END IF;
END $$;

ALTER TABLE campanha_destinatario
    ALTER COLUMN empresa_id SET NOT NULL;

-- 4. FK. `ADD CONSTRAINT IF NOT EXISTS` não existe pra FK no Postgres, daí
--    o guard por catálogo (a migration precisa ser idempotente).
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conname = 'campanha_destinatario_empresa_id_fkey'
           AND conrelid = 'campanha_destinatario'::regclass
    ) THEN
        ALTER TABLE campanha_destinatario
            ADD CONSTRAINT campanha_destinatario_empresa_id_fkey
            FOREIGN KEY (empresa_id) REFERENCES empresa(id) ON DELETE CASCADE;
    END IF;
END $$;

-- 5. Índice pro predicado do RLS. O `idx_campanha_dest_pendentes` (mig 034)
--    continua servindo o claim por campanha; este cobre a varredura por
--    tenant, que passa a existir em toda query graças à policy.
CREATE INDEX IF NOT EXISTS idx_campanha_dest_empresa
    ON campanha_destinatario (empresa_id, campanha_id);

-- 6. RLS no mesmo formato das outras 58 tabelas (migs 096/101/102):
--    ENABLE + FORCE (FORCE faz valer inclusive pro dono da tabela) + policy
--    `tenant_isolation` usando o helper `_rls_tenant_match`, que desde a
--    mig 102 é ESTRITO: sem `app.empresa_id` no context, a linha não aparece.
ALTER TABLE campanha_destinatario ENABLE ROW LEVEL SECURITY;
ALTER TABLE campanha_destinatario FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS tenant_isolation ON campanha_destinatario;
CREATE POLICY tenant_isolation ON campanha_destinatario
    USING (_rls_tenant_match(empresa_id))
    WITH CHECK (_rls_tenant_match(empresa_id));

COMMENT ON COLUMN campanha_destinatario.empresa_id IS
    'Tenant dono da linha. Denormalizado da campanha (mig 182) porque o RLS '
    'precisa do empresa_id NA linha — policy nao navega FK. Escrito por '
    'shared/campanha.py em todos os INSERTs; a FK garante que nao diverge.';

-- 7. Validação: se a policy não pegou, o deploy tem que parar aqui e não
--    duas semanas depois, num vazamento silencioso.
DO $$
DECLARE
    tem_rls BOOLEAN;
    tem_policy BOOLEAN;
BEGIN
    SELECT c.relrowsecurity AND c.relforcerowsecurity INTO tem_rls
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public' AND c.relname = 'campanha_destinatario';

    SELECT EXISTS (
        SELECT 1 FROM pg_policies
         WHERE schemaname = 'public'
           AND tablename = 'campanha_destinatario'
           AND policyname = 'tenant_isolation'
    ) INTO tem_policy;

    IF NOT tem_rls OR NOT tem_policy THEN
        RAISE EXCEPTION
            'Migration 182: RLS nao ficou ativo em campanha_destinatario '
            '(force=%, policy=%).', tem_rls, tem_policy;
    END IF;

    RAISE NOTICE 'Migration 182: campanha_destinatario sob RLS.';
END $$;
