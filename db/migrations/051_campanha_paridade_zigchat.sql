-- Sprint 5 — Paridade ZigChat (Campanha expand).
--
-- Documentação: docs/zigchat/depara/03_gap_grande.md
--
-- Adiciona ao campanha:
--   - modelo_mensagem_id: FK pra modelo_mensagem (template HSM aprovado WABA)
--   - scheduled_at: agendamento programado (envio futuro)
--   - tipo: broadcast/transactional/reativacao
--   - filtro_segmento: filtro de destinatário por segmento
--   - filtro_tags: filtro por tags

ALTER TABLE campanha
    ADD COLUMN IF NOT EXISTS modelo_mensagem_id BIGINT,
    ADD COLUMN IF NOT EXISTS scheduled_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS tipo TEXT NOT NULL DEFAULT 'broadcast'
        CHECK (tipo IN ('broadcast', 'transactional', 'reativacao')),
    ADD COLUMN IF NOT EXISTS filtro_segmento TEXT,
    ADD COLUMN IF NOT EXISTS filtro_tags TEXT[];

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
         WHERE constraint_name = 'fk_campanha_modelo_mensagem'
    ) THEN
        ALTER TABLE campanha
            ADD CONSTRAINT fk_campanha_modelo_mensagem
            FOREIGN KEY (modelo_mensagem_id)
            REFERENCES modelo_mensagem(id) ON DELETE SET NULL;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_campanha_scheduled
    ON campanha (scheduled_at) WHERE scheduled_at IS NOT NULL;
