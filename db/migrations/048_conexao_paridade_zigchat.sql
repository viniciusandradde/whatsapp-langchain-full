-- Sprint 4 — Paridade ZigChat (Conexão expand).
--
-- Documentação: docs/zigchat/depara/03_gap_grande.md
--
-- Adiciona ao conexao:
--   - tipo_atendimento: manual/ia/hibrido (controla quem atende —
--     operador humano sempre, IA sempre, ou IA com fallback humano)
--   - whatsapp_state: estado da instância WhatsApp Web (CONNECTED/QR/etc)
--   - waba_account_id/phone_id/app_id/account_description: config WABA
--     dedicada (em vez de mexer com payload_json genérico)

ALTER TABLE conexao
    ADD COLUMN IF NOT EXISTS tipo_atendimento TEXT NOT NULL DEFAULT 'ia'
        CHECK (tipo_atendimento IN ('manual', 'ia', 'hibrido')),
    ADD COLUMN IF NOT EXISTS whatsapp_state TEXT,
    ADD COLUMN IF NOT EXISTS waba_account_id TEXT,
    ADD COLUMN IF NOT EXISTS waba_phone_id TEXT,
    ADD COLUMN IF NOT EXISTS waba_app_id TEXT,
    ADD COLUMN IF NOT EXISTS waba_account_description TEXT;
