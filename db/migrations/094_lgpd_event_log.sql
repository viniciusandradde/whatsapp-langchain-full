-- Sprint LGPD: log de auditoria pra agentes IA hospitalares.
--
-- Toda ação que toca dado sensível (CPF, data nasc, prontuário, agendamento
-- existente, identidade verificada, dado compartilhado com humano) registra
-- evento aqui via tool `log_lgpd_event` chamada pelo agente IA OU helper
-- `shared/lgpd.py::log_event` chamado pelo backend.
--
-- Necessário pra compliance LGPD (Art. 37 — relatório de impacto à proteção
-- de dados pessoais) e CFM (sigilo médico).

CREATE TABLE IF NOT EXISTS lgpd_event_log (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    atendimento_id BIGINT REFERENCES atendimento(id) ON DELETE SET NULL,
    cliente_id BIGINT REFERENCES cliente(id) ON DELETE SET NULL,
    agent_slug TEXT,
    user_id TEXT,  -- atendente humano se a ação partiu do painel
    event_type TEXT NOT NULL,
    details JSONB NOT NULL DEFAULT '{}'::jsonb,
    ip_address TEXT,  -- IP do request quando disponível
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT lgpd_event_type_check CHECK (
        event_type IN (
            'identity_verified',
            'identity_verification_failed',
            'cpf_collected',
            'dob_collected',
            'appointment_lookup',
            'data_shared_with_human',
            'modality_qualified',
            'document_request_created',
            'sensitive_data_exposed',
            'patient_record_accessed'
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_lgpd_event_empresa_created
    ON lgpd_event_log (empresa_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_lgpd_event_atendimento
    ON lgpd_event_log (atendimento_id) WHERE atendimento_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_lgpd_event_type
    ON lgpd_event_log (empresa_id, event_type, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_lgpd_event_cliente
    ON lgpd_event_log (cliente_id) WHERE cliente_id IS NOT NULL;

-- Perm RBAC (Admin + role Compliance)
INSERT INTO permissao (codigo, descricao, modulo) VALUES
    (
        'lgpd.audit.read',
        'Ver log de auditoria LGPD (acessos a dados sensíveis)',
        'lgpd'
    )
ON CONFLICT (codigo) DO NOTHING;

INSERT INTO perfil_permissao (perfil_id, permissao_codigo)
SELECT pa.id, 'lgpd.audit.read'
  FROM perfil_acesso pa
 WHERE pa.is_system AND pa.nome IN ('Admin', 'Gestor')
ON CONFLICT DO NOTHING;
