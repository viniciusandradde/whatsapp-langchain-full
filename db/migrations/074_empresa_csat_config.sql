-- Sprint Y — Configuração da pesquisa NPS/CSAT direto no cadastro da empresa.
--
-- Antes (Sprint X): worker buscava item `pesquisa_csat` no menu_chatbot
-- ativo da empresa. Exigia ter menu cadastrado, e a config ficava perdida
-- entre dezenas de itens de menu.
--
-- Agora: 4 colunas em `empresa` controlam o fluxo CSAT global da empresa.
-- Config feita direto na aba NPS do edit empresa.

ALTER TABLE empresa
    ADD COLUMN IF NOT EXISTS csat_ativo BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS csat_pergunta TEXT,
    ADD COLUMN IF NOT EXISTS csat_msg_agradecimento TEXT,
    ADD COLUMN IF NOT EXISTS csat_solicita_comentario BOOLEAN NOT NULL DEFAULT TRUE;

-- Desativa qualquer item legado pesquisa_csat — agora a config vem de
-- empresa.csat_*. Mantemos a row pra histórico (não DELETE).
UPDATE menu_item SET ativo = FALSE WHERE acao_tipo = 'pesquisa_csat';
