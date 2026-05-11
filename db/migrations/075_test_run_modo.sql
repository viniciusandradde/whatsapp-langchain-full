-- Sprint Eval-UI — distingue runs E2E vs eval no histórico /relatorios/allure.
--
-- 'e2e'          → pytest tests/e2e/ -m docker_demo (comportamento original)
-- 'eval-online'  → pytest tests/eval/ com EVAL_SOURCE=langsmith
-- 'eval-offline' → pytest tests/eval/ com EVAL_SOURCE=local (goldens.json)

ALTER TABLE test_run
    ADD COLUMN IF NOT EXISTS modo TEXT NOT NULL DEFAULT 'e2e';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'test_run_modo_check'
    ) THEN
        ALTER TABLE test_run
            ADD CONSTRAINT test_run_modo_check
            CHECK (modo IN ('e2e', 'eval-online', 'eval-offline'));
    END IF;
END $$;
