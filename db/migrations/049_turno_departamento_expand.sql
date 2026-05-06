-- Sprint 4 — Paridade ZigChat (Turno reutilizável + departamento expand).
--
-- Documentação: docs/zigchat/depara/03_gap_grande.md + 04_pendentes_criar.md
--
-- Cria turno: escala compartilhável entre departamentos (ex: "Comercial 9-18",
-- "24x7", "Plantão noite") em vez de cada depto ter seu próprio horário.
--
-- Adiciona ao departamento:
--   - turno_id: FK pra turno (nice-to-have — preserva horario_funcionamento legacy)
--   - posicao_fila_transferencia: ordem de fallback quando outros depto cheios
--   - encerra_atendimento: flag se transfer pro depto fecha atendimento
--   - tolerancia_atend_inativo_min: minutos antes de marcar atendimento inativo
--   - enviar_fila_atendimento: flag pra mandar "você é o N na fila"
--   - menu_coleta_id: menu específico de coleta atrelado ao depto
--   - retencao_msg_dias: dias de retenção de mensagens

CREATE TABLE IF NOT EXISTS turno (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    nome TEXT NOT NULL,                  -- "Comercial 9-18", "24x7", "Plantão noite"
    -- Estrutura: [{dia_semana: 1, inicio: "09:00", fim: "18:00"}, ...]
    -- dia_semana: 0=domingo, 1=segunda, ..., 6=sábado
    horarios JSONB NOT NULL DEFAULT '[]'::jsonb,
    fuso_horario TEXT NOT NULL DEFAULT 'America/Sao_Paulo',
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    created_by_user_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (empresa_id, nome)
);

CREATE INDEX IF NOT EXISTS idx_turno_empresa
    ON turno (empresa_id) WHERE ativo;

ALTER TABLE departamento
    ADD COLUMN IF NOT EXISTS turno_id BIGINT,
    ADD COLUMN IF NOT EXISTS posicao_fila_transferencia INT,
    ADD COLUMN IF NOT EXISTS encerra_atendimento BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS tolerancia_atend_inativo_min INT,
    ADD COLUMN IF NOT EXISTS enviar_fila_atendimento BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS menu_coleta_id BIGINT,
    ADD COLUMN IF NOT EXISTS retencao_msg_dias INT;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
         WHERE constraint_name = 'fk_departamento_turno'
    ) THEN
        ALTER TABLE departamento
            ADD CONSTRAINT fk_departamento_turno
            FOREIGN KEY (turno_id)
            REFERENCES turno(id) ON DELETE SET NULL;
    END IF;
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
         WHERE constraint_name = 'fk_departamento_menu_coleta'
    ) THEN
        ALTER TABLE departamento
            ADD CONSTRAINT fk_departamento_menu_coleta
            FOREIGN KEY (menu_coleta_id)
            REFERENCES menu_chatbot(id) ON DELETE SET NULL;
    END IF;
END $$;
