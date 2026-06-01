-- Módulo Histórico de Atendimentos — índices pra consulta sobre TODOS os status
-- (resolvido/abandonado inclusos) com período + ordenação.
--
-- O painel ao vivo (atendimento.list_atendimentos) usa índices parciais de
-- abertos (idx_atendimento_aberto_unique / idx_atendimento_empresa_status). O
-- histórico varre o conjunto completo por (empresa, created_at|closed_at), então
-- precisa de índices próprios pra paginar/ordenar volumes grandes (~9.8k/3m por
-- empresa no dump real ZigChat).

CREATE INDEX IF NOT EXISTS idx_atendimento_emp_created
    ON atendimento (empresa_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_atendimento_emp_closed
    ON atendimento (empresa_id, closed_at DESC);

CREATE INDEX IF NOT EXISTS idx_atendimento_emp_status_created
    ON atendimento (empresa_id, status, created_at DESC);
