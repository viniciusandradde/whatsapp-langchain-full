-- 198: saúde das conexões — silêncio deixa de ser alerta; eco ao próprio número
--
-- Incidente de 21/09/2026 18:02: "VSA: sem mensagens há 1 h 26 min (esperadas ≈ 8)
-- · conexão responde". Falso positivo por construção: a regra da mig 196 supunha
-- chegadas independentes (Poisson), mas mensagens chegam em rajadas — medido em
-- produção, a VSA teve 38 silêncios >= 1 h em horário comercial nos 28 dias
-- anteriores, todos com a conexão saudável. O sinal decisivo (a sonda) já dizia
-- "responde".
--
-- A partir daqui: silêncio acima do normal da própria conexão só dispara um ECO
-- (mensagem ao próprio número que tem de voltar pelo webhook); alerta só quando o
-- eco não volta duas vezes. Os episódios de silêncio abertos são fechados aqui,
-- sem aviso no canal (o tick só avisa o que ele mesmo resolve).

ALTER TABLE conexao
    ADD COLUMN IF NOT EXISTS eco_ativo BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS eco_pendente_id TEXT,
    ADD COLUMN IF NOT EXISTS eco_enviado_em TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS ultimo_eco_em TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS eco_falhas_seguidas INT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS eco_solicitado_em TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS ultimo_ack_em TIMESTAMPTZ;

COMMENT ON COLUMN conexao.eco_ativo IS 'Verificação por eco ao próprio número (só Evolution). Desligar para o cliente que não quer a mensagem na conversa "Você".';
COMMENT ON COLUMN conexao.eco_pendente_id IS 'key.id do eco em voo (aguardando voltar pelo webhook).';
COMMENT ON COLUMN conexao.eco_enviado_em IS 'Quando o eco pendente foi enviado.';
COMMENT ON COLUMN conexao.ultimo_eco_em IS 'Último eco que voltou (upsert fromMe ou ack de entrega).';
COMMENT ON COLUMN conexao.eco_falhas_seguidas IS 'Ecos seguidos sem retorno; 2 abrem conexao_caida (origem eco).';
COMMENT ON COLUMN conexao.eco_solicitado_em IS 'Pedido de eco fora do ciclo (ex.: logo após reconectar); o tick atende e limpa.';
COMMENT ON COLUMN conexao.ultimo_ack_em IS 'Último ack de entrega (messages.update) de uma mensagem nossa — saída funcionando.';

SELECT set_config('app.bypass_rls', 'true', true);

UPDATE conexao_alerta
   SET resolvido_em = NOW(),
       detalhe = detalhe || '{"resolvido_por": "mig 198: silêncio deixou de ser alerta"}'::jsonb
 WHERE tipo = 'sem_atividade' AND resolvido_em IS NULL;
