-- Sprint Conexões — Templates HSM WhatsApp (Message Templates aprovados pela Meta).
--
-- WABA exige template aprovado pra enviar mensagem fora da janela 24h pós-última-msg
-- do cliente. Sem isso, operador só responde atendimentos ativos — não inicia conversa.
-- Cada conexão WABA tem seus próprios templates aprovados (não compartilha).
--
-- componentes_json segue shape Meta API:
--   [
--     {"type": "HEADER", "format": "TEXT", "text": "Olá {{1}}"},
--     {"type": "BODY", "text": "Seu pedido {{1}} foi confirmado", "example": {"body_text": [["12345"]]}},
--     {"type": "FOOTER", "text": "Equipe Suporte"},
--     {"type": "BUTTONS", "buttons": [{"type": "QUICK_REPLY", "text": "Ok"}]}
--   ]
--
-- meta_template_id é o ID retornado pelo POST /{waba_account_id}/message_templates.
-- Usado depois pra sync de status (GET /{id}) e delete.

CREATE TABLE IF NOT EXISTS waba_template (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    conexao_id BIGINT NOT NULL REFERENCES conexao(id) ON DELETE CASCADE,
    nome TEXT NOT NULL,
    categoria TEXT NOT NULL
        CHECK (categoria IN ('UTILITY', 'AUTHENTICATION', 'MARKETING')),
    idioma TEXT NOT NULL DEFAULT 'pt_BR',
    componentes_json JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'pending', 'approved', 'rejected', 'disabled', 'paused')),
    meta_template_id TEXT,
    meta_quality_score TEXT,
    motivo_rejeicao TEXT,
    ultimo_sync_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by_user_id TEXT,
    UNIQUE (conexao_id, nome, idioma)
);

CREATE INDEX IF NOT EXISTS idx_waba_template_empresa_status
    ON waba_template (empresa_id, status);

CREATE INDEX IF NOT EXISTS idx_waba_template_conexao
    ON waba_template (conexao_id, status);

-- Perms RBAC (Admin + Gestor têm acesso por default)
INSERT INTO permissao (codigo, descricao, modulo) VALUES
    ('waba_template.read', 'Ver templates de mensagem WhatsApp', 'conexao'),
    ('waba_template.write', 'Criar/editar/submeter templates WhatsApp', 'conexao')
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO perfil_permissao (perfil_id, permissao_codigo)
SELECT pa.id, c.codigo
  FROM perfil_acesso pa, (VALUES ('waba_template.read'), ('waba_template.write')) AS c(codigo)
 WHERE pa.is_system AND pa.nome IN ('Admin', 'Gestor')
ON CONFLICT DO NOTHING;
