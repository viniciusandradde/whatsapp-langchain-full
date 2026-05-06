-- Sprint 6 — Paridade ZigChat (Formulários reutilizáveis).
--
-- Documentação: docs/zigchat/depara/04_pendentes_criar.md
--
-- Lead capture, CSAT, NPS — formulários estruturados que vinculam a
-- atendimento ou cliente. Campos definidos como JSONB pra flexibilidade
-- (sem schema rígido).

CREATE TABLE IF NOT EXISTS form_padrao (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    nome TEXT NOT NULL,
    descricao TEXT,
    -- Estrutura: [{nome, tipo, obrigatorio, opcoes, validacao, label}, ...]
    -- tipos: text/email/phone/select/checkbox/scale/longtext
    campos JSONB NOT NULL DEFAULT '[]'::jsonb,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    created_by_user_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (empresa_id, nome)
);

CREATE INDEX IF NOT EXISTS idx_form_padrao_empresa
    ON form_padrao (empresa_id) WHERE ativo;

CREATE TABLE IF NOT EXISTS form_resposta (
    id BIGSERIAL PRIMARY KEY,
    form_id BIGINT NOT NULL REFERENCES form_padrao(id) ON DELETE CASCADE,
    cliente_id BIGINT REFERENCES cliente(id) ON DELETE SET NULL,
    atendimento_id BIGINT REFERENCES atendimento(id) ON DELETE SET NULL,
    -- Estrutura: {nome_campo: valor, ...}
    respostas JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_form_resposta_form
    ON form_resposta (form_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_form_resposta_cliente
    ON form_resposta (cliente_id) WHERE cliente_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_form_resposta_atendimento
    ON form_resposta (atendimento_id) WHERE atendimento_id IS NOT NULL;
