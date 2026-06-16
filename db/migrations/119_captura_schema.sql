-- Disparador (Task 3) — schema de captura de contatos/grupos do WhatsApp.
--
-- Os dados raspados (extensão Chrome) ou puxados (Evolution server-side) caem
-- em STAGING (`contato_capturado`), NÃO direto no CRM `cliente`: são sujos
-- (push-name, sem consentimento/LGPD). O usuário promove os escolhidos depois.
--
-- Decisões de modelagem (do veredito multi-agente cruzando docs/Baileys):
-- * `wa_jid` é a IDENTIDADE PRIMÁRIA, não o telefone. Membros multi-device
--   aparecem como `<lid>@lid` SEM telefone derivável; chavear por telefone os
--   perderia. Telefone é NULLABLE (só extraído de `@s.whatsapp.net`).
-- * `grupo_membro` carrega `empresa_id` DENORMALIZADO para a policy RLS ser
--   direta (`_rls_tenant_match`), evitando policy por subquery (mig 101 marca
--   tabelas FK-indiretas como gap conhecido de RLS).
-- * Contato é único por (empresa, wa_jid); a relação N:N com grupos vive em
--   `grupo_membro` (permite "contatos únicos" = DISTINCT wa_jid cross-grupo).

-- 1) Auditoria de cada captura (extensão OU evolution).
CREATE TABLE IF NOT EXISTS captura_lote (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    origem TEXT NOT NULL CHECK (origem IN ('extensao_chrome', 'evolution_server')),
    conexao_id BIGINT REFERENCES conexao(id) ON DELETE SET NULL,        -- só evolution
    api_key_id BIGINT REFERENCES empresa_api_key(id) ON DELETE SET NULL, -- só extensão
    tipo TEXT NOT NULL CHECK (tipo IN ('contatos', 'grupos', 'grupo_membros')),
    origem_jid TEXT,                           -- wa_group_id quando tipo=grupo_membros
    total_recebidos INT NOT NULL DEFAULT 0,
    total_novos INT NOT NULL DEFAULT 0,
    total_atualizados INT NOT NULL DEFAULT 0,
    total_pulados_invalido INT NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'processando'
        CHECK (status IN ('processando', 'concluido', 'parcial', 'erro')),
    erro TEXT,
    created_by_user_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    finished_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_captura_lote_empresa
    ON captura_lote (empresa_id, created_at DESC);

-- 2) Grupos/comunidades (criado antes de contato/membro p/ FKs).
CREATE TABLE IF NOT EXISTS grupo (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    conexao_id BIGINT REFERENCES conexao(id) ON DELETE SET NULL,
    wa_group_id TEXT NOT NULL,                 -- 120363...@g.us
    tipo TEXT NOT NULL DEFAULT 'grupo' CHECK (tipo IN ('grupo', 'comunidade')),
    nome TEXT,
    descricao TEXT,
    invite_link TEXT,
    participantes_count INT NOT NULL DEFAULT 0,
    somos_admin BOOLEAN NOT NULL DEFAULT FALSE,
    origem TEXT NOT NULL DEFAULT 'evolution_server',
    visto_ultima_vez_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (empresa_id, wa_group_id)
);
CREATE INDEX IF NOT EXISTS idx_grupo_empresa
    ON grupo (empresa_id, created_at DESC);

-- 3) Contatos capturados (staging único por empresa+wa_jid).
CREATE TABLE IF NOT EXISTS contato_capturado (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    captura_lote_id BIGINT REFERENCES captura_lote(id) ON DELETE SET NULL,
    wa_jid TEXT NOT NULL,                      -- 5511...@s.whatsapp.net OU <lid>@lid
    wa_lid TEXT,                               -- <lid>@lid quando conhecido
    telefone TEXT,                             -- E.164; NULL p/ membros só-LID
    push_name TEXT,
    verified_name TEXT,
    is_business BOOLEAN NOT NULL DEFAULT FALSE,
    origem TEXT NOT NULL DEFAULT 'extensao_chrome',
    cliente_id BIGINT REFERENCES cliente(id) ON DELETE SET NULL,  -- setado na promoção
    promovido_at TIMESTAMPTZ,
    wa_existe BOOLEAN,                          -- preenchido por check_numbers (Task 6)
    validado_at TIMESTAMPTZ,
    visto_ultima_vez_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (empresa_id, wa_jid)
);
CREATE INDEX IF NOT EXISTS idx_contato_capt_empresa
    ON contato_capturado (empresa_id, created_at DESC);

-- 4) Membros de grupo (N:N grupo↔contato; empresa_id denormalizado p/ RLS).
CREATE TABLE IF NOT EXISTS grupo_membro (
    id BIGSERIAL PRIMARY KEY,
    grupo_id BIGINT NOT NULL REFERENCES grupo(id) ON DELETE CASCADE,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    wa_jid TEXT NOT NULL,
    telefone TEXT,
    push_name TEXT,
    is_admin BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (grupo_id, wa_jid)
);
CREATE INDEX IF NOT EXISTS idx_grupo_membro_grupo ON grupo_membro (grupo_id);
CREATE INDEX IF NOT EXISTS idx_grupo_membro_empresa_jid
    ON grupo_membro (empresa_id, wa_jid);

-- RLS uniforme (Sprint A.2 STRICT) em cada tabela com empresa_id.
ALTER TABLE captura_lote ENABLE ROW LEVEL SECURITY;
ALTER TABLE captura_lote FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON captura_lote;
CREATE POLICY tenant_isolation ON captura_lote
    USING (_rls_tenant_match(empresa_id)) WITH CHECK (_rls_tenant_match(empresa_id));

ALTER TABLE grupo ENABLE ROW LEVEL SECURITY;
ALTER TABLE grupo FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON grupo;
CREATE POLICY tenant_isolation ON grupo
    USING (_rls_tenant_match(empresa_id)) WITH CHECK (_rls_tenant_match(empresa_id));

ALTER TABLE contato_capturado ENABLE ROW LEVEL SECURITY;
ALTER TABLE contato_capturado FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON contato_capturado;
CREATE POLICY tenant_isolation ON contato_capturado
    USING (_rls_tenant_match(empresa_id)) WITH CHECK (_rls_tenant_match(empresa_id));

ALTER TABLE grupo_membro ENABLE ROW LEVEL SECURITY;
ALTER TABLE grupo_membro FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON grupo_membro;
CREATE POLICY tenant_isolation ON grupo_membro
    USING (_rls_tenant_match(empresa_id)) WITH CHECK (_rls_tenant_match(empresa_id));
