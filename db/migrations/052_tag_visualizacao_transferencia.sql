-- Sprint 5 — Paridade ZigChat (4 tabelas: tag, cliente_tag_v2,
-- atendimento_visualizacao, atendimento_transferencia + backfill).
--
-- Documentação: docs/zigchat/depara/04_pendentes_criar.md

-- ---- 1) Tag entity (substitui string em cliente_tag) ----
CREATE TABLE IF NOT EXISTS tag (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    nome TEXT NOT NULL,
    cor TEXT,                              -- hex pra UI
    descricao TEXT,
    -- Hook disparado quando tag aplicada (futuro: reativar campanha por tag)
    hook_id BIGINT REFERENCES hook(id) ON DELETE SET NULL,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    created_by_user_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (empresa_id, nome)
);

CREATE INDEX IF NOT EXISTS idx_tag_empresa
    ON tag (empresa_id) WHERE ativo;

-- ---- 2) Cliente-tag many-to-many v2 (FK em vez de string) ----
CREATE TABLE IF NOT EXISTS cliente_tag_v2 (
    cliente_id BIGINT NOT NULL REFERENCES cliente(id) ON DELETE CASCADE,
    tag_id BIGINT NOT NULL REFERENCES tag(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (cliente_id, tag_id)
);

CREATE INDEX IF NOT EXISTS idx_cliente_tag_v2_tag
    ON cliente_tag_v2 (tag_id);

-- Backfill: cria tag pra cada string distinta em cliente_tag
INSERT INTO tag (empresa_id, nome)
SELECT DISTINCT c.empresa_id, ct.tag
  FROM cliente_tag ct
  JOIN cliente c ON c.id = ct.cliente_id
ON CONFLICT (empresa_id, nome) DO NOTHING;

INSERT INTO cliente_tag_v2 (cliente_id, tag_id)
SELECT ct.cliente_id, t.id
  FROM cliente_tag ct
  JOIN cliente c ON c.id = ct.cliente_id
  JOIN tag t ON t.empresa_id = c.empresa_id AND t.nome = ct.tag
ON CONFLICT DO NOTHING;

COMMENT ON TABLE cliente_tag IS
    'DEPRECATED — usar cliente_tag_v2 + tag (mig 052). Removido em mig futura.';


-- ---- 3) Read receipts internos (quem viu cada atendimento) ----
CREATE TABLE IF NOT EXISTS atendimento_visualizacao (
    atendimento_id BIGINT NOT NULL REFERENCES atendimento(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    ultima_visualizacao_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (atendimento_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_atendimento_visualizacao_user
    ON atendimento_visualizacao (user_id, ultima_visualizacao_at DESC);


-- ---- 4) Histórico de transferências entre depto/atendentes ----
CREATE TABLE IF NOT EXISTS atendimento_transferencia (
    id BIGSERIAL PRIMARY KEY,
    atendimento_id BIGINT NOT NULL REFERENCES atendimento(id) ON DELETE CASCADE,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    -- Origem (NULL = bot/menu)
    de_user_id TEXT,
    de_departamento_id BIGINT REFERENCES departamento(id) ON DELETE SET NULL,
    de_agente_slug TEXT,
    -- Destino
    para_user_id TEXT,
    para_departamento_id BIGINT REFERENCES departamento(id) ON DELETE SET NULL,
    para_agente_slug TEXT,
    motivo TEXT,
    iniciado_por_user_id TEXT,             -- quem clicou em transferir (ou bot)
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_transferencia_atendimento
    ON atendimento_transferencia (atendimento_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_transferencia_empresa
    ON atendimento_transferencia (empresa_id, created_at DESC);
