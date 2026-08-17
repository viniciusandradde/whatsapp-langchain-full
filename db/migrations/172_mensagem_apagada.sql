-- 172 — Marca de "mensagem apagada para todos" no WhatsApp.
--
-- O operador erra e precisa remover o que mandou. A Evolution expõe
-- `deleteMessageForEveryone` (verificado no binário v2.3.7 que roda em
-- produção); a WABA recusa com "Method not available on WhatsApp Business API",
-- então a ação só existe em conexão Evolution.
--
-- **Soft delete de propósito.** Poderia ser `SET response = NULL`, mas isso
-- destruiria o registro do que foi dito ao cliente — exatamente o que um
-- sistema de atendimento não pode perder. O texto fica no banco para
-- auditoria e a timeline passa a renderizar "Mensagem apagada" no lugar.
--
-- Só o lado OUTBOUND tem coluna: apagar mensagem do cliente não existe no
-- WhatsApp, e a assimetria é da plataforma, não nossa.
ALTER TABLE message_queue
  ADD COLUMN IF NOT EXISTS response_apagada_at TIMESTAMPTZ;

COMMENT ON COLUMN message_queue.response_apagada_at IS
  'Quando o operador apagou para todos a mensagem enviada (mig 172). O texto em `response` é preservado para auditoria; as timelines mostram "Mensagem apagada". NULL = não apagada.';
