-- 139 — Custo real da OpenRouter em vez de tabela de preços local.
--
-- Motivo: o painel mostrava 13,32 USD para o agente do Luis Fernando quando o
-- custo real era ~6,96 USD (+91%). `calc_custo()` recebia `tokens_cached` mas
-- nunca usava: cobrava os 48,6M de tokens de input a preço cheio quando 46,9M
-- (96,5%) eram cache hit, que o DeepSeek cobra pela metade.
--
-- A correção de fundo não é ajustar a tabela: é parar de estimar. A OpenRouter
-- devolve `usage.cost` em toda resposta — o valor efetivamente cobrado, já com
-- desconto de cache, BYOK e o preço do provedor upstream escolhido no
-- roteamento. Medido em chamada real: 0.2072 USD/Mtok de prompt no
-- deepseek-v3.2 contra 0.269 listados no catálogo. Nenhuma tabela local
-- acompanha isso.

-- Proveniência do custo. Sem isto, relatório mistura medido com estimado sem
-- avisar — foi assim que um erro de +91% sobreviveu até alguém questionar.
--   'openrouter' = veio de `usage.cost` (medido)
--   'tabela'     = estimado por modelo_llm (fallback)
--   NULL         = sem custo apurado
ALTER TABLE ia_execucao ADD COLUMN IF NOT EXISTS custo_fonte text;

-- ID da geração na OpenRouter (ex.: gen-1785096266-BaLnrBxk5b5qeMggbcoG).
-- Permite auditar qualquer linha depois via GET /api/v1/generation?id=.
-- Não tínhamos isso, e é por isso que o histórico anterior não pode ser
-- reconciliado com o custo verdadeiro.
ALTER TABLE ia_execucao ADD COLUMN IF NOT EXISTS openrouter_generation_id text;

CREATE INDEX IF NOT EXISTS idx_ia_execucao_custo_fonte
    ON ia_execucao (empresa_id, custo_fonte);

-- Preço de leitura de cache, para o FALLBACK. Sem esta coluna o fallback
-- cobra cache a preço de input (conservador: superestima em vez de zerar).
ALTER TABLE modelo_llm ADD COLUMN IF NOT EXISTS custo_cache_mtok numeric(10, 4);

COMMENT ON COLUMN modelo_llm.custo_cache_mtok IS
    'USD por milhao de tokens lidos de cache (input_cache_read na OpenRouter). '
    'Usado apenas no fallback quando usage.cost nao vem na resposta.';

-- deepseek-v3.2: input_cache_read = 0.1345 USD/Mtok (metade do prompt),
-- conferido em openrouter.ai/api/v1/models.
UPDATE modelo_llm
   SET custo_cache_mtok = 0.1345, updated_at = NOW()
 WHERE provedor = 'deepseek' AND nome = 'deepseek-v3.2'
   AND custo_cache_mtok IS NULL;

-- Zera o custo histórico. Os valores gravados são sabidamente errados (até
-- +91%) e NÃO podem ser reconciliados com o real: o generation_id não era
-- guardado, então a fonte de verdade daquelas chamadas se perdeu.
-- Recalcular pela fórmula apenas trocaria um número errado por outro menos
-- errado, com aparência de precisão. Os tokens ficam intactos — quem quiser
-- estimar o passado tem os dados. Relatórios de custo passam a valer do fix
-- em diante.
UPDATE ia_execucao
   SET custo_total = NULL,
       custo_fonte = NULL
 WHERE custo_total IS NOT NULL;

-- ia_budget NÃO é ajustado de propósito: o consumo acumulado seguiu sendo
-- debitado em dobro até aqui, mas corrigir o passado exigiria decidir por
-- empresa o que já foi cobrado. Decisão: corrigir só daqui pra frente.
