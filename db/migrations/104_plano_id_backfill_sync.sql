-- Sprint Q.1 — Backfill empresa.plano_id + trigger sync com empresa.plano
--
-- Hoje empresa tem 2 colunas pra plano:
--   - empresa.plano        TEXT  ('free'/'pro'/'enterprise') — usado pelo app
--   - empresa.plano_id     BIGINT FK → plano(id)            — usado pra JOIN
--
-- Estão desincronizadas: só VSA Tech (id=1) tem plano_id setado. Resto
-- tem plano='pro' mas plano_id=NULL → não dá pra fazer JOIN simples
-- pra resolver limites.
--
-- Esta mig:
-- 1) Backfill: UPDATE plano_id baseado em plano.slug que casa com
--    empresa.plano (case-insensitive).
-- 2) Trigger BEFORE INSERT/UPDATE: sempre que empresa.plano (text) muda,
--    o plano_id é recalculado. Vale também pro INSERT: app passa só o
--    texto, o trigger preenche o FK.
-- 3) Migração defensiva: se plano texto não casa com nenhum plano.slug,
--    cai pro 'free' (id menor de slug=free).

-- 1) Backfill empresas existentes
UPDATE empresa e
   SET plano_id = p.id,
       updated_at = NOW()
  FROM plano p
 WHERE LOWER(e.plano) = LOWER(p.slug)
   AND e.plano_id IS NULL;

-- Fallback: empresas com plano que não bate com nenhum plano.slug
-- (ex: empresa.plano='premium' que não existe na tabela plano)
UPDATE empresa e
   SET plano_id = (SELECT id FROM plano WHERE slug = 'free' LIMIT 1),
       plano = 'free',
       updated_at = NOW()
 WHERE e.plano_id IS NULL;

-- 2) Trigger sync empresa.plano (text) ↔ empresa.plano_id (FK)
CREATE OR REPLACE FUNCTION _sync_empresa_plano_id()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    target_id BIGINT;
BEGIN
    -- Sync acontece quando:
    --   - INSERT (preencher plano_id baseado em plano texto)
    --   - UPDATE de empresa.plano (mudou texto, FK pode estar errado)
    --   - UPDATE de empresa.plano_id pra NULL (recalcular)
    IF TG_OP = 'INSERT' OR NEW.plano IS DISTINCT FROM OLD.plano
        OR NEW.plano_id IS NULL THEN

        SELECT id INTO target_id
          FROM plano
         WHERE LOWER(slug) = LOWER(COALESCE(NEW.plano, 'free'))
           AND ativo = TRUE
         LIMIT 1;

        -- Fallback final: free
        IF target_id IS NULL THEN
            SELECT id INTO target_id
              FROM plano WHERE slug = 'free' LIMIT 1;
        END IF;

        NEW.plano_id := target_id;
        -- Garante que texto fica coerente com FK
        IF target_id IS NOT NULL THEN
            NEW.plano := (SELECT slug FROM plano WHERE id = target_id);
        END IF;
    END IF;

    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION _sync_empresa_plano_id() IS
    'Sprint Q.1 — mantém empresa.plano (text) ↔ empresa.plano_id (FK) '
    'em sync. App pode setar só o texto que o trigger preenche FK; ou '
    'só o FK que trigger preenche texto. Fallback pra free se nenhum '
    'casa.';

DROP TRIGGER IF EXISTS trg_sync_empresa_plano ON empresa;
CREATE TRIGGER trg_sync_empresa_plano
    BEFORE INSERT OR UPDATE ON empresa
    FOR EACH ROW
    EXECUTE FUNCTION _sync_empresa_plano_id();

-- 3) Audit view: empresas + limites resolvidos
CREATE OR REPLACE VIEW empresa_plano_audit AS
SELECT
    e.id           AS empresa_id,
    e.nome         AS empresa_nome,
    e.plano        AS plano_text,
    e.plano_id     AS plano_id,
    p.slug         AS plano_slug_resolved,
    p.preco_mensal_brl,
    p.limite_usuarios,
    p.limite_conexoes,
    p.limite_atendimentos_mes,
    p.limite_orcamento_ia_usd,
    p.limite_documentos_kb,
    p.features
  FROM empresa e
  LEFT JOIN plano p ON p.id = e.plano_id
 WHERE e.status = 'active'
 ORDER BY e.id;

COMMENT ON VIEW empresa_plano_audit IS
    'Sprint Q.1 audit — empresa + plano resolvido com limites. Esperado: '
    'plano_text == plano_slug_resolved pra todas empresas (sync OK).';

-- 4) Validação pós-migração: nenhuma empresa pode ter plano_id NULL
DO $$
DECLARE
    unsync_count INT;
BEGIN
    SELECT COUNT(*) INTO unsync_count
      FROM empresa
     WHERE plano_id IS NULL AND status = 'active';

    IF unsync_count > 0 THEN
        RAISE EXCEPTION 'Sprint Q.1: % empresas ativas com plano_id NULL — backfill falhou', unsync_count;
    END IF;

    RAISE NOTICE 'Sprint Q.1: backfill + trigger OK';
END $$;
