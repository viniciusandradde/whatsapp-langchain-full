-- M3 CRM Light: Cliente como entidade primeira-classe + Atendimento
-- como conversa estruturada com status / atribuição / transferência.

-- cliente: pessoa cadastrada na empresa (1 row por empresa+telefone).
CREATE TABLE IF NOT EXISTS cliente (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    telefone TEXT NOT NULL,
    nome TEXT,
    email TEXT,
    doc TEXT,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'archived', 'blocked')),
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (empresa_id, telefone)
);

CREATE INDEX IF NOT EXISTS idx_cliente_empresa
    ON cliente (empresa_id, status, updated_at DESC);

-- cliente_anotacao: notas livres de um operador sobre um cliente.
CREATE TABLE IF NOT EXISTS cliente_anotacao (
    id BIGSERIAL PRIMARY KEY,
    cliente_id BIGINT NOT NULL REFERENCES cliente(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    conteudo TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_cliente_anotacao_cliente
    ON cliente_anotacao (cliente_id, created_at DESC);

-- cliente_tag: marcadores por cliente (1 row por par cliente+tag).
CREATE TABLE IF NOT EXISTS cliente_tag (
    cliente_id BIGINT NOT NULL REFERENCES cliente(id) ON DELETE CASCADE,
    tag TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (cliente_id, tag)
);

-- atendimento: 1 conversa estruturada (status, atribuição, transferência).
-- Política: 1 atendimento "aberto" por (empresa_id, cliente_id, conexao_id)
-- ao mesmo tempo. Status segue queue/CRM mainstream:
-- 'aguardando' (sem atribuição) → 'em_andamento' (claim) → 'resolvido' / 'abandonado'
CREATE TABLE IF NOT EXISTS atendimento (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    cliente_id BIGINT NOT NULL REFERENCES cliente(id) ON DELETE CASCADE,
    conexao_id BIGINT NOT NULL REFERENCES conexao(id) ON DELETE RESTRICT,
    agente_atual TEXT NOT NULL DEFAULT 'vsa_tech',
    status TEXT NOT NULL DEFAULT 'aguardando'
        CHECK (status IN ('aguardando', 'em_andamento', 'resolvido', 'abandonado')),
    assigned_to_user_id TEXT,
    last_message_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Garante 1 atendimento aberto por (empresa, cliente, conexão).
-- Status final ('resolvido' / 'abandonado') sai do índice — o próximo
-- inbound abre um novo atendimento.
CREATE UNIQUE INDEX IF NOT EXISTS idx_atendimento_aberto_unique
    ON atendimento (empresa_id, cliente_id, conexao_id)
    WHERE status IN ('aguardando', 'em_andamento');

CREATE INDEX IF NOT EXISTS idx_atendimento_empresa_status
    ON atendimento (empresa_id, status, last_message_at DESC);

CREATE INDEX IF NOT EXISTS idx_atendimento_assigned
    ON atendimento (empresa_id, assigned_to_user_id, last_message_at DESC)
    WHERE status = 'em_andamento';

-- atendimento_id em message_queue (nullable: rows antigas ficam NULL).
ALTER TABLE message_queue
    ADD COLUMN IF NOT EXISTS atendimento_id BIGINT
    REFERENCES atendimento(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_message_queue_atendimento
    ON message_queue (atendimento_id, created_at DESC);
