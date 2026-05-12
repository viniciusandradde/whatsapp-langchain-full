-- Mig 080 — Wizard de coleta por menu_item
--
-- Adiciona array de perguntas estruturadas a cada item do menu chatbot.
-- Quando cliente escolhe o item, o worker dispara N perguntas em sequência
-- antes de executar a `acao_tipo` original (chamar_agente/transferir_dep/etc).
-- Cada pergunta tem label, save_as (slug), validate_with (cpf/data_br/etc),
-- retry_message e flag obrigatorio.

ALTER TABLE menu_item
    ADD COLUMN IF NOT EXISTS coleta_perguntas JSONB DEFAULT NULL;

COMMENT ON COLUMN menu_item.coleta_perguntas IS
    'Array opcional de perguntas pra coleta antes da acao_tipo. '
    'Schema: [{label, save_as, validate_with?, retry_message?, obrigatorio?}, ...]';

-- Índice GIN pra queries futuras tipo "menus com pergunta X" (raro mas útil)
CREATE INDEX IF NOT EXISTS idx_menu_item_coleta_perguntas
    ON menu_item USING gin (coleta_perguntas)
    WHERE coleta_perguntas IS NOT NULL;
