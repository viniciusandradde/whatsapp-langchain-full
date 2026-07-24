-- Auto-dataset via Langfuse (Fase 1) — rastreabilidade + idempotência.
--
-- `fewshot_example` passa a registrar a ORIGEM de cada exemplo e, quando vem
-- de uma trace do Langfuse (score NPS alto), o `source_trace_id`. O índice
-- único parcial garante que re-rodar a ingestão NÃO duplica: cada trace vira
-- no máximo 1 few-shot por empresa (ON CONFLICT DO NOTHING).
--
--   fonte           — capture (trigger SQL) | import (upload) | langfuse
--   source_trace_id — id da trace Langfuse (só quando fonte='langfuse')

ALTER TABLE fewshot_example
    ADD COLUMN IF NOT EXISTS source_trace_id TEXT,
    ADD COLUMN IF NOT EXISTS fonte TEXT NOT NULL DEFAULT 'capture';

-- Idempotência do re-run: 1 trace → no máx 1 few-shot por empresa.
CREATE UNIQUE INDEX IF NOT EXISTS ux_fewshot_source_trace
    ON fewshot_example (empresa_id, source_trace_id)
    WHERE source_trace_id IS NOT NULL;
