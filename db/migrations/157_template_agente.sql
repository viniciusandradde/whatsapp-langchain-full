-- Renomeia a topologia `vsa_tech` para `agente`.
--
-- Etapa 2 de 4. A etapa 1 (codigo) criou `catalog/agente/` e deixou
-- `catalog/vsa_tech/` como shim que so re-exporta, entao NESTE momento os dois
-- nomes resolvem em `list_agents()`. E o que torna esta migration segura de
-- rodar com trafego: `webhook.py` valida o template a cada requisicao, e
-- durante a troca nenhum dos dois valores e invalido.
--
-- O que NAO muda, e por que:
--
--   `conexao.default_agent_id`   guarda SLUG de agente, nao nome de template
--   `atendimento.agente_atual`   idem — e `processor.py:917` compara o literal
--                                'vsa_tech' como sentinela de dado legado
--   `message_queue.agent_id`     idem
--   `thread_id` (checkpoints)    derivado do agent_id; mexer orfana historico
--
-- Trocar esses por 'agente' substituiria um valor errado por outro: a coluna
-- `default_agent_id` ja tem 'assistente-luis-fernando' numa linha, que e um
-- slug. Limpar isso e divida separada.

DO $$
DECLARE
    antes INT;
    depois INT;
    sobrou INT;
BEGIN
    SELECT count(*) INTO antes FROM agente_ia WHERE template_catalog = 'vsa_tech';

    UPDATE agente_ia
       SET template_catalog = 'agente',
           updated_at = NOW()
     WHERE template_catalog = 'vsa_tech';
    GET DIAGNOSTICS depois = ROW_COUNT;

    IF depois <> antes THEN
        RAISE EXCEPTION
            'Migration 157: esperava atualizar % agente(s), atualizou %. '
            'Alguem mexeu na tabela durante a migration.', antes, depois;
    END IF;

    -- Nenhum agente pode ficar apontando pra topologia que nao existe mais.
    -- Se sobrar, o webhook devolve AgentNotFoundError em toda mensagem daquela
    -- empresa — melhor nao subir do que subir mudo.
    SELECT count(*) INTO sobrou
      FROM agente_ia
     WHERE template_catalog NOT IN ('agente', 'atendimento_router');

    IF sobrou > 0 THEN
        RAISE EXCEPTION
            'Migration 157: % agente(s) com template desconhecido. '
            'Rode: SELECT DISTINCT template_catalog FROM agente_ia;', sobrou;
    END IF;

    RAISE NOTICE 'Migration 157: % agente(s) migrados para "agente".', depois;
END $$;

ALTER TABLE agente_ia ALTER COLUMN template_catalog SET DEFAULT 'agente';

COMMENT ON COLUMN agente_ia.template_catalog IS
    'Topologia do grafo, nao "qual agente". Dois valores: "agente" (simples, '
    'via create_agent) e "atendimento_router" (especialistas em paralelo). O '
    'que o agente FAZ vem de prompt_override, tools_enabled e '
    'base_conhecimento_ids — tudo no banco, editavel no painel. Renomeado de '
    '"vsa_tech" na mig 157.';
