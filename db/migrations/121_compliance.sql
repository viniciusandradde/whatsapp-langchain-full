-- Disparador (Task 8) — compliance: opt-out/supressão + kill-switch.
--
-- Denúncias são o gatilho nº1 de ban no WhatsApp não-oficial. Quem pede
-- STOP/PARAR entra na lista de supressão (o worker detecta e registra) e o
-- resolver de disparo filtra esses contatos. O kill-switch aborta a campanha
-- automaticamente se a taxa de falha estourar o limite (sinal de número
-- comprometido / lista ruim).

CREATE TABLE IF NOT EXISTS disparador_opt_out (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    wa_jid TEXT NOT NULL,
    telefone TEXT,
    motivo TEXT NOT NULL DEFAULT 'user_request'
        CHECK (motivo IN ('user_request', 'bounce', 'complaint', 'manual')),
    origem TEXT,                               -- campanha_id, webhook, manual...
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (empresa_id, wa_jid)
);
CREATE INDEX IF NOT EXISTS idx_opt_out_empresa_tel
    ON disparador_opt_out (empresa_id, telefone);

-- Kill-switch + razão de aborto na campanha.
ALTER TABLE campanha
    ADD COLUMN IF NOT EXISTS kill_switch_pct INT NOT NULL DEFAULT 30,
    ADD COLUMN IF NOT EXISTS aborted_reason TEXT;

-- RLS uniforme.
ALTER TABLE disparador_opt_out ENABLE ROW LEVEL SECURITY;
ALTER TABLE disparador_opt_out FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON disparador_opt_out;
CREATE POLICY tenant_isolation ON disparador_opt_out
    USING (_rls_tenant_match(empresa_id)) WITH CHECK (_rls_tenant_match(empresa_id));
