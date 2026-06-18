-- Disparador (anti-ban) — teto diário por conexão + aquecimento (warm-up).
--
-- Lição do incidente da campanha 9 (número RESTRINGIDO pela Meta): número novo
-- + volume alto = sinal de spam. As melhores práticas (docs/DISPARO_MASSA_
-- BEST_PRACTICES.md) recomendam um TETO DIÁRIO de mensagens por número e um
-- AQUECIMENTO gradual em número novo (dia1≈20, ~1.8x/dia até estabilizar).
--
-- Modelo:
--   conexao.daily_send_cap      — teto manual de envios/dia (NULL = sem teto).
--   conexao.warmup_started_at   — início do aquecimento (NULL = sem aquecimento).
--     Quando setado, o teto EFETIVO do dia é o menor entre o teto manual e a
--     curva de aquecimento calculada a partir dos dias decorridos.
--   conexao_envio_diario        — contador de envios por (conexao, dia) usado
--     pelo dispatcher pra saber quanto já saiu hoje e parar no teto.
--
-- Quando o teto do dia é atingido no meio de uma campanha, o dispatcher NÃO
-- aborta: reagenda a campanha (status 'scheduled') pro próximo dia e o poller
-- retoma os pendentes — o disparo "pinga" ao longo dos dias, que é exatamente
-- o comportamento de aquecimento desejado.

ALTER TABLE conexao
    ADD COLUMN IF NOT EXISTS daily_send_cap INTEGER,
    ADD COLUMN IF NOT EXISTS warmup_started_at TIMESTAMPTZ;

-- teto >= 1 quando setado (defesa em profundidade; a UI também valida).
ALTER TABLE conexao
    DROP CONSTRAINT IF EXISTS chk_conexao_daily_cap_pos;
ALTER TABLE conexao
    ADD CONSTRAINT chk_conexao_daily_cap_pos
    CHECK (daily_send_cap IS NULL OR daily_send_cap >= 1);

-- Contador de envios por conexão por dia (incrementado a cada envio bem
-- sucedido do dispatcher). UNIQUE (conexao_id, dia) → UPSERT idempotente.
CREATE TABLE IF NOT EXISTS conexao_envio_diario (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    conexao_id BIGINT NOT NULL REFERENCES conexao(id) ON DELETE CASCADE,
    dia DATE NOT NULL,
    enviados INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (conexao_id, dia)
);

CREATE INDEX IF NOT EXISTS idx_conexao_envio_diario_lookup
    ON conexao_envio_diario (conexao_id, dia);

-- RLS uniforme (tabela com empresa_id) — espelha mig 111/112.
DO $$
BEGIN
    EXECUTE 'ALTER TABLE conexao_envio_diario ENABLE ROW LEVEL SECURITY';
    EXECUTE 'ALTER TABLE conexao_envio_diario FORCE ROW LEVEL SECURITY';
    EXECUTE 'DROP POLICY IF EXISTS tenant_isolation ON conexao_envio_diario';
    EXECUTE
        'CREATE POLICY tenant_isolation ON conexao_envio_diario '
        'USING (_rls_tenant_match(empresa_id)) '
        'WITH CHECK (_rls_tenant_match(empresa_id))';
END $$;
