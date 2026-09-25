-- 204: chave da OpenRouter por empresa (ADR-007)
--
-- Até aqui toda chamada de IA saía por UMA chave da plataforma
-- (OPENROUTER_API_KEY), com o custo separado por empresa em ia_execucao e
-- ia_budget. A partir daqui a empresa pode ter chave própria, de dois jeitos:
--
--   propria       a empresa traz a chave dela (Opção A): o gasto aparece na
--                 conta DELA na OpenRouter e ela paga direto.
--   provisionada  a plataforma cria uma chave só para ela pela API de gestão
--                 da OpenRouter (Opção B): limite de crédito por empresa,
--                 limite de uso isolado e raio menor se uma chave vazar.
--
-- A chave fica cifrada (Fernet, a mesma infra de api_connection) e nunca sai
-- pela API; openrouter_chave_prefixo é o que o painel mostra.
-- openrouter_chave_hash identifica a chave na API de gestão (só para a
-- provisionada): serve para consultar o uso, mudar o limite e apagar.
-- Empresa sem chave continua na chave da plataforma (padrão, Opção 0).

SELECT set_config('app.bypass_rls', 'true', true);

ALTER TABLE empresa
    ADD COLUMN IF NOT EXISTS openrouter_chave_cifrada TEXT,
    ADD COLUMN IF NOT EXISTS openrouter_chave_prefixo TEXT,
    ADD COLUMN IF NOT EXISTS openrouter_chave_origem TEXT,
    ADD COLUMN IF NOT EXISTS openrouter_chave_hash TEXT,
    ADD COLUMN IF NOT EXISTS openrouter_chave_limite_usd NUMERIC(12, 2),
    ADD COLUMN IF NOT EXISTS openrouter_chave_definida_em TIMESTAMPTZ;

ALTER TABLE empresa DROP CONSTRAINT IF EXISTS empresa_openrouter_chave_origem_check;
ALTER TABLE empresa
    ADD CONSTRAINT empresa_openrouter_chave_origem_check
    CHECK (
        openrouter_chave_origem IS NULL
        OR openrouter_chave_origem IN ('propria', 'provisionada')
    );

COMMENT ON COLUMN empresa.openrouter_chave_cifrada IS
    'Chave da OpenRouter desta empresa, cifrada (Fernet). NULL = usa a chave da plataforma (ADR-007).';
COMMENT ON COLUMN empresa.openrouter_chave_prefixo IS
    'Primeiros caracteres da chave, para o painel identificar qual está em uso sem expor a chave.';
COMMENT ON COLUMN empresa.openrouter_chave_origem IS
    'propria = a empresa trouxe a chave; provisionada = a plataforma criou pela API de gestão.';
COMMENT ON COLUMN empresa.openrouter_chave_hash IS
    'Identificador da chave na API de gestão da OpenRouter (só provisionada): uso, limite e remoção.';
COMMENT ON COLUMN empresa.openrouter_chave_limite_usd IS
    'Limite de crédito (US$) configurado na chave; NULL = sem limite ou desconhecido.';
