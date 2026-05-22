-- Sprint A.2.3 — Troca policy permissive → estrita.
--
-- Mig 096 criou `_rls_tenant_match(empresa_id)` em modo PERMISSIVE:
--   ctx_empresa NULL/vazio → RETURN TRUE (compat retroativa)
--
-- Esta mig substitui pela estrita:
--   ctx_empresa NULL/vazio → RETURN FALSE (deny por default)
--
-- Pré-condição: 100% dos call sites em código devem setar
-- `SET app.empresa_id` OU `SET app.bypass_rls=true` ANTES de tocar
-- tabela com empresa_id. Caso contrário, query retorna 0 rows
-- silenciosamente (com SELECT) ou falha com InsufficientPrivilege
-- (com INSERT/UPDATE/DELETE).
--
-- Sprints anteriores prepararam o terreno:
--   A.2.4 — middleware FastAPI seta context via X-Empresa-Id
--   A.2.5 — worker seta context per-msg via empresa_scope(empresa_id)
--   A.2.6 — DATABASE_URL_APP=chat_nexus_app (NOBYPASSRLS) + bypass
--           explícito em pontos cross-tenant legítimos:
--             - claim_next_message
--             - list_active_calendar_empresas
--             - cleanup_zumbis_all_empresas (SELECT empresa)
--             - get_conexao_by_from_number/evolution_instance/waba_phone_id
--   queue.py::enqueue_or_buffer — seta app.empresa_id na conn ao entrar
--
-- Rollback: re-aplica mig 096 (volta função pra TRUE no NULL).

CREATE OR REPLACE FUNCTION _rls_tenant_match(row_empresa_id BIGINT)
RETURNS BOOLEAN
LANGUAGE plpgsql
STABLE
PARALLEL SAFE
AS $$
DECLARE
    ctx_empresa TEXT;
    ctx_bypass TEXT;
BEGIN
    -- 1) bypass explícito (superadmin, webhooks pré-resolução, crons)
    ctx_bypass := current_setting('app.bypass_rls', true);
    IF ctx_bypass = 'true' THEN
        RETURN TRUE;
    END IF;

    -- 2) Sprint A.2.3 — STRICT: sem context = sem acesso
    ctx_empresa := current_setting('app.empresa_id', true);
    IF ctx_empresa IS NULL OR ctx_empresa = '' THEN
        RETURN FALSE;
    END IF;

    -- 3) context setado → row precisa bater
    RETURN row_empresa_id = ctx_empresa::BIGINT;
END;
$$;

COMMENT ON FUNCTION _rls_tenant_match(BIGINT) IS
    'Sprint A.2.3 STRICT — sem app.empresa_id setado, retorna FALSE '
    '(deny). Bypass apenas via app.bypass_rls=true. Caller deve usar '
    'middleware (API) ou empresa_scope() (worker/cron/webhook).';

-- Sanity check: confirma que função existe e retorna esperado
DO $$
BEGIN
    PERFORM set_config('app.empresa_id', '', true);
    PERFORM set_config('app.bypass_rls', '', true);
    IF _rls_tenant_match(1) <> FALSE THEN
        RAISE EXCEPTION 'STRICT broken: vazio deveria retornar FALSE';
    END IF;

    PERFORM set_config('app.empresa_id', '42', true);
    IF _rls_tenant_match(42) <> TRUE THEN
        RAISE EXCEPTION 'STRICT broken: empresa=42 row=42 deveria TRUE';
    END IF;
    IF _rls_tenant_match(99) <> FALSE THEN
        RAISE EXCEPTION 'STRICT broken: empresa=42 row=99 deveria FALSE';
    END IF;

    PERFORM set_config('app.empresa_id', '', true);
    PERFORM set_config('app.bypass_rls', 'true', true);
    IF _rls_tenant_match(99) <> TRUE THEN
        RAISE EXCEPTION 'STRICT broken: bypass deveria TRUE';
    END IF;

    -- Reset
    PERFORM set_config('app.empresa_id', '', true);
    PERFORM set_config('app.bypass_rls', '', true);

    RAISE NOTICE 'Sprint A.2.3 STRICT policy validada com sucesso';
END $$;
