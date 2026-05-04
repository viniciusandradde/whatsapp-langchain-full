-- S3 Calendar v2: regras de negócio por empresa pra agendamento.
--
-- Centraliza governança de horário num único row por empresa. Lido por:
-- - find_free_slots: filtra slots gerados pra ficar dentro da janela
-- - validate_request: rejeita create_event fora das regras antes do Google
-- - validate_request: aplica antecedência mínima e dias bloqueados
--
-- Defaults sensatos (08-18, seg-sex, 1h antecedência) — empresa pode
-- editar via PUT /api/calendar/regras (admin-only).
--
-- `requer_aprovacao` é placeholder pra S4 (fluxo via WhatsApp). Em S3
-- fica FALSE por default e não tem efeito.

CREATE TABLE IF NOT EXISTS agendamento_regras (
    empresa_id BIGINT PRIMARY KEY REFERENCES empresa(id) ON DELETE CASCADE,
    -- Janela de horário comercial em hora local (timezone vem de
    -- empresa_calendar_config.timezone). 08:00 → 18:00 default.
    hora_inicio TIME NOT NULL DEFAULT '08:00',
    hora_fim TIME NOT NULL DEFAULT '18:00',
    -- Antecedência mínima entre agora e o início do agendamento.
    -- Default 60min: cliente não pode agendar pra "daqui a 5 min".
    antecedencia_minima_minutos INTEGER NOT NULL DEFAULT 60,
    -- Buffer entre 2 agendamentos consecutivos (S3 não usa diretamente
    -- pra rejeitar conflito — find_free_slots já garante via freebusy).
    -- Reservado pra futuro.
    intervalo_entre_minutos INTEGER NOT NULL DEFAULT 0,
    -- Array ISO 8601 weekday: 1=segunda, 7=domingo. Default seg-sex.
    dias_semana_permitidos JSONB NOT NULL DEFAULT '[1,2,3,4,5]'::jsonb,
    -- Array de datas YYYY-MM-DD bloqueadas (feriados, férias).
    dias_bloqueados JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- S4 placeholder — em S3 não tem efeito.
    requer_aprovacao BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Sanity checks: hora_fim > hora_inicio, intervalos >= 0
    CONSTRAINT chk_horario_valido CHECK (hora_fim > hora_inicio),
    CONSTRAINT chk_antecedencia_nonneg CHECK (antecedencia_minima_minutos >= 0),
    CONSTRAINT chk_intervalo_nonneg CHECK (intervalo_entre_minutos >= 0)
);
