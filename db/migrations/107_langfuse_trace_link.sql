-- Sprint Langfuse — link bidirecional ia_execucao/message_queue ↔ trace
--
-- Quando settings.langfuse_enabled, o worker gera trace_id determinístico
-- por mensagem (Langfuse.create_trace_id(seed=str(message.id))) e:
--   1) passa via trace_context pro CallbackHandler (controlamos o ID, não
--      é gerado dentro do callback).
--   2) grava o mesmo ID em ia_execucao + message_queue.
--
-- Pra que serve a coluna:
--   - debug: clicar numa msg no painel /atendimento e abrir trace exata
--     no Langfuse.
--   - NPS → score: avaliacao.save_avaliacao busca o último ia_execucao
--     do atendimento, pega trace_id e posta langfuse.create_score(trace).
--
-- Coluna é nullable porque (a) feature é opt-in e (b) backfill histórico
-- não tem trace. Index parcial mantém custo zero quando coluna não preenchida.

ALTER TABLE ia_execucao
    ADD COLUMN IF NOT EXISTS langfuse_trace_id TEXT;

COMMENT ON COLUMN ia_execucao.langfuse_trace_id IS
    'Sprint Langfuse — ID da trace Langfuse correspondente a esta execução. '
    'NULL quando Langfuse off no momento da execução. Usado pelo NPS pra '
    'anexar score posthoc à trace.';

CREATE INDEX IF NOT EXISTS ia_execucao_langfuse_trace_id_idx
    ON ia_execucao (langfuse_trace_id)
    WHERE langfuse_trace_id IS NOT NULL;


ALTER TABLE message_queue
    ADD COLUMN IF NOT EXISTS langfuse_trace_id TEXT;

COMMENT ON COLUMN message_queue.langfuse_trace_id IS
    'Sprint Langfuse — ID da trace Langfuse do turno do agente que respondeu '
    'esta mensagem. NULL quando Langfuse off no momento do processing. Permite '
    'deep-link do painel /atendimento → Langfuse UI por mensagem.';

CREATE INDEX IF NOT EXISTS message_queue_langfuse_trace_id_idx
    ON message_queue (langfuse_trace_id)
    WHERE langfuse_trace_id IS NOT NULL;
