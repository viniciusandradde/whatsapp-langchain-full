-- M4.d Webhooks configuráveis: hooks HTTP que disparam quando eventos
-- internos acontecem (mensagem inbound, atendimento aberto/fechado/transferido).
-- Despachados async pelo dispatcher; cada tentativa entra em hook_log.

CREATE TABLE IF NOT EXISTS hook (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    nome TEXT NOT NULL,
    evento TEXT NOT NULL CHECK (evento IN (
        'mensagem.recebida',
        'atendimento.aberto',
        'atendimento.atendido',
        'atendimento.fechado',
        'atendimento.transferido'
    )),
    url TEXT NOT NULL,
    secret TEXT,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    created_by_user_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Lookup principal do dispatcher: empresa+evento ativos.
CREATE INDEX IF NOT EXISTS idx_hook_empresa_evento_ativo
    ON hook (empresa_id, evento) WHERE ativo;

-- Auditoria de tentativas. Linha por dispatch (sucesso ou falha).
CREATE TABLE IF NOT EXISTS hook_log (
    id BIGSERIAL PRIMARY KEY,
    hook_id BIGINT NOT NULL REFERENCES hook(id) ON DELETE CASCADE,
    evento TEXT NOT NULL,
    payload JSONB NOT NULL,
    status_code INTEGER,
    response_body TEXT,
    error TEXT,
    duration_ms INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hook_log_hook
    ON hook_log (hook_id, created_at DESC);
