-- Sprint B.2 — Campos Asaas em empresa + index pra webhook lookup
--
-- Schema billing (`plano` + `transacao`) já existe desde mig 059. Esta
-- adiciona apenas o que falta pra integração Asaas:
--
-- empresa.asaas_customer_id — id do customer no Asaas (1:1 com empresa,
--   UNIQUE). Preenchido na 1ª subscription criada.
-- empresa.asaas_subscription_id — id da subscription ATIVA (FK lógica).
--   Pode ser NULL (plano Free não tem subscription Asaas).
-- transacao.gateway_id já existe — vai armazenar asaas payment_id.
-- transacao.gateway já existe — vai armazenar 'asaas'.
--
-- Index novo em (gateway, gateway_id) pra resolver webhook em O(1):
-- webhook Asaas envia payment.id, precisamos achar a transacao local
-- correspondente sem table scan.
--
-- billing_event_log: audit de TODO webhook recebido. Append-only.
-- Investigação de bug ou auditoria fiscal precisa da sequência completa.

-- 1) Colunas empresa
ALTER TABLE empresa
    ADD COLUMN IF NOT EXISTS asaas_customer_id TEXT,
    ADD COLUMN IF NOT EXISTS asaas_subscription_id TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_empresa_asaas_customer
    ON empresa (asaas_customer_id)
    WHERE asaas_customer_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_empresa_asaas_subscription
    ON empresa (asaas_subscription_id)
    WHERE asaas_subscription_id IS NOT NULL;

COMMENT ON COLUMN empresa.asaas_customer_id IS
    'Sprint B — Customer ID no Asaas (1:1 com empresa). Preenchido na '
    '1ª criação de subscription via POST /api/billing/checkout.';
COMMENT ON COLUMN empresa.asaas_subscription_id IS
    'Sprint B — Subscription ID ativa no Asaas. NULL = plano free ou '
    'subscription cancelada (mantém histórico em transacao).';

-- 2) Index lookup webhook
CREATE INDEX IF NOT EXISTS idx_transacao_gateway_lookup
    ON transacao (gateway, gateway_id)
    WHERE gateway IS NOT NULL AND gateway_id IS NOT NULL;

-- 3) Audit log de webhooks Asaas
CREATE TABLE IF NOT EXISTS billing_event_log (
    id              BIGSERIAL PRIMARY KEY,
    received_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event_type      TEXT        NOT NULL,
    asaas_payment_id   TEXT,
    asaas_customer_id  TEXT,
    asaas_subscription_id TEXT,
    empresa_id      BIGINT REFERENCES empresa(id) ON DELETE SET NULL,
    transacao_id    BIGINT REFERENCES transacao(id) ON DELETE SET NULL,
    payload         JSONB       NOT NULL,
    processado      BOOLEAN     NOT NULL DEFAULT FALSE,
    erro            TEXT
);

CREATE INDEX IF NOT EXISTS idx_billing_event_received
    ON billing_event_log (received_at DESC);
CREATE INDEX IF NOT EXISTS idx_billing_event_payment
    ON billing_event_log (asaas_payment_id)
    WHERE asaas_payment_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_billing_event_empresa
    ON billing_event_log (empresa_id, received_at DESC)
    WHERE empresa_id IS NOT NULL;

COMMENT ON TABLE billing_event_log IS
    'Sprint B — audit append-only de webhooks Asaas. Nenhuma row é '
    'deletada (compliance fiscal). processado=true após handler updateu '
    'transacao com sucesso; processado=false fica pra retry manual.';

-- 4) View resumo billing por empresa
CREATE OR REPLACE VIEW empresa_billing_status AS
SELECT
    e.id            AS empresa_id,
    e.nome          AS empresa_nome,
    e.plano         AS plano_atual,
    e.asaas_customer_id,
    e.asaas_subscription_id,
    p.preco_mensal_brl AS valor_mensal,
    (
        SELECT count(*) FROM transacao t
         WHERE t.empresa_id = e.id AND t.status = 'pago'
    ) AS total_pagamentos,
    (
        SELECT max(t.pago_em) FROM transacao t
         WHERE t.empresa_id = e.id AND t.status = 'pago'
    ) AS ultimo_pagamento_em,
    (
        SELECT count(*) FROM transacao t
         WHERE t.empresa_id = e.id AND t.status = 'pendente'
    ) AS pendentes
FROM empresa e
LEFT JOIN plano p ON p.id = e.plano_id
WHERE e.status = 'active'
ORDER BY e.id;

COMMENT ON VIEW empresa_billing_status IS
    'Sprint B audit — billing por empresa. Esperado: free → '
    'asaas_subscription_id NULL; pro/enterprise → subscription_id '
    'preenchido após primeiro pagamento.';
