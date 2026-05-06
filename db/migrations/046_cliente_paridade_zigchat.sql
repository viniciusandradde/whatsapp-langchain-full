-- Sprint 3 — Paridade ZigChat (Cliente CRM enrichment).
--
-- Documentação: docs/zigchat/depara/03_gap_grande.md
--
-- Adiciona ao cliente:
--   - whatsapp_state: estado WhatsApp Web (CONNECTED/QR/DISCONNECTED)
--   - numero_verificado: flag se WhatsApp validou o número
--   - whatsapp_lid: Linked Identity (LID) do WhatsApp — id alternativo
--     novo (multi-device) que não é o telefone direto
--   - remote_id: ID do cliente em CRM externo (Salesforce/RD/HubSpot/etc)
--   - msg_apos_encerramento: mensagem automática enviada quando atendimento
--     fecha (ex: "Foi um prazer te atender! Volte sempre.")
--   - field_1..5: 5 campos custom por cliente (cada empresa decide o que
--     armazenar — ex: cnpj_emissor, cor_preferida, plano_contratado)
--   - ignora_inatividade: cliente VIP que ignora timeout de inatividade
--   - desconsidera_turno: cliente VIP que ignora horário de funcionamento

ALTER TABLE cliente
    ADD COLUMN IF NOT EXISTS whatsapp_state TEXT,
    ADD COLUMN IF NOT EXISTS numero_verificado BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS whatsapp_lid TEXT,
    ADD COLUMN IF NOT EXISTS remote_id TEXT,
    ADD COLUMN IF NOT EXISTS msg_apos_encerramento TEXT,
    ADD COLUMN IF NOT EXISTS field_1 TEXT,
    ADD COLUMN IF NOT EXISTS field_2 TEXT,
    ADD COLUMN IF NOT EXISTS field_3 TEXT,
    ADD COLUMN IF NOT EXISTS field_4 TEXT,
    ADD COLUMN IF NOT EXISTS field_5 TEXT,
    ADD COLUMN IF NOT EXISTS ignora_inatividade BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS desconsidera_turno BOOLEAN NOT NULL DEFAULT FALSE;

-- Índices pra busca rápida em sync com CRM externo
CREATE INDEX IF NOT EXISTS idx_cliente_remote_id
    ON cliente (empresa_id, remote_id) WHERE remote_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_cliente_whatsapp_lid
    ON cliente (whatsapp_lid) WHERE whatsapp_lid IS NOT NULL;
