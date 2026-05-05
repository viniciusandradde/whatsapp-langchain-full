-- E2.D M6.b Campanhas: broadcast outbound de mensagem pra lista de
-- telefones. Reaproveita OutboundClient/Conexao já existente.
--
-- Estado da campanha:
--   draft → running → done | partial | aborted
--   - draft: criada, ainda não disparada
--   - running: worker iterando destinatários
--   - done: todos enviados (sucesso ou falha definitiva)
--   - partial: parou no meio (admin abortou ou erro fatal de provider)
--   - aborted: admin cancelou antes de finalizar
--
-- Estado do destinatário:
--   pendente → enviado | falhou
--   - retry de falhas individuais é manual (admin pode "reenviar
--     pendentes/falhos" via endpoint dedicado)

CREATE TABLE IF NOT EXISTS campanha (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    nome TEXT NOT NULL,
    descricao TEXT,
    -- Mensagem direta. Em iteração futura (WABA real), `template_id`
    -- vai apontar pra waba_template.
    mensagem TEXT NOT NULL,
    -- Conexão usada pra enviar. Se NULL no dispatch, busca a primeira
    -- conexão ativa da empresa.
    conexao_id BIGINT REFERENCES conexao(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (
        status IN ('draft', 'running', 'done', 'partial', 'aborted')
    ),
    -- Cooldown entre envios (ms). Default 500ms = 2 msg/s, conservador
    -- pra Evolution e Twilio sandbox sem ser banido.
    intervalo_ms INTEGER NOT NULL DEFAULT 500,
    -- Limite hard de destinatários por campanha pra evitar spam massivo
    -- por bug. UI/endpoint reforça antes do dispatch.
    max_destinatarios INTEGER NOT NULL DEFAULT 1000,
    total_destinatarios INTEGER NOT NULL DEFAULT 0,
    enviados INTEGER NOT NULL DEFAULT 0,
    falhas INTEGER NOT NULL DEFAULT 0,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_by_user_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_campanha_empresa_status
    ON campanha (empresa_id, status, created_at DESC);


CREATE TABLE IF NOT EXISTS campanha_destinatario (
    id BIGSERIAL PRIMARY KEY,
    campanha_id BIGINT NOT NULL REFERENCES campanha(id) ON DELETE CASCADE,
    -- E.164 normalizado. UNIQUE composto previne duplicata por campanha.
    telefone TEXT NOT NULL,
    -- Snapshot opcional do nome/cliente_id pra debugging.
    cliente_id BIGINT REFERENCES cliente(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'pendente' CHECK (
        status IN ('pendente', 'enviado', 'falhou')
    ),
    mensagem_id_externo TEXT,
    erro TEXT,
    sent_at TIMESTAMPTZ,
    UNIQUE (campanha_id, telefone)
);

CREATE INDEX IF NOT EXISTS idx_campanha_dest_pendentes
    ON campanha_destinatario (campanha_id) WHERE status = 'pendente';


-- WABA template stub pra futuras integrações (Twilio Content Templates,
-- Evolution waba). Por enquanto só armazena local; submit pra Facebook
-- continua manual.
CREATE TABLE IF NOT EXISTS waba_template (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    nome TEXT NOT NULL,
    idioma TEXT NOT NULL DEFAULT 'pt_BR',
    body TEXT NOT NULL,
    -- Status do lado do provider (Facebook). Default LOCAL = só
    -- existe no nosso DB, ainda não submetido. Quando submeter,
    -- atualizar via endpoint admin.
    status TEXT NOT NULL DEFAULT 'LOCAL' CHECK (
        status IN ('LOCAL', 'SUBMETIDO', 'APROVADO', 'REJEITADO')
    ),
    payload_externo JSONB,
    created_by_user_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (empresa_id, nome, idioma)
);
