-- Materializa `agente_ia.tools_enabled` nos agentes cujo template o ignorava.
--
-- Até aqui, `atendimento_completo` e `agendamentos` montavam a lista de
-- ferramentas CRAVADA em Python e descartavam `tools_enabled` — a assinatura
-- recebia o campo e o marcava `# noqa: ARG001`. O admin marcava caixa no painel
-- e nada acontecia. Medido no espelho de producao: 7 dos 9 agentes da empresa 1
-- exibiam "N tools" que nao valiam.
--
-- O codigo desta mesma branch passa os dois templates a usar `resolve_tools`,
-- que le o campo. Sem esta migration, o efeito seria o oposto do desejado: um
-- agente com 3 slugs marcados perderia de uma vez as ~20 ferramentas que vinha
-- recebendo em silencio — inclusive transferir para humano. Agente que nao
-- transfere e incidente, nao ajuste de configuracao.
--
-- Entao aqui o campo passa a dizer a VERDADE sobre o que o agente ja tem, e a
-- partir de agora desmarcar passa a funcionar.
--
-- Por que a lista completa e nao o que estava marcado: o valor gravado nunca
-- foi lido, entao nao e configuracao — e marca aspiracional. Preserva-lo
-- significaria aplicar, de surpresa, uma restricao que ninguem testou.

-- `atendimento_completo` dava o conjunto inteiro do registry (CRM, contexto,
-- memoria estruturada, escalacao, agenda, conhecimento e as 4 multimodais).
UPDATE agente_ia
   SET tools_enabled = ARRAY[
        'solicitar_humano', 'transferir_dep', 'encerrar_atendimento',
        'tag_cliente', 'tag_atendimento', 'consultar_contexto',
        'salvar_contexto', 'cliente.read', 'cliente.write',
        'cliente_anotacao.create', 'search_knowledge_base',
        'calendar.create', 'calendar.list',
        'midia.imagem', 'midia.audio', 'midia.documento'
       ],
       updated_at = NOW()
 WHERE template_catalog = 'atendimento_completo';

-- `agendamentos` era mais estreito: agenda + quem e o cliente + escalacao.
-- Sem multimodal e sem escrita de cliente.
UPDATE agente_ia
   SET tools_enabled = ARRAY[
        'calendar.create', 'calendar.list',
        'cliente.read', 'consultar_contexto',
        'solicitar_humano', 'tag_atendimento'
       ],
       updated_at = NOW()
 WHERE template_catalog = 'agendamentos';

-- `vsa_tech` ja lia o campo desde 2026-07-27 — nao se toca.
-- `atendimento_router` tem topologia propria e os especialistas trazem as
-- tools deles; o campo continua sem efeito la, por desenho.

COMMENT ON COLUMN agente_ia.tools_enabled IS
    'Slugs de ferramenta marcados no painel, traduzidos por '
    '`agents/tools/registry.py::resolve_tools`. Lista vazia = conjunto '
    'completo. Vale para os templates de topologia simples; o '
    '`atendimento_router` monta as tools pelos especialistas. Materializado '
    'na mig 154, quando dois templates deixaram de ignorar o campo.';
