-- Sliding-window por hora cheia, compartilhado entre réplicas da API.
-- A row existe enquanto o bucket é relevante; cleanup é feito inline
-- (probabilístico, 1% das requisições) pra evitar dependência de cron.
CREATE TABLE IF NOT EXISTS rate_limit_buckets (
    phone_number TEXT NOT NULL,
    hour_start TIMESTAMPTZ NOT NULL,
    request_count INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (phone_number, hour_start)
);

CREATE INDEX IF NOT EXISTS idx_rate_limit_buckets_hour
    ON rate_limit_buckets (hour_start);
