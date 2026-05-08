-- 063_test_run.sql
-- Sprint L — UI de Test Runner E2E.
-- Tabela `test_run` rastreia bateria E2E disparada via /api/admin/tests/run.
-- 1 run por vez (guard via SELECT WHERE status='running' antes de INSERT).
--
-- Campos:
-- - status: queued|running|passed|failed|error
-- - filtro: -k expression do pytest (NULL = roda todos os 32 cenários)
-- - storage_path: tests/reports/runs/{id}/ relativo ao repo
-- - pid: PID do subprocess pytest pra SIGTERM via /kill

CREATE TABLE IF NOT EXISTS test_run (
    id BIGSERIAL PRIMARY KEY,
    started_by_user_id TEXT REFERENCES auth."user"(id) ON DELETE SET NULL,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL CHECK (
        status IN ('queued','running','passed','failed','error')
    ),
    filtro TEXT,
    total INT,
    passed INT,
    failed INT,
    duration_seconds NUMERIC,
    pid INT,
    storage_path TEXT NOT NULL,
    log_size_bytes BIGINT NOT NULL DEFAULT 0,
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS idx_test_run_started ON test_run (started_at DESC);
CREATE INDEX IF NOT EXISTS idx_test_run_status ON test_run (status)
    WHERE status IN ('queued', 'running');
