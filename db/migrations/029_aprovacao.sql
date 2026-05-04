-- S4 Calendar v2: fluxo de aprovação de agendamento via WhatsApp.
--
-- Quando empresa ativa `agendamento_regras.requer_aprovacao=true`,
-- create_event não cria evento direto no Google: cria row em agendamento
-- com status='pendente' e dispara notify_gestor que:
-- 1. Cria row aqui com token uuid + status='pendente'
-- 2. Manda WhatsApp pro gestor: "APROVAR <token>" ou "REJEITAR <token>"
-- 3. Persiste mensagem_id_outbound (rastrear envio)
--
-- worker/processor.py intercepta a resposta do gestor (regex), decide,
-- e (se aprovado) cria o evento Google + UPDATE agendamento → confirmado.
--
-- Token uuid é incluso na mensagem pra evitar ambiguidade (gestor pode
-- ter múltiplos pedidos em paralelo) e prevenir replay (token único).

CREATE TABLE IF NOT EXISTS agendamento_aprovacao (
    id BIGSERIAL PRIMARY KEY,
    agendamento_id BIGINT NOT NULL
        REFERENCES agendamento(id) ON DELETE CASCADE,
    -- E.164 (`+55...`). Cópia do empresa_calendar_config.aprovador_telefone
    -- no momento da criação (snapshot — admin pode trocar depois sem
    -- afetar pedidos pendentes).
    gestor_telefone TEXT NOT NULL,
    -- Opcional: se gestor está em auth.user (futuro RBAC pra audit)
    gestor_user_id TEXT,
    status TEXT NOT NULL DEFAULT 'pendente'
        CHECK (status IN ('pendente', 'aprovado', 'rejeitado', 'expirado')),
    -- Token incluso na mensagem WhatsApp ("APROVAR <token>")
    token UUID NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    -- Id retornado pelo OutboundClient (Twilio SID ou Evolution key.id)
    mensagem_id_outbound TEXT,
    decided_at TIMESTAMPTZ,
    motivo TEXT,                                  -- texto livre do gestor após APROVAR/REJEITAR
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_aprovacao_status_pending
    ON agendamento_aprovacao (gestor_telefone, status)
    WHERE status = 'pendente';

CREATE INDEX IF NOT EXISTS idx_aprovacao_agendamento
    ON agendamento_aprovacao (agendamento_id);

-- Telefone do gestor que recebe os pedidos. NULL = sem fluxo ativo
-- (mesmo se requer_aprovacao=true, sem telefone não envia).
ALTER TABLE empresa_calendar_config
    ADD COLUMN IF NOT EXISTS aprovador_telefone TEXT;
