-- M5.d Variáveis de ambiente: KV por empresa que pode ser referenciado
-- como `{{var.NOME}}` em prompts (system_prompt_override) e modelos
-- de mensagem. Render acontece no servidor antes do texto sair pra Twilio
-- ou virar prompt de agente.

CREATE TABLE IF NOT EXISTS variavel_ambiente (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    -- Nome só com letras, números e underscore — evita conflito com
    -- sintaxe de template e ambiguidade no parser.
    nome TEXT NOT NULL CHECK (nome ~ '^[a-zA-Z][a-zA-Z0-9_]*$'),
    valor TEXT NOT NULL,
    descricao TEXT,
    -- Liga/desliga sem perder o valor (usuário pode testar sem reescrever).
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    created_by_user_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Mesma empresa não pode ter duas vars com o mesmo nome — chave que
    -- aparece no template precisa resolver pra um único valor.
    UNIQUE (empresa_id, nome)
);

CREATE INDEX IF NOT EXISTS idx_variavel_ambiente_empresa
    ON variavel_ambiente (empresa_id) WHERE ativo;
