-- Sprint Atendimento UX (1.1) — Abas customizáveis no painel de atendimento.
--
-- A tabela `aba` JÁ EXISTE (mig 050 — modelo "filtro salvo" estilo Trello).
-- Esta sprint reusa a tabela mas adiciona o conceito de PINNING: atendimento
-- pode estar atribuído a uma aba via `atendimento.aba_id`. ZigChat usa esse
-- padrão (`Atendimento.aba_id`). O `filtro JSONB` da mig 050 fica disponível
-- pra evolução futura (filtro dinâmico salvo na aba), mas no MVP a UI só usa
-- abas pessoais com atendimentos pinneados manualmente.
--
-- Convenção: aba.user_id NOT NULL = aba pessoal (caso comum MVP).
--            aba.user_id NULL     = aba compartilhada (mig 050, sem UI MVP).

-- Pinning: atendimento atribuído a uma aba.
-- ON DELETE SET NULL: deletar aba não derruba atendimento (só perde o pin).
ALTER TABLE atendimento
    ADD COLUMN IF NOT EXISTS aba_id BIGINT REFERENCES aba(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_atendimento_aba
    ON atendimento (aba_id) WHERE aba_id IS NOT NULL;

-- Índice ZigChat-style pra lookup "minhas abas pessoais ordenadas".
CREATE INDEX IF NOT EXISTS idx_aba_user_personal
    ON aba (user_id, ordem) WHERE ativo AND user_id IS NOT NULL;
