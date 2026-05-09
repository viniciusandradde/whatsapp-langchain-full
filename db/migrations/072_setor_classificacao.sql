-- Sprint R.1+R.2 — schema pra sandbox 999 + classificação setorial.

-- 1. Empresa sandbox (idempotente)
INSERT INTO empresa (id, nome, slug, status)
VALUES (999, 'Sandbox Análise Rádio', 'sandbox-radio', 'active')
ON CONFLICT (id) DO UPDATE SET nome = EXCLUDED.nome;

-- 2. Conexão dummy (necessária por FK)
INSERT INTO conexao (id, empresa_id, provider, from_number, status, default_agent_id, display_name)
VALUES (999, 999, 'twilio_sandbox', '+1000000000', 'active', 'atendimento', 'Sandbox')
ON CONFLICT (id) DO UPDATE SET status = 'active';

-- 3. Coluna setor_classificado em rag_query_log
ALTER TABLE rag_query_log
    ADD COLUMN IF NOT EXISTS setor_classificado TEXT,
    ADD COLUMN IF NOT EXISTS classificacao_confianca NUMERIC(3,2);

-- 4. Coluna setor_classificado em fewshot_example
ALTER TABLE fewshot_example
    ADD COLUMN IF NOT EXISTS setor_classificado TEXT,
    ADD COLUMN IF NOT EXISTS classificacao_confianca NUMERIC(3,2);

-- 5. Indexes pra dashboard agregar por setor
CREATE INDEX IF NOT EXISTS idx_rag_setor
    ON rag_query_log (empresa_id, setor_classificado, created_at DESC)
    WHERE setor_classificado IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_fewshot_setor
    ON fewshot_example (empresa_id, setor_classificado)
    WHERE setor_classificado IS NOT NULL;
