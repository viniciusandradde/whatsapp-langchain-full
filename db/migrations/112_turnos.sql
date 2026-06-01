-- Sprint U (Fase 2) — Turnos / jornada de trabalho (paridade ZigChat
-- `Turno`/`TurnoHorario`). Janelas de horário por usuário que podem servir
-- de gate de distribuição de fila.
--
-- 3 tabelas:
--   turno          — cabeçalho (nome, ativo) por empresa
--   turno_horario  — janelas por dia da semana (0=Dom..6=Sáb) de um turno
--   usuario_turno  — atribuição M:N usuário↔turno
--
-- turno_horario NÃO tem empresa_id (tenant via FK turno_id) — segue a
-- convenção da mig 101 (tabelas FK-indiretas ficam fora da RLS; acesso
-- controlado via JOIN com o parent + app).

CREATE TABLE IF NOT EXISTS turno (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    nome TEXT NOT NULL,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (empresa_id, nome)
);

CREATE TABLE IF NOT EXISTS turno_horario (
    id BIGSERIAL PRIMARY KEY,
    turno_id BIGINT NOT NULL REFERENCES turno(id) ON DELETE CASCADE,
    dia_semana SMALLINT NOT NULL CHECK (dia_semana BETWEEN 0 AND 6),
    hora_inicio TIME NOT NULL,
    hora_fim TIME NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_turno_horario_turno
    ON turno_horario (turno_id);

CREATE TABLE IF NOT EXISTS usuario_turno (
    user_id TEXT NOT NULL,
    turno_id BIGINT NOT NULL REFERENCES turno(id) ON DELETE CASCADE,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, turno_id, empresa_id)
);

CREATE INDEX IF NOT EXISTS idx_usuario_turno_user
    ON usuario_turno (user_id, empresa_id);

-- RLS uniforme nas tabelas com empresa_id (turno_horario é FK-indireta).
DO $$
DECLARE
    t TEXT;
BEGIN
    FOREACH t IN ARRAY ARRAY['turno', 'usuario_turno']
    LOOP
        EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
        EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', t);
        EXECUTE format('DROP POLICY IF EXISTS tenant_isolation ON %I', t);
        EXECUTE format(
            'CREATE POLICY tenant_isolation ON %I '
            'USING (_rls_tenant_match(empresa_id)) '
            'WITH CHECK (_rls_tenant_match(empresa_id))',
            t
        );
    END LOOP;
END $$;
