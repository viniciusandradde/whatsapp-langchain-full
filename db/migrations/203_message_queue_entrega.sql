-- 203: estado de entrega das mensagens enviadas pela Cloud API (WABA)
--
-- A Meta avisa por webhook (`messages.statuses[]`) se cada mensagem enviada
-- foi entregue, lida ou FALHOU — e a falha pode vir depois de o envio ter
-- sido aceito (fora da janela de 24 h, número sem WhatsApp, limite de
-- marketing). Até 24/09/2026 esses avisos eram descartados: o painel mostrava
-- como enviada uma mensagem que nunca chegou.
--
-- `response_message_ids`: os wamids do que saiu por esta linha. É lista
-- porque uma resposta longa da IA sai em várias partes. O painel grava o id
-- ao salvar (`_persist_outbound_row`); o worker, por um invólucro do cliente
-- de envio (`shared/entrega.py::ClienteQueRegistraEnvio`).
-- `entrega_status` só avança (sent → delivered → read) e `failed` prevalece.

SELECT set_config('app.bypass_rls', 'true', true);

ALTER TABLE message_queue
    ADD COLUMN IF NOT EXISTS response_message_ids TEXT[],
    ADD COLUMN IF NOT EXISTS entrega_status TEXT,
    ADD COLUMN IF NOT EXISTS entrega_erro TEXT,
    ADD COLUMN IF NOT EXISTS entrega_em TIMESTAMPTZ;

ALTER TABLE message_queue DROP CONSTRAINT IF EXISTS message_queue_entrega_status_check;
ALTER TABLE message_queue
    ADD CONSTRAINT message_queue_entrega_status_check
    CHECK (entrega_status IS NULL OR entrega_status IN ('sent', 'delivered', 'read', 'failed'));

CREATE INDEX IF NOT EXISTS idx_message_queue_response_message_ids
    ON message_queue USING GIN (response_message_ids)
    WHERE response_message_ids IS NOT NULL;

-- Mensagens do painel já guardam o wamid em `message_id` (a linha é só de
-- saída): passam a ser encontradas pelo aviso de status.
UPDATE message_queue
   SET response_message_ids = ARRAY[message_id]
 WHERE response_message_ids IS NULL
   AND normalized_input LIKE 'manual:%'
   AND message_id LIKE 'wamid.%';

COMMENT ON COLUMN message_queue.response_message_ids IS 'wamids do que saiu por esta linha (Cloud API) — casa com o aviso de status da Meta (mig 203).';
COMMENT ON COLUMN message_queue.entrega_status IS 'Último estado de entrega avisado pela Meta: sent|delivered|read|failed (failed prevalece).';
COMMENT ON COLUMN message_queue.entrega_erro IS 'Motivo legível da falha de entrega, com o código da Meta.';
