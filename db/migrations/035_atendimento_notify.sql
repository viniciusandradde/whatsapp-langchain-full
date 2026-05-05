-- E2.E SSE: triggers Postgres pra empurrar eventos via LISTEN/NOTIFY.
--
-- Canal único `atendimento_event` carrega payload JSON com atendimento_id
-- + tipo de evento. Listeners filtram client-side por atendimento_id
-- (ou via WHERE no caller). Postgres NOTIFY é fire-and-forget e não tem
-- backpressure — payload limitado a 8000 bytes (config). Mantemos
-- payload mínimo (só IDs + status), refresh detalhado fica por conta do
-- client buscar GET /api/atendimentos/{id}/mensagens.

CREATE OR REPLACE FUNCTION notify_mensagem_inserted() RETURNS trigger AS $$
BEGIN
    IF NEW.atendimento_id IS NULL THEN
        RETURN NEW;
    END IF;
    PERFORM pg_notify(
        'atendimento_event',
        json_build_object(
            'event', 'mensagem',
            'atendimento_id', NEW.atendimento_id,
            'mensagem_id', NEW.id,
            'direction', NEW.direction
        )::text
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;


DROP TRIGGER IF EXISTS mensagem_notify_trigger ON mensagem;
CREATE TRIGGER mensagem_notify_trigger
    AFTER INSERT ON mensagem
    FOR EACH ROW EXECUTE FUNCTION notify_mensagem_inserted();


CREATE OR REPLACE FUNCTION notify_atendimento_changed() RETURNS trigger AS $$
BEGIN
    -- Só dispara se algo relevante mudou — evita ruído nos updates
    -- de last_message_at (que disparam a cada mensagem).
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
