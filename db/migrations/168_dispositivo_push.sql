-- Push por FCM: registro de dispositivos dos operadores.
--
-- O app Android só sabe de mensagem nova com a tela ABERTA (SSE). Medido em
-- produção antes desta migration: 0 atendimentos `em_andamento` e 1 único
-- operador jamais assumiu em 30 dias — o modelo é co-piloto, ninguém vive
-- dentro do painel. Sem push, a mensagem do cliente espera até alguém lembrar
-- de olhar.
--
-- Uma linha por dispositivo (token FCM é a identidade do APARELHO, não do
-- usuário). UNIQUE no token com UPSERT trocando o dono: o mesmo celular que
-- reloga com outro usuário passa a notificar o novo — sem isso, o aparelho
-- do ex-funcionário continuaria recebendo conversa de cliente.
--
-- O alvo do envio é "todos os dispositivos da EMPRESA" (modelo co-piloto:
-- não há dono de atendimento a quem mirar). O worker resolve por empresa_id.

CREATE TABLE IF NOT EXISTS dispositivo_push (
    id BIGSERIAL PRIMARY KEY,
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    fcm_token TEXT NOT NULL UNIQUE,
    plataforma TEXT NOT NULL DEFAULT 'android',
    criado_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Último registro/uso — base pra expurgo futuro de token morto.
    visto_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_dispositivo_push_empresa
    ON dispositivo_push (empresa_id);

-- RLS uniforme (Sprint A.2 — bloco canônico).
ALTER TABLE dispositivo_push ENABLE ROW LEVEL SECURITY;
ALTER TABLE dispositivo_push FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON dispositivo_push;
CREATE POLICY tenant_isolation ON dispositivo_push
    USING (_rls_tenant_match(empresa_id)) WITH CHECK (_rls_tenant_match(empresa_id));
