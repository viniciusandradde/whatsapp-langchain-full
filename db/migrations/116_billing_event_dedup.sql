-- R9 — Idempotência do webhook Asaas.
--
-- Asaas reentrega o MESMO webhook quando não recebe 2xx no prazo. Sem dedup,
-- process_asaas_webhook reprocessava o evento (e billing_event_log acumulava
-- duplicatas), apesar da docstring afirmar idempotência. Combinado com o
-- handler passando a retornar 5xx em falha de infra (pra Asaas retentar e não
-- PERDER a confirmação de pagamento), a dedup é o que torna o retry seguro.
--
-- dedup_key = event.id do Asaas (quando presente) ou uma chave sintetizada
-- `event_type:payment_id|subscription_id`. NULL = evento sem chave identificável
-- (mantém o comportamento antigo de sempre inserir; NULLs são distintos no
-- índice UNIQUE do Postgres).
ALTER TABLE billing_event_log
    ADD COLUMN IF NOT EXISTS dedup_key TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_billing_event_dedup
    ON billing_event_log (dedup_key);
