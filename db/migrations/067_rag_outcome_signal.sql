-- Sprint P.1 — sinal de qualidade implícito pra cada query RAG.
--
-- Hoje rag_query_log só sabe se a query teve hit ou não. NÃO sabe se a
-- resposta do agente foi útil. Esta mig conecta:
--   query → atendimento_id → desfecho → outcome
--
-- Outcomes:
--   success:    cliente resolveu sem intervenção humana
--   transferred: humano assumiu (assigned_to_user_id setado depois)
--   abandoned:   cliente nunca respondeu
--   escalated:   agente errou >=2x (qtde_resposta_invalida)
--   unknown:     atendimento ainda aberto ou sem sinal claro

-- 1. Coluna outcome em rag_query_log
ALTER TABLE rag_query_log
    ADD COLUMN IF NOT EXISTS outcome TEXT,
    ADD COLUMN IF NOT EXISTS outcome_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_rag_query_log_outcome
    ON rag_query_log (empresa_id, outcome, created_at DESC)
    WHERE outcome IS NOT NULL;

-- 2. Function pra computar outcome de um atendimento
CREATE OR REPLACE FUNCTION compute_atendimento_outcome(p_atendimento_id BIGINT)
RETURNS TEXT AS $$
DECLARE
    rec RECORD;
BEGIN
    SELECT
        a.status,
        a.assigned_to_user_id,
        COALESCE(a.qtde_resposta_invalida, 0) AS invalidas,
        a.solicitou_encerramento,
        a.classificacao,
        EXTRACT(EPOCH FROM (NOW() - a.created_at)) AS age_seconds
    INTO rec
    FROM atendimento a
    WHERE a.id = p_atendimento_id;

    IF rec IS NULL THEN
        RETURN NULL;
    END IF;

    -- Atendimento ainda aberto/jovem → desconhecido
    IF rec.status = 'aguardando' AND rec.age_seconds < 3600 THEN
        RETURN 'unknown';
    END IF;

    IF rec.status = 'abandonado' THEN
        RETURN 'abandoned';
    END IF;

    IF rec.assigned_to_user_id IS NOT NULL THEN
        RETURN 'transferred';
    END IF;

    IF rec.invalidas >= 2 THEN
        RETURN 'escalated';
    END IF;

    IF rec.status = 'resolvido' THEN
        RETURN 'success';
    END IF;

    RETURN 'unknown';
END;
$$ LANGUAGE plpgsql STABLE;

-- 3. Function pra propagar outcome em rag_query_log dado um atendimento
CREATE OR REPLACE FUNCTION refresh_rag_outcomes_for_atendimento(p_atendimento_id BIGINT)
RETURNS INT AS $$
DECLARE
    new_outcome TEXT;
    affected INT;
BEGIN
    new_outcome := compute_atendimento_outcome(p_atendimento_id);
    IF new_outcome IS NULL THEN
        RETURN 0;
    END IF;
    UPDATE rag_query_log
       SET outcome = new_outcome,
           outcome_at = NOW()
     WHERE atendimento_id = p_atendimento_id
       AND (outcome IS NULL OR outcome != new_outcome);
    GET DIAGNOSTICS affected = ROW_COUNT;
    RETURN affected;
END;
$$ LANGUAGE plpgsql;

-- 4. Trigger: quando atendimento.status, .assigned_to_user_id ou
--    .qtde_resposta_invalida mudam, atualiza outcomes das queries.
CREATE OR REPLACE FUNCTION trg_atendimento_outcome_propagate()
RETURNS TRIGGER AS $$
BEGIN
    IF (TG_OP = 'UPDATE' AND (
        OLD.status IS DISTINCT FROM NEW.status OR
        OLD.assigned_to_user_id IS DISTINCT FROM NEW.assigned_to_user_id OR
        OLD.qtde_resposta_invalida IS DISTINCT FROM NEW.qtde_resposta_invalida
    )) OR TG_OP = 'INSERT' THEN
        PERFORM refresh_rag_outcomes_for_atendimento(NEW.id);
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS atendimento_outcome_propagate ON atendimento;
CREATE TRIGGER atendimento_outcome_propagate
    AFTER INSERT OR UPDATE ON atendimento
    FOR EACH ROW EXECUTE FUNCTION trg_atendimento_outcome_propagate();

-- 5. Backfill: aplica outcome em queries antigas vinculadas a atendimentos.
UPDATE rag_query_log r
   SET outcome = compute_atendimento_outcome(r.atendimento_id),
       outcome_at = NOW()
 WHERE r.atendimento_id IS NOT NULL
   AND r.outcome IS NULL;
