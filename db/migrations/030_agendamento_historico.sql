-- S5 Calendar v2: audit trail de todas as mudanças em agendamento.
--
-- Ao contrário de agendamento.payload_externo (snapshot único do Google),
-- aqui guardamos um row por AÇÃO (criação, aprovação, reschedule,
-- cancelamento, sync_drift) com payload_diff opcional pra mostrar o
-- que mudou.
--
-- Consumido por:
-- - GET /api/agendamentos/{id}/historico (UI dashboard)
-- - Auditoria/compliance (LGPD: quem mudou o quê e quando)
-- - Detecção de problema operacional (drift sync, recusas em série)

CREATE TABLE IF NOT EXISTS agendamento_historico (
    id BIGSERIAL PRIMARY KEY,
    agendamento_id BIGINT NOT NULL
        REFERENCES agendamento(id) ON DELETE CASCADE,
    action TEXT NOT NULL,                          -- ex: 'created', 'approved', 'rescheduled', 'cancelled', 'sync_drift'
    actor_user_id TEXT,                            -- auth.user.id (operador) OU NULL (agente/sync)
    payload_diff JSONB NOT NULL DEFAULT '{}'::jsonb,
    at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agendamento_historico_ag
    ON agendamento_historico (agendamento_id, at DESC);

CREATE INDEX IF NOT EXISTS idx_agendamento_historico_action
    ON agendamento_historico (action, at DESC);
