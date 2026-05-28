-- Sprint Message Templates — generaliza waba_template pra multi-provider.
--
-- Antes: tabela waba_template servia SÓ conexões WABA (Meta Cloud API direto).
-- Twilio (BSP) usa Content API (content.twilio.com) com fluxo próprio:
--   POST /v1/Content → ContentSid (HX...)
--   POST /v1/Content/{sid}/ApprovalRequests/whatsapp → submete Meta review
--
-- Categorias (UTILITY/MARKETING/AUTHENTICATION) e workflow de status
-- (draft→pending→approved/rejected) são IDÊNTICOS entre WABA e Twilio, então
-- reusamos a mesma tabela com um discriminador `provider` + `content_sid`.
--
-- Mantemos o nome físico `waba_template` pra não quebrar FKs, índices e RBAC
-- existentes (perms waba_template.read/write). Conceitualmente vira
-- "message template" provider-agnostic.

ALTER TABLE waba_template
    ADD COLUMN IF NOT EXISTS provider TEXT NOT NULL DEFAULT 'waba',
    ADD COLUMN IF NOT EXISTS content_sid TEXT;

-- CHECK separado (ADD COLUMN + CHECK + IF NOT EXISTS dá problema em PG antigo)
ALTER TABLE waba_template DROP CONSTRAINT IF EXISTS waba_template_provider_check;
ALTER TABLE waba_template
    ADD CONSTRAINT waba_template_provider_check
    CHECK (provider IN ('waba', 'twilio_sandbox', 'twilio_prod'));

COMMENT ON COLUMN waba_template.provider IS
    'Sprint message templates — discrimina o BSP/canal do template. '
    '"waba" = Meta Cloud API direto (meta_template_id); "twilio_*" = Twilio '
    'Content API (content_sid). Rows pré-migração ficam "waba" (default).';

COMMENT ON COLUMN waba_template.content_sid IS
    'Sprint message templates — ContentSid do Twilio (HX...). NULL pra WABA '
    '(que usa meta_template_id). Usado por send_outbound_template (Gap 3) pra '
    'enviar o template aprovado.';

-- Index pra listagem filtrada por empresa+provider+status (UI de templates)
CREATE INDEX IF NOT EXISTS idx_msg_template_provider
    ON waba_template (empresa_id, provider, status);

-- Lookup do content_sid (envio + sync) — parcial pra rows Twilio
CREATE INDEX IF NOT EXISTS idx_msg_template_content_sid
    ON waba_template (content_sid)
    WHERE content_sid IS NOT NULL;
