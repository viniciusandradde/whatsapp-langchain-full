-- Adiciona `empresa_id` ao payload do canal `atendimento_event` (mig 035).
--
-- Motivo: o SSE de hoje e por atendimento (`/api/atendimentos/{id}/events`) e
-- filtra pelo `atendimento_id` do payload. O app Android precisa de um stream
-- da EMPRESA (mensagem nova em qualquer conversa) pra manter a lista viva —
-- abrir uma conexao SSE por conversa nao escala, e cada SSE ja consome uma
-- conexao psycopg dedicada FORA do pool.
--
-- Sem `empresa_id` no payload nao ha como filtrar por tenant: o endpoint global
-- entregaria evento de todas as empresas a qualquer cliente conectado. Como o
-- canal LISTEN e global no Postgres, isso seria vazamento cross-tenant — o
-- oposto do que a Sprint A.2 (RLS) garantiu no resto do sistema.
--
-- Alternativa descartada: resolver atendimento_id -> empresa_id com um SELECT
-- por evento. Custa uma query por notificacao em todos os devices conectados,
-- justo no caminho que deveria ser barato.
--
-- As tres funcoes sao recriadas com `NEW.empresa_id` acrescentado. Campos
-- existentes ficam intactos, entao o consumidor atual (drawer web) nao muda.
-- `message_queue` e `atendimento` tem `empresa_id` NOT NULL, sem risco de null.

-- 1. INSERT em message_queue (mensagem nova chegando)
CREATE OR REPLACE FUNCTION notify_message_queue_inserted() RETURNS trigger AS $$
BEGIN
    IF NEW.atendimento_id IS NULL THEN
        RETURN NEW;
    END IF;
    PERFORM pg_notify(
        'atendimento_event',
        json_build_object(
            'event', 'mensagem',
            'empresa_id', NEW.empresa_id,
            'atendimento_id', NEW.atendimento_id,
            'message_id', NEW.id,
            'kind', 'inbound'
        )::text
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 2. UPDATE em message_queue (worker gravou a resposta / mudou status)
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

-- 3. UPDATE em atendimento (claim / close / transfer / departamento)
CREATE OR REPLACE FUNCTION notify_atendimento_changed() RETURNS trigger AS $$
BEGIN
    IF OLD.status IS DISTINCT FROM NEW.status
       OR OLD.assigned_to_user_id IS DISTINCT FROM NEW.assigned_to_user_id
       OR OLD.departamento_id IS DISTINCT FROM NEW.departamento_id THEN
        PERFORM pg_notify(
            'atendimento_event',
            json_build_object(
                'event', 'status_changed',
                'empresa_id', NEW.empresa_id,
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

-- Triggers nao mudam (CREATE OR REPLACE FUNCTION basta), mas reafirmamos por
-- idempotencia caso a mig 035 nunca tenha rodado neste banco.
DROP TRIGGER IF EXISTS message_queue_insert_notify ON message_queue;
CREATE TRIGGER message_queue_insert_notify
    AFTER INSERT ON message_queue
    FOR EACH ROW EXECUTE FUNCTION notify_message_queue_inserted();

DROP TRIGGER IF EXISTS message_queue_update_notify ON message_queue;
CREATE TRIGGER message_queue_update_notify
    AFTER UPDATE ON message_queue
    FOR EACH ROW EXECUTE FUNCTION notify_message_queue_updated();

DROP TRIGGER IF EXISTS atendimento_changed_trigger ON atendimento;
CREATE TRIGGER atendimento_changed_trigger
    AFTER UPDATE ON atendimento
    FOR EACH ROW EXECUTE FUNCTION notify_atendimento_changed();
