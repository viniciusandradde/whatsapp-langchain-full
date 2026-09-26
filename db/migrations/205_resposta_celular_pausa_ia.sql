-- 205: resposta do dono pelo celular pausa a IA (ADR-008)
--
-- Na conexão Evolution, a mensagem que o dono digita no celular (ou no
-- WhatsApp Web) chega ao webhook com `key.fromMe = true` e era descartada: o
-- agente não via o que o dono já tinha respondido e entrava por cima da
-- conversa. Agora ela vira linha de saída (`origem_resposta = 'celular'`),
-- pausa a IA naquela conversa (dono sentinela `whatsapp_celular`, o mesmo
-- mecanismo da Coexistência da mig 200) e entra no contexto do agente.
--
-- `celular_retorno_ia_minutos`: NULL = a IA só volta por "Devolver à IA"
-- (padrão decidido pelo dono em 26/09/2026, igual ao agente da Meta). Um
-- valor faz a IA voltar sozinha depois desse tempo sem resposta do celular
-- (PR B da ADR-008).
--
-- Índice único parcial: a Evolution reentrega webhook; a mesma mensagem do
-- celular não pode virar duas bolhas. Parcial porque `message_id` não é
-- único na fila (multi-mídia e agrupamento de mensagens).

SELECT set_config('app.bypass_rls', 'true', true);

ALTER TABLE conexao
    ADD COLUMN IF NOT EXISTS celular_retorno_ia_minutos INTEGER;

ALTER TABLE conexao DROP CONSTRAINT IF EXISTS conexao_celular_retorno_ia_minutos_check;
ALTER TABLE conexao
    ADD CONSTRAINT conexao_celular_retorno_ia_minutos_check
    CHECK (
        celular_retorno_ia_minutos IS NULL
        OR celular_retorno_ia_minutos BETWEEN 5 AND 10080
    );

COMMENT ON COLUMN conexao.celular_retorno_ia_minutos IS
    'Minutos sem resposta pelo celular para a IA voltar sozinha; NULL = só por "Devolver à IA" (ADR-008).';

CREATE UNIQUE INDEX IF NOT EXISTS uq_message_queue_resposta_celular
    ON message_queue (conexao_id, message_id)
    WHERE origem_resposta = 'celular';
