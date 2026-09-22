-- 199: coluna legada `agente_ia.modelo` passa a espelhar o modelo efetivo
--
-- O seletor de modelos (ADR-004, mig 187) grava `modelo_provedor`/`modelo_nome`
-- e nunca tocou em `modelo`; o editor só a escrevia no fallback curado. A lista
-- de agentes (/agents) e o painel "em uso" da Saúde de IA liam a legada, então
-- mostravam um modelo parado em 22/08/2026 enquanto o worker usava outro
-- (VSA: card dizia gemini-2.5-flash-lite, runtime rodava o do seletor).
-- A partir daqui `update_agente` mantém as duas em dia; isto corrige o estoque.

SELECT set_config('app.bypass_rls', 'true', true);

UPDATE agente_ia
   SET modelo = modelo_provedor || '/' || modelo_nome
 WHERE COALESCE(modelo_provedor, '') <> ''
   AND COALESCE(modelo_nome, '') <> ''
   AND modelo IS DISTINCT FROM modelo_provedor || '/' || modelo_nome;
