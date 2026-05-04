-- S2 Calendar v2: source-of-truth interno de agendamentos.
--
-- Espelha eventos do Google Calendar com governança local: status
-- pendente/confirmado/cancelado, vínculo opcional a cliente/atendimento,
-- snapshot do payload externo pra auditoria, audit timestamps.
--
-- Pre-requisito do fluxo de aprovação (S4): aqui só guardamos o evento.
-- A coluna `aprovado` fica TRUE por default (sem fluxo) e vira FALSE
-- quando S4 introduzir requer_aprovacao em agendamento_regras.

CREATE TABLE IF NOT EXISTS agendamento (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    -- Calendar onde o evento foi criado (snapshot — empresa pode trocar
    -- o ativo depois sem afetar histórico).
    calendar_id TEXT NOT NULL DEFAULT 'primary',
    -- Quem criou: auth.user.id (operador) OU NULL quando criado pelo agente
    user_id_criador TEXT,
    -- Vínculo opcional ao CRM (M3). Quando agente cria via WhatsApp,
    -- amarra ao cliente da conversa.
    cliente_id BIGINT REFERENCES cliente(id) ON DELETE SET NULL,
    -- Google event id retornado pelo events.insert. Pode ser NULL
    -- transitoriamente entre INSERT local e response do Google.
    evento_id_externo TEXT,
    summary TEXT NOT NULL,
    descricao TEXT,
    data_inicio TIMESTAMPTZ NOT NULL,
    data_fim TIMESTAMPTZ NOT NULL,
    status TEXT NOT NULL DEFAULT 'confirmado'
        CHECK (status IN ('pendente', 'confirmado', 'cancelado')),
    aprovado BOOLEAN NOT NULL DEFAULT TRUE,
    gestor_notificado BOOLEAN NOT NULL DEFAULT FALSE,
    -- Snapshot do payload Google (htmlLink, attendees, organizer, etc).
    payload_externo JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Index principal: queries por empresa + período (UI dashboard, agente
-- listando, gestor revisando).
CREATE INDEX IF NOT EXISTS idx_agendamento_empresa_inicio
    ON agendamento (empresa_id, data_inicio DESC);

-- Lookup por evento_id_externo pra reconciliar webhook futuro do Google
-- (drift detection em S5).
CREATE INDEX IF NOT EXISTS idx_agendamento_evento_externo
    ON agendamento (evento_id_externo)
    WHERE evento_id_externo IS NOT NULL;

-- Lookup por cliente pra histórico CRM.
CREATE INDEX IF NOT EXISTS idx_agendamento_cliente
    ON agendamento (cliente_id, data_inicio DESC)
    WHERE cliente_id IS NOT NULL;
