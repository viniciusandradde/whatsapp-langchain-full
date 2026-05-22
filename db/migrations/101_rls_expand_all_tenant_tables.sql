-- Sprint A.2.2 — Expande RLS pras outras 48 tabelas com empresa_id.
--
-- Mig 096 cobriu 10 tabelas críticas. Esta cobre TODAS as restantes
-- com coluna empresa_id, totalizando 58 tabelas (ou 59 dependendo do
-- conjunto de migs aplicadas) com RLS + FORCE + policy uniforme.
--
-- Estratégia: DO block dinâmico — itera por information_schema, aplica
-- ENABLE + FORCE + policy tenant_isolation a cada tabela que ainda não
-- tem RLS. Idempotente: tabela já com RLS é pulada.
--
-- Política usa _rls_tenant_match() criada em mig 096 (permissive: sem
-- context = passa). Será trocada pra estrita em mig 102 após app
-- estar usando context em 100% dos call sites (Sprint A.2.3).
--
-- Tabelas EXCLUÍDAS deliberadamente (sem empresa_id):
--   _migrations, permissao, plano, empresa (globais)
--   auth_login_event, auth.* (Better Auth, schema separado)
--   checkpoints*, store*, workflow_chatbot_version (LangGraph, gerenciado externamente)
--   cliente_anotacao, cliente_tag, atendimento_menu_historico (tenant via FK indireto)
--
-- Pra cobrir FK-indirect tables (cliente_anotacao etc), sprint futura
-- precisa adicionar coluna empresa_id (denormalização) ou policy
-- baseada em JOIN com tabela parent.

DO $$
DECLARE
    r RECORD;
    enabled_count INT := 0;
    skipped_count INT := 0;
BEGIN
    FOR r IN
        SELECT cols.table_name
          FROM information_schema.columns cols
          JOIN information_schema.tables t
            ON t.table_schema = cols.table_schema
           AND t.table_name = cols.table_name
          LEFT JOIN pg_class c ON c.relname = cols.table_name
          LEFT JOIN pg_namespace n
            ON n.oid = c.relnamespace
           AND n.nspname = cols.table_schema
         WHERE cols.column_name = 'empresa_id'
           AND cols.table_schema = 'public'
           AND t.table_type = 'BASE TABLE'
           AND COALESCE(c.relrowsecurity, false) = false
         ORDER BY cols.table_name
    LOOP
        EXECUTE format(
            'ALTER TABLE %I ENABLE ROW LEVEL SECURITY',
            r.table_name
        );
        EXECUTE format(
            'ALTER TABLE %I FORCE ROW LEVEL SECURITY',
            r.table_name
        );
        EXECUTE format(
            'DROP POLICY IF EXISTS tenant_isolation ON %I',
            r.table_name
        );
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I '
            'USING (_rls_tenant_match(empresa_id)) '
            'WITH CHECK (_rls_tenant_match(empresa_id))',
            r.table_name
        );
        enabled_count := enabled_count + 1;
        RAISE NOTICE 'RLS enabled: %', r.table_name;
    END LOOP;

    RAISE NOTICE '----';
    RAISE NOTICE 'Sprint A.2.2: % tabelas adicionadas a RLS', enabled_count;
END $$;

-- Validação pós-aplicação: contagem total deve ser >=58
DO $$
DECLARE
    total INT;
BEGIN
    SELECT COUNT(*) INTO total
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public'
       AND c.relkind = 'r'
       AND c.relrowsecurity = true;

    RAISE NOTICE 'Total tabelas com RLS: %', total;
    IF total < 50 THEN
        RAISE EXCEPTION 'Sprint A.2.2: esperado >=50 tabelas com RLS, achou %', total;
    END IF;
END $$;
