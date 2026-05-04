-- Generic rate limit buckets (E1.3): além do limite por phone_number do
-- webhook (mig 005), agora temos buckets por chave arbitrária — usado
-- pra limitar IP no login Better Auth e user_id em endpoints admin.
--
-- Schema é genérico (bucket_key text), permite múltiplos consumidores:
-- - "ip:1.2.3.4:auth.signin" → 5 req / 15min
-- - "user:abc-123:admin"     → 60 req / min
-- - "ip:1.2.3.4:invite"      → 10 req / hora
--
-- O `window_start` é o início do bucket (truncado pelo caller — minute,
-- hour, etc); count incrementa via UPSERT idempotente.
--
-- Cleanup inline probabilístico (~1% das requisições) apaga buckets
-- expirados (mais que 24h), mesmo padrão da mig 005.
CREATE TABLE IF NOT EXISTS rate_limit_bucket (
    bucket_key TEXT NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    request_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (bucket_key, window_start)
);

CREATE INDEX IF NOT EXISTS idx_rate_limit_bucket_window
    ON rate_limit_bucket (window_start);
