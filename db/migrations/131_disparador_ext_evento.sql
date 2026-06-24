-- Telemetria própria da extensão Chrome (Disparador).
-- Substitui a telemetria GA4 do ZDG (que mandava dados pra conta deles): os
-- eventos da NOSSA extensão ficam aqui, por empresa, isolados via RLS.
-- Gravado pelo endpoint POST /api/disparador/ext/telemetria (auth por API key).

CREATE TABLE IF NOT EXISTS disparador_ext_evento (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    evento TEXT NOT NULL,             -- instalada | ativada | captura | disparo_iniciado | disparo_concluido
    meta JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_disparador_ext_evento_empresa
    ON disparador_ext_evento (empresa_id, created_at DESC);

-- RLS STRICT (Sprint A.2) — mesma policy uniforme das tabelas de captura.
ALTER TABLE disparador_ext_evento ENABLE ROW LEVEL SECURITY;
ALTER TABLE disparador_ext_evento FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON disparador_ext_evento;
CREATE POLICY tenant_isolation ON disparador_ext_evento
    USING (_rls_tenant_match(empresa_id)) WITH CHECK (_rls_tenant_match(empresa_id));
