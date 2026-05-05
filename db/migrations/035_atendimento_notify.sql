-- E2.E SSE: triggers Postgres pra empurrar eventos via LISTEN/NOTIFY.
--
-- Canal único `atendimento_event` carrega payload JSON com atendimento_id
-- + tipo de evento. Listeners filtram client-side por atendimento_id.
-- Postgres NOTIFY é fire-and-forget e payload limitado a 8000 bytes
-- (config). Mantemos payload mínimo (só IDs + status), refresh detalhado
-- fica por conta do client buscar GET /api/atendimentos/{id}/mensagens.
--
-- Tabela das mensagens é `message_queue` (rows = inbound + outbound;
-- response = texto da resposta do agente, NULL até o worker enviar).

CREATE OR REPLACE FUNCTION notify_message_queue_inserted() RETURNS trigger AS $$
BEGIN
    IF NEW.atendimento_id IS NULL THEN
        RETURN NEW;
    END IF;
    PERFORM pg_notify(
        'atendimento_event',
        json_build_object(
            'event', 'mensagem',
            'atendimento_id', NEW.atendimento_id,
            'message_id', NEW.id,
            'kind', 'inbound'
        )::text
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


DROP TRIGGER IF EXISTS message_queue_insert_notify ON message_queue;
CREATE TRIGGER message_queue_insert_notify
    AFTER INSERT ON message_queue
    FOR EACH ROW EXECUTE FUNCTION notify_message_queue_inserted();


-- Update de message_queue: quando o worker grava `response` ou muda status
-- pra `done`/`failed`, notifica o painel pra refresh imediato.
CREATE OR REPLACE FUNCTION notify_message_queue_updated() RETURNS trigger AS $$
BEGIN
    IF NEW.atendimento_id IS NULL THEN
        RETURN NEW;
    END IF;
    IF (OLD.response IS DISTINCT FROM NEW.response)
       OR (OLD.status IS DISTINCT FROM NEW.status) THEN
        PERFORM pg_notify(
            'atendimento_event',
            json_build_object(
                'event', 'mensagem',
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


DROP TRIGGER IF EXISTS message_queue_update_notify ON message_queue;
CREATE TRIGGER message_queue_update_notify
    AFTER UPDATE ON message_queue
    FOR EACH ROW EXECUTE FUNCTION notify_message_queue_updated();


-- Atendimento: claim/close/transfer/departamento → notify
CREATE OR REPLACE FUNCTION notify_atendimento_changed() RETURNS trigger AS $$
BEGIN
    IF OLD.status IS DISTINCT FROM NEW.status
       OR OLD.assigned_to_user_id IS DISTINCT FROM NEW.assigned_to_user_id
       OR OLD.departamento_id IS DISTINCT FROM NEW.departamento_id THEN
        PERFORM pg_notify(
            'atendimento_event',
            json_build_object(
                'event', 'status_changed',
                'atendimento_id', NEW.id,
                'status', NEW.status,
                'assigned_to', NEW.assigned_to_user_id,
                'departamento_id', NEW.departamento_id
            )::text
        );
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


DROP TRIGGER IF EXISTS atendimento_changed_trigger ON atendimento;
CREATE TRIGGER atendimento_changed_trigger
    AFTER UPDATE ON atendimento
    FOR EACH ROW EXECUTE FUNCTION notify_atendimento_changed();
