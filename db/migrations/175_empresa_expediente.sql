-- 175 — expediente da empresa, para o agente parar de adivinhar se está aberto
--
-- Pedir ao modelo "compare o relógio com o expediente e decida" não funciona:
-- testado com três modelos, todos erraram — uns diziam "fora do horário" às 19h
-- (dentro), outro atendia normalmente às 01h (fora). Comparar horas é conta, e
-- conta é trabalho do código.
--
-- Com estas colunas o contexto de render entrega a CONCLUSÃO pronta em
-- `{{data.expediente}}` (ABERTO/FECHADO) e o prompt só escolhe o que dizer —
-- mesmo princípio das checagens do relatório de produção, onde o LLM redige mas
-- não decide.
--
-- Tudo nullable: empresa sem expediente cadastrado não ganha a variável, e o
-- prompt de quem não usa isso continua igual.

ALTER TABLE empresa
    ADD COLUMN IF NOT EXISTS expediente_inicio TIME,
    ADD COLUMN IF NOT EXISTS expediente_fim    TIME,
    -- ISO: 1 = segunda ... 7 = domingo. Default = dias úteis.
    ADD COLUMN IF NOT EXISTS expediente_dias   SMALLINT[] DEFAULT '{1,2,3,4,5}';

COMMENT ON COLUMN empresa.expediente_inicio IS
    'Início do atendimento humano, no fuso de empresa.timezone. NULL = não usa.';
COMMENT ON COLUMN empresa.expediente_fim IS
    'Fim do atendimento humano, no fuso de empresa.timezone. NULL = não usa.';
COMMENT ON COLUMN empresa.expediente_dias IS
    'Dias com atendimento (ISO: 1=segunda … 7=domingo).';
