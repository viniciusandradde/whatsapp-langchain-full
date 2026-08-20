-- Few-shot passa a poder ser usado pelo agente — por agente, e desligado.
--
-- `shared/fewshot.py` tem `find_similar_examples` e `format_fewshot_block`
-- desde sempre, e NENHUM chamador em `agents/` ou `worker/`. Em 2026-08-04
-- geramos 113 exemplos das avaliações reais dos clientes (fonte 'csat'), todos
-- com embedding — matéria-prima parada.
--
-- Por que por AGENTE e não por env: é caminho quente. Cada mensagem passa a
-- custar uma chamada de embedding a mais e alguns milhares de tokens de prompt.
-- São 19 agentes na base; ligar todos de uma vez seria mudança de
-- comportamento que ninguém pediu, num caminho que fala com cliente.
--
-- Default FALSE de propósito: quem quiser liga, mede, e decide. O log
-- `fewshot_injetado` no worker é o que permite essa medição.
--
-- Sem bloco de RLS: `agente_ia` já tem ENABLE + FORCE + isolamento por tenant
-- desde a Sprint A.2, e ALTER TABLE não movimenta linha.

ALTER TABLE agente_ia
    ADD COLUMN IF NOT EXISTS fewshot_enabled BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN agente_ia.fewshot_enabled IS
    'Quando true, o worker busca exemplos parecidos em fewshot_example e os '
    'antepõe à mensagem do cliente. Custa uma chamada de embedding e tokens '
    'extras por mensagem — por isso é opt-in por agente.';
