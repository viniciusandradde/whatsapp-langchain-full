-- Sprint 7 — Paridade ZigChat (Plano + Transacao — billing comercial).
--
-- Documentação: docs/zigchat/depara/04_pendentes_criar.md
--
-- Catálogo de planos comerciais (free/pro/enterprise) + histórico de
-- transações (assinaturas, addons, reembolsos). Substitui o `empresa.plano`
-- TEXT genérico atual.
--
-- Hoje empresa.plano é só TEXT 'free'. Mig 060 vai adicionar empresa.plano_id
-- FK pro plano cadastrado (ainda mantém o TEXT pra compat).

CREATE TABLE IF NOT EXISTS plano (
    id BIGSERIAL PRIMARY KEY,
    nome TEXT NOT NULL UNIQUE,             -- "Free", "Pro", "Enterprise"
    slug TEXT NOT NULL UNIQUE,             -- "free", "pro", "enterprise"
    descricao TEXT,
    preco_mensal_brl NUMERIC(10,2),
    preco_anual_brl NUMERIC(10,2),         -- desconto anual
    -- Limites operacionais
    limite_usuarios INT,
    limite_conexoes INT,
    limite_atendimentos_mes INT,
    limite_orcamento_ia_usd NUMERIC(10,2),
    limite_documentos_kb INT,
    -- Features liberadas (flags por plano)
    -- Ex: {"calendar": true, "mcp": false, "menu_moderno": true, ...}
    features JSONB NOT NULL DEFAULT '{}'::jsonb,
    ativo BOOLEAN NOT NULL DEFAULT TRUE,
    ordem INT,                             -- ordem no pricing page
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Seed inicial (3 planos padrão)
INSERT INTO plano
    (nome, slug, descricao, preco_mensal_brl, preco_anual_brl,
     limite_usuarios, limite_conexoes, limite_atendimentos_mes,
     limite_orcamento_ia_usd, limite_documentos_kb, features, ordem)
VALUES
    ('Free', 'free', 'Plano grátis pra testar a plataforma',
     0.00, 0.00, 2, 1, 100, 5.00, 5,
     '{"calendar": false, "mcp": false, "menu_moderno": false, "rbac": false}'::jsonb, 1),
    ('Pro', 'pro', 'PME com operação ativa — recursos completos',
     299.00, 2990.00, 10, 3, 5000, 100.00, 100,
     '{"calendar": true, "mcp": false, "menu_moderno": true, "rbac": true}'::jsonb, 2),
    ('Enterprise', 'enterprise', 'Operações grandes com integrações custom',
     1499.00, 14990.00, NULL, NULL, NULL, 500.00, NULL,
     '{"calendar": true, "mcp": true, "menu_moderno": true, "rbac": true, "white_label": true}'::jsonb, 3)
ON CONFLICT (nome) DO NOTHING;

CREATE TABLE IF NOT EXISTS transacao (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    plano_id BIGINT REFERENCES plano(id) ON DELETE SET NULL,
    tipo TEXT NOT NULL
        CHECK (tipo IN ('assinatura', 'addon', 'reembolso', 'credito', 'estorno')),
    valor_brl NUMERIC(10,2) NOT NULL,
    status TEXT NOT NULL DEFAULT 'pendente'
        CHECK (status IN ('pendente', 'pago', 'falhou', 'estornado', 'cancelado')),
    -- Gateway externo (Stripe charge ID, PagSeguro tx ID, etc)
    gateway TEXT,                          -- "stripe" / "pagseguro" / "manual"
    gateway_id TEXT,
    descricao TEXT,
    pago_em TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_transacao_empresa
    ON transacao (empresa_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_transacao_status_pendente
    ON transacao (status) WHERE status = 'pendente';
