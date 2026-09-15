-- Fase D: tempo de retenção de dados por empresa e por agente.
--
-- Passado o prazo, o loop de retenção (Fase E) apaga as mensagens de
-- atendimentos encerrados e a mídia delas, mantendo o registro do atendimento.
-- Efetivo = max(empresa, agente): o agente só ESTENDE (nunca reduz abaixo do
-- piso da empresa). NULL = ilimitado (empresa) / herda (agente) — nasce NULL
-- de propósito pra retenção nenhuma começar a apagar sem o dono escolher.

ALTER TABLE empresa
    ADD COLUMN IF NOT EXISTS retencao_dias INT;
COMMENT ON COLUMN empresa.retencao_dias IS
    'Dias de retenção das conversas (NULL = ilimitado). Piso da empresa.';

ALTER TABLE agente_ia
    ADD COLUMN IF NOT EXISTS retencao_dias INT;
COMMENT ON COLUMN agente_ia.retencao_dias IS
    'Dias de retenção do agente (NULL = herda a empresa). Só ESTENDE: efetivo '
    '= max(empresa, agente).';
