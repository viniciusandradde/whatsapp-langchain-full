-- Catálogo global (modelo_llm, mcp_server) volta a ser visível sob RLS STRICT.
--
-- Bug: `modelo_llm`/`mcp_server` guardam linhas GLOBAIS (empresa_id IS NULL,
-- catálogo compartilhado — GPT/Gemini/Claude etc.) + linhas por empresa. A
-- policy `tenant_isolation` usa `_rls_tenant_match(empresa_id)`, que retorna
-- FALSE quando empresa_id é NULL (STRICT: `NULL = ctx` → NULL). Resultado: a
-- app (chat_nexus_app) enxergava ZERO modelos globais — o seletor de modelo
-- do agente e o A/B de teste ficavam vazios (incidente 2026-07-24).
--
-- Fix: separar leitura de escrita. USING (leitura) permite global OU do
-- tenant; WITH CHECK (escrita) segue ESTRITO no tenant — tenant não cria/
-- edita linha global (isso é superadmin via app.bypass_rls). Só estas duas
-- tabelas de catálogo têm linhas globais; as demais seguem `_rls_tenant_match`.

DO $$
DECLARE
    tbl TEXT;
BEGIN
    FOREACH tbl IN ARRAY ARRAY['modelo_llm', 'mcp_server'] LOOP
        EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', tbl);
        EXECUTE format($f$
            CREATE POLICY tenant_isolation ON %I
              USING (empresa_id IS NULL OR _rls_tenant_match(empresa_id))
              WITH CHECK (_rls_tenant_match(empresa_id))
        $f$, tbl);
    END LOOP;
END $$;
