-- Colapsa os templates que eram o mesmo agente.
--
-- `atendimento_completo` e `agendamentos` chamavam `create_agent()` com
-- argumentos identicos ao `vsa_tech` — conferido linha a linha, e a docstring
-- do primeiro admitia "espelha vsa_tech". O que os distinguia era prompt e
-- lista de tools, e as duas coisas ja moram no banco:
--
--   mig 154 → materializou `tools_enabled`
--   mig 155 → materializou `prompt_override`
--
-- Sem elas, este UPDATE trocaria o comportamento de 16 agentes em silencio.
-- Com elas, o agente carrega o proprio texto e a propria lista, e o diretorio
-- Python vira so a topologia.
--
-- Sobram DOIS templates, e agora eles significam topologia de verdade:
--   `vsa_tech`          → agente simples (LangChain `create_agent`)
--   `atendimento_router`→ router + especialistas em paralelo + sintese
--
-- O nome `vsa_tech` continua por ser caro trocar: 60 arquivos e a coluna
-- `conexao.default_agent_id` o referenciam. Renomear pra `simples` e cosmetico
-- e fica pra depois — o que importava era acabar com o catalogo de quatro
-- caixas onde tres eram a mesma.

UPDATE agente_ia
   SET template_catalog = 'vsa_tech',
       updated_at = NOW()
 WHERE template_catalog IN ('atendimento_completo', 'agendamentos');

COMMENT ON COLUMN agente_ia.template_catalog IS
    'Topologia do grafo, nao "qual agente". Dois valores desde a mig 156: '
    '"vsa_tech" (simples, via create_agent) e "atendimento_router" (router + '
    'especialistas em paralelo). O que o agente FAZ vem de prompt_override, '
    'tools_enabled e base_conhecimento_ids — tudo no banco, editavel no painel.';
