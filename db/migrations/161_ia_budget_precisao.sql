-- Teto de gasto de IA: `consumo_usd` volta a acumular.
--
-- `ia_budget.consumo_usd` era NUMERIC(10,2) — duas casas decimais. Mas o custo
-- de UMA chamada de LLM hoje é da ordem de 0.0014 USD, e o débito
-- (`shared/governanca_ia.py::acrescentar_consumo`) é um UPSERT que soma
-- `EXCLUDED.consumo_usd`. O EXCLUDED já chega convertido pro tipo da coluna,
-- então o incremento virava 0.00 ANTES da soma:
--
--     0.0014 convertido pra NUMERIC(10,2)  ->  0.00
--     consumo + 0.00 = consumo, pra sempre
--
-- Medido em produção: 116 chamadas em agosto/2026, custo real 0.1754 USD,
-- consumo debitado 0.00.
--
-- Antes, com modelos a ~0.005 por chamada, o efeito era o inverso e igualmente
-- errado: cada chamada arredondava PRA CIMA, a 0.01, e o valor gravado deixava
-- de ser um custo pra virar a contagem de chamadas dividida por 100. Foi o que
-- produziu os 12.79 USD de julho/2026 contra um custo real de ~8.1.
--
-- A escala escolhida é a MESMA de `ia_execucao.custo_total` (NUMERIC(12,8)),
-- de propósito: divergência de escala entre a origem e o acumulador é
-- exatamente o defeito que esta migração corrige. 14 dígitos deixam o total
-- mensal chegar a 999.999,99999999 USD sem estourar.

-- O runner de migração usa o pool da aplicação. Hoje ele conecta como
-- `postgres` (superusuário, que ignora RLS), mas o UPDATE abaixo toca linhas
-- com `empresa_id` — sob FORCE RLS e um papel comum ele seria silenciosamente
-- barrado em produção e passaria em dev, onde a conexão é superusuário.
-- `is_local = true`: vale só até o fim desta transação.
SELECT set_config('app.bypass_rls', 'true', true);

ALTER TABLE ia_budget
    ALTER COLUMN consumo_usd TYPE NUMERIC(14,8);

-- Recalcula o histórico a partir da fonte. `ia_execucao` reconstrói o consumo
-- porque `llm_callback` grava a execução e chama o débito no mesmo ponto, com
-- o mesmo valor, e só quando o custo é maior que zero — as duas escritas têm
-- origem única.
--
-- Meses cujo custo a migração 139 zerou (custo_total NULL) voltam a zero, pela
-- mesma razão que ela deu: o valor gravado é sabidamente errado e não é
-- reconstituível, porque o generation_id não era guardado na época.
--
-- `to_char(created_at, 'YYYY-MM')` casa com o `datetime.now().strftime` do
-- débito porque aplicação e banco rodam em UTC (conferido nos dois).
UPDATE ia_budget b
   SET consumo_usd = COALESCE((
           SELECT SUM(e.custo_total)
             FROM ia_execucao e
            WHERE e.empresa_id = b.empresa_id
              AND e.custo_total > 0
              AND to_char(e.created_at, 'YYYY-MM') = b.ano_mes
       ), 0),
       updated_at = NOW();

COMMENT ON COLUMN ia_budget.consumo_usd IS
    'Consumo acumulado do mês em USD. Escala idêntica a ia_execucao.custo_total '
    '(8 casas) porque o débito soma valor por valor: escala menor aqui zera o '
    'incremento de uma chamada antes da soma.';
