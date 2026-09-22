-- 200: WhatsApp Coexistence — modo da conexão WABA + livro de idempotência por wamid
--
-- Coexistence é um MODO do provider `waba`, não um provider novo: o cliente
-- continua usando o WhatsApp Business no celular e o ChatNexus recebe/responde
-- pela Cloud API. O que muda por modo: o onboarding (Coexistence NÃO chama
-- `/register` e precisa sincronizar `smb_app_data` em até 24 h) e os campos de
-- webhook tratados (`smb_message_echoes`, `history`, `smb_app_state_sync`).
-- Conexões existentes ficam `cloud_api`; Evolution nunca é coexistence.
--
-- `waba_wamid_processado`: a Meta reentrega o lote inteiro quando respondemos
-- 5xx, e até aqui a "idempotência por message_id" prometida nos comentários do
-- webhook não existia (INSERT puro em `message_queue`). Índice único em
-- `message_queue.message_id` é inviável — multi-mídia grava N rows com o mesmo
-- id e o debounce mescla rows. O livro guarda só o wamid já processado; não é
-- dado de tenant (sem `empresa_id`, sem RLS).

ALTER TABLE conexao
    ADD COLUMN IF NOT EXISTS waba_mode TEXT NOT NULL DEFAULT 'cloud_api';

ALTER TABLE conexao DROP CONSTRAINT IF EXISTS conexao_waba_mode_check;
ALTER TABLE conexao
    ADD CONSTRAINT conexao_waba_mode_check
    CHECK (waba_mode IN ('cloud_api', 'coexistence'));

ALTER TABLE conexao DROP CONSTRAINT IF EXISTS conexao_waba_mode_provider_check;
ALTER TABLE conexao
    ADD CONSTRAINT conexao_waba_mode_provider_check
    CHECK (provider = 'waba' OR waba_mode = 'cloud_api');

COMMENT ON COLUMN conexao.waba_mode IS 'Modo da conexão WABA: cloud_api (número dedicado à API) ou coexistence (WhatsApp Business no celular + Cloud API). Evolution fica sempre cloud_api (CHECK).';

CREATE TABLE IF NOT EXISTS waba_wamid_processado (
    wamid       TEXT PRIMARY KEY,
    recebido_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_waba_wamid_processado_recebido_em
    ON waba_wamid_processado (recebido_em);

COMMENT ON TABLE waba_wamid_processado IS 'Livro de idempotência do webhook WABA: wamid já processado (mensagem, eco ou histórico). A reentrega da Meta pula o que está aqui.';
