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

-- O gatilho de UPDATE (migs 035/145) avisa as timelines abertas por NOTIFY,
-- mas só olhava `response` e `status`. Editar mexe em `response` e propagava
-- de graça; APAGAR mexe só na coluna nova e ficaria invisível para quem já
-- estivesse com a conversa aberta — justamente o caso que apagar precisa
-- resolver, porque o painel estaria exibindo como entregue algo que o cliente
-- não vê mais.
--
-- `kind` continua 'updated', então o loop de push (mig 168) segue ignorando:
-- ele filtra 'inbound'. Apagar não deve notificar celular de ninguém.
CREATE OR REPLACE FUNCTION notify_message_queue_updated() RETURNS TRIGGER AS $$
BEGIN
    IF NEW.atendimento_id IS NULL THEN
        RETURN NEW;
    END IF;
    IF (OLD.response IS DISTINCT FROM NEW.response)
       OR (OLD.status IS DISTINCT FROM NEW.status)
       OR (OLD.response_apagada_at IS DISTINCT FROM NEW.response_apagada_at) THEN
        PERFORM pg_notify(
            'atendimento_event',
            json_build_object(
                'event', 'mensagem',
                'empresa_id', NEW.empresa_id,
                'atendimento_id', NEW.atendimento_id,
                'message_id', NEW.id,
                'kind', 'updated',
                'status', NEW.status
            )::text
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
