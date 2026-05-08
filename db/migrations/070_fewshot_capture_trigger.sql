-- Sprint P.3 — captura automática de exemplos few-shot a partir de
-- atendimentos com outcome=success.
--
-- Usa message_queue como fonte: cada row tem incoming_message (cliente)
-- e response (agente). Pegamos o último par com response não-nulo.

CREATE OR REPLACE FUNCTION trg_capture_fewshot_on_success()
RETURNS TRIGGER AS $$
DECLARE
    v_outcome TEXT;
    v_in TEXT;
    v_out TEXT;
BEGIN
    IF TG_OP = 'UPDATE' AND
       OLD.status IS DISTINCT FROM NEW.status AND
       NEW.status = 'resolvido' AND
       NEW.assigned_to_user_id IS NULL AND
       COALESCE(NEW.qtde_resposta_invalida, 0) < 2 AND
       NEW.agente_atual IS NOT NULL THEN

        v_outcome := compute_atendimento_outcome(NEW.id);
        IF v_outcome != 'success' THEN
            RETURN NEW;
        END IF;

        IF EXISTS (SELECT 1 FROM fewshot_example WHERE atendimento_id = NEW.id) THEN
            RETURN NEW;
        END IF;

        -- Último par (msg cliente, response agente) com ambos preenchidos
        SELECT incoming_message, response
          INTO v_in, v_out
          FROM message_queue
         WHERE phone_number = (SELECT cli.telefone FROM cliente cli WHERE cli.id = NEW.cliente_id)
           AND agent_id = NEW.agente_atual
           AND response IS NOT NULL
           AND char_length(coalesce(response, '')) > 5
           AND char_length(coalesce(incoming_message, '')) >= 5
           AND created_at >= NEW.created_at
         ORDER BY created_at DESC
         LIMIT 1;

        IF v_in IS NOT NULL AND v_out IS NOT NULL THEN
            INSERT INTO fewshot_example
                (empresa_id, agente_slug, cliente_msg, agente_resposta,
                 outcome, atendimento_id, status)
            VALUES
                (NEW.empresa_id, NEW.agente_atual,
                 LEFT(v_in, 1000), LEFT(v_out, 1500),
                 'success', NEW.id, 'pending');
        END IF;
    END IF;
    RETURN NEW;
EXCEPTION WHEN OTHERS THEN
    -- Best-effort: erro na captura não bloqueia atualização do atendimento
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS atendimento_capture_fewshot ON atendimento;
CREATE TRIGGER atendimento_capture_fewshot
    AFTER UPDATE ON atendimento
    FOR EACH ROW
    EXECUTE FUNCTION trg_capture_fewshot_on_success();
