-- Campanhas via template HSM (WABA real). O comentário original da mig 034 já
-- previa "template_id → waba_template". Broadcast fora da janela 24h no
-- WhatsApp oficial SÓ é permitido via template aprovado.
--
-- Campanha agora é: texto livre (mensagem, só dentro da janela 24h) OU
-- template aprovado (message_template_id + variáveis). Por isso `mensagem`
-- deixa de ser NOT NULL.

ALTER TABLE campanha
    ADD COLUMN IF NOT EXISTS message_template_id BIGINT
        REFERENCES waba_template(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS template_variaveis JSONB NOT NULL DEFAULT '{}'::jsonb;

-- Texto OU template — `mensagem` passa a ser opcional.
ALTER TABLE campanha ALTER COLUMN mensagem DROP NOT NULL;

CREATE INDEX IF NOT EXISTS idx_campanha_template
    ON campanha (message_template_id) WHERE message_template_id IS NOT NULL;
