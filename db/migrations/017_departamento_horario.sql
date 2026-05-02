-- M6.a Departamento + Horário de funcionamento + Feriado.
--
-- - departamento: categorização opcional pra atendimento (suporte, vendas...)
-- - horario_funcionamento: quando a empresa está aberta. Por dia da
--   semana (0=domingo .. 6=sábado), opcionalmente filtrado por
--   departamento (NULL = horário geral).
-- - feriado: override (empresa fechada na data inteira) por empresa.
-- - atendimento.departamento_id: FK NULL — atendimento pode ser
--   classificado pra direcionar pra equipe certa.
--
-- Timezone vem de empresa_calendar_config (M5.a) com fallback
-- America/Sao_Paulo no helper.

CREATE TABLE IF NOT EXISTS departamento (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    nome TEXT NOT NULL,
    descricao TEXT,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    created_by_user_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (empresa_id, nome)
);

CREATE INDEX IF NOT EXISTS idx_departamento_empresa
    ON departamento(empresa_id) WHERE ativo;

CREATE TABLE IF NOT EXISTS horario_funcionamento (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    -- 0=domingo, 1=segunda, ..., 6=sábado (compat ISO Python `weekday`+1 mod 7)
    dia_semana SMALLINT NOT NULL CHECK (dia_semana BETWEEN 0 AND 6),
    hora_inicio TIME NOT NULL,
    hora_fim TIME NOT NULL,
    -- NULL = aplica à empresa toda (horário "geral")
    departamento_id BIGINT REFERENCES departamento(id) ON DELETE CASCADE,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Janela inválida (fim <= início) é proibida; admin pode fazer
    -- almoço criando 2 rows pro mesmo dia (ex: 09:00-12:00 e 13:00-18:00).
    CHECK (hora_fim > hora_inicio)
);

CREATE INDEX IF NOT EXISTS idx_horario_empresa_dia
    ON horario_funcionamento(empresa_id, dia_semana) WHERE ativo;

CREATE TABLE IF NOT EXISTS feriado (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    data DATE NOT NULL,
    descricao TEXT,
    created_by_user_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (empresa_id, data)
);

CREATE INDEX IF NOT EXISTS idx_feriado_empresa_data
    ON feriado(empresa_id, data);

-- atendimento ganha departamento_id (FK opcional). SET NULL no delete pra
-- não perder histórico de atendimento se um departamento for removido.
ALTER TABLE atendimento
    ADD COLUMN IF NOT EXISTS departamento_id BIGINT
        REFERENCES departamento(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_atendimento_departamento
    ON atendimento(departamento_id) WHERE departamento_id IS NOT NULL;
