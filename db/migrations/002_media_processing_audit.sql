-- 002_media_processing_audit.sql
-- Auditoria de normalização de mídia antes do agente.

ALTER TABLE message_queue
    ADD COLUMN IF NOT EXISTS normalized_input TEXT,
    ADD COLUMN IF NOT EXISTS media_processing_status TEXT,
    ADD COLUMN IF NOT EXISTS media_processing_error TEXT;
