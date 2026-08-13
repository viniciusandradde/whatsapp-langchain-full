-- A IA pode continuar respondendo enquanto o atendimento espera na fila.
--
-- Hoje, transferir para um departamento cala o agente naquela conversa até
-- alguém puxar o atendimento. O desenho pressupõe que a fila é trabalhada por
-- gente — quando não é, o cliente fala sozinho.
--
-- Medido na empresa 1018 em 12/08/2026, 7 dias: 100 de 177 atendimentos foram
-- transferidos, **465 mensagens** ficaram sem resposta nenhuma, e o
-- departamento de destino registrou 0 atendimentos assumidos, 0 mensagens de
-- operador e 0 resolvidos — contra 61 abandonados. Um cliente só (id 3006)
-- mandou 45 mensagens em 6 atendimentos e recebeu 4 respostas.
--
-- O ciclo que o dono descreveu como "às vezes responde, às vezes não" é esse:
-- a limpeza automática fecha o atendimento parado depois de 48h, a mensagem
-- seguinte abre um novo, o agente responde UMA vez, transfere, e cala de novo.
--
-- Por que no DEPARTAMENTO e não no agente ou na empresa: se a fila é
-- trabalhada por gente é propriedade da fila. A mesma empresa pode ter um
-- "Financeiro" com plantão e um "Diretoria" que é só caixa de entrada do dono.
-- Contratou alguém para a fila? Desliga o interruptor, e o silêncio volta.
--
-- DEFAULT FALSE preserva o comportamento de todo mundo que já usa: quem tem
-- fila trabalhada não quer a IA falando por cima do atendente que vai puxar.
--
-- Sem bloco de RLS: `departamento` já tem ENABLE + FORCE e isolamento por
-- tenant desde a Sprint A.2, e ALTER TABLE não movimenta linha.

ALTER TABLE departamento
    ADD COLUMN IF NOT EXISTS ia_continua_na_fila BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN departamento.ia_continua_na_fila IS
    'Quando TRUE, o agente segue respondendo o cliente enquanto o atendimento '
    'aguarda um atendente puxar. O handoff continua valendo: assim que alguém '
    'assume (status em_andamento + dono), a IA cala.';
