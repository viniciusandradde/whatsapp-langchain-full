-- 141 — Preferência global de provider de observabilidade (Langfuse/LangSmith).
--
-- Motivo: hoje `_active_provider()` em `server/routes/traces.py` decide por
-- env — Langfuse se as duas chaves estiverem setadas, senão LangSmith. Isso
-- amarra a escolha ao deploy e cria uma armadilha: desligar os containers do
-- Langfuse NÃO muda `settings.langfuse_enabled` (as chaves seguem no .env),
-- então a página /traces continua apontando pro host morto e quebra.
--
-- Com a preferência persistida o admin troca pela UI, sem redeploy, e desligar
-- o stack do Langfuse vira operação segura.
--
-- Por que tabela nova e não `platform_integration_config`: aquela guarda
-- `config_encrypted` — existe pra segredo (chave de API). Provider ativo é
-- preferência em texto puro; passar por cripto só pra ler uma string seria
-- cerimônia sem ganho.
--
-- Por que global e não por empresa: a instância do Langfuse e o projeto do
-- LangSmith são infra compartilhada, com UMA chave cada. Não há o que
-- segmentar por tenant.

CREATE TABLE IF NOT EXISTS app_setting (
    chave       TEXT PRIMARY KEY,
    valor       TEXT NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by  TEXT
);

COMMENT ON TABLE app_setting IS
    'Preferencias globais da plataforma em texto puro (nao-secretas). '
    'Segredo vai em platform_integration_config, que e criptografado.';

COMMENT ON COLUMN app_setting.chave IS
    'Namespace por ponto, ex: observabilidade.provider';

-- Valor inicial: `auto` preserva exatamente o comportamento de hoje
-- (Langfuse > LangSmith > nenhum). Ninguém acorda com provider trocado por
-- causa desta migration; a mudança só acontece quando alguém escolher na UI.
INSERT INTO app_setting (chave, valor, updated_by)
VALUES ('observabilidade.provider', 'auto', 'migration-141')
ON CONFLICT (chave) DO NOTHING;
