-- 180 — Alertas de degradação de IA (módulo Saúde de IA, F4).
--
-- Detecção DETERMINÍSTICA no tick do worker (shared/ia_alertas.py), sobre a
-- série que a mig 178 já coleta + a nossa operação (ia_execucao): uptime
-- abaixo do piso, latência acima de 2× o baseline 7d, throughput na metade,
-- taxa de erro própria alta, modelo sumido dos endpoints. Nenhum LLM decide
-- alerta — mesmo racional do scripts/producao_checks.py: limiar visível e
-- testável, não implícito na cabeça de um modelo.
--
-- Uma linha por episódio; (tipo, modelo_slug) ativo é ÚNICO (índice parcial)
-- — o tick atualiza `detalhe` em vez de duplicar. Auto-resolve preenche
-- `resolvido_em` quando a condição limpa; reabertura dentro do cooldown de
-- 6h reativa a MESMA linha sem nova notificação (anti-flap).
--
-- Escopo de plataforma, sem empresa_id/RLS (padrão migs 173/178/179).

CREATE TABLE IF NOT EXISTS ia_alerta (
    id            BIGSERIAL PRIMARY KEY,
    tipo          TEXT NOT NULL,      -- uptime|latencia|throughput|erros_proprios|modelo_sumiu
    modelo_slug   TEXT NOT NULL,
    detalhe       JSONB NOT NULL DEFAULT '{}'::jsonb,  -- {valor, limiar, baseline, ...}
    criado_em     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolvido_em  TIMESTAMPTZ,
    notificado_em TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_ia_alerta_ativo
    ON ia_alerta (tipo, modelo_slug) WHERE resolvido_em IS NULL;
CREATE INDEX IF NOT EXISTS idx_ia_alerta_recentes
    ON ia_alerta (criado_em DESC);
