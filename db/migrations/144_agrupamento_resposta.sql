-- Agrupamento adaptativo de mensagens — o agente para de responder a cada
-- fragmento que o cliente manda.
--
-- Problema medido na empresa 1018 (27-29/07): 156 de 415 respostas da IA
-- sairam a menos de 30s da resposta anterior pro mesmo numero. O cliente
-- digita "oi" / "bom dia" / "queria saber de X" e leva tres respostas.
--
-- Causa: `enqueue_or_buffer` so agrupa numa row `queued` com
-- `process_after > NOW()`. Com MESSAGE_BUFFER_SECONDS=2.0 o worker reivindica
-- a row quase imediato; a mensagem seguinte chega com a primeira ja em
-- `processing` e vira row nova = turno novo = resposta nova. A janela de 2s
-- e curta demais pra cobrir a latencia do agente (1,9s de LLM + outbound).
--
-- Modelo:
--   conexao.resposta_agrupamento_segundos — janela aplicada as mensagens de
--     FOLLOW-UP (quando o agente acabou de responder ou ainda esta
--     respondendo). A primeira mensagem de um turno segue na janela curta de
--     MESSAGE_BUFFER_SECONDS, entao ela continua respondida na hora.
--     0 desliga o agrupamento e restaura o comportamento anterior.
--   message_queue.origem_resposta — quem produziu a resposta daquela row.
--     Serve de sinal pra ISENTAR fluxo guiado: se a ultima resposta do thread
--     veio de menu/workflow/coleta/csat, a proxima mensagem do cliente e
--     resposta a um prompt (nao fragmento), e nao deve esperar a janela longa.
--
-- O teto da janela (quanto o lote pode adiar no maximo) fica em
-- MESSAGE_GROUPING_MAX_SECONDS, no shared/config.py: e trava de seguranca,
-- nao knob de produto.

ALTER TABLE conexao
    ADD COLUMN IF NOT EXISTS resposta_agrupamento_segundos INTEGER NOT NULL DEFAULT 8;

COMMENT ON COLUMN conexao.resposta_agrupamento_segundos IS
    'Segundos de espera antes de responder mensagens seguidas do mesmo '
    'contato, pra agrupar numa resposta so. 0 desliga.';

-- Faixa sa: acima de 60s a conversa passa a parecer travada, e o teto de
-- seguranca do config torna valores maiores inocuos de qualquer forma.
ALTER TABLE conexao
    DROP CONSTRAINT IF EXISTS chk_conexao_agrupamento_faixa;
ALTER TABLE conexao
    ADD CONSTRAINT chk_conexao_agrupamento_faixa
    CHECK (resposta_agrupamento_segundos BETWEEN 0 AND 60);

ALTER TABLE message_queue
    ADD COLUMN IF NOT EXISTS origem_resposta TEXT;

COMMENT ON COLUMN message_queue.origem_resposta IS
    'Quem produziu a resposta: agente|sistema|menu|workflow|coleta|csat|'
    'aprovacao|opt_out|encerrar. NULL = nenhuma resposta automatica saiu '
    '(whitelist, modo manual, fila de departamento, handoff humano, erro).';

-- Lookup do gate de isencao: ultima row respondida do thread. O indice cobre
-- o ORDER BY id DESC do enqueue sem varrer a fila inteira.
CREATE INDEX IF NOT EXISTS idx_message_queue_origem_thread
    ON message_queue (phone_number, agent_id, id DESC)
    WHERE origem_resposta IS NOT NULL;
