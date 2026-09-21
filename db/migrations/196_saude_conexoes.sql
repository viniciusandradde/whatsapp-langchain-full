-- 196: Saúde das conexões dos clientes — "sem conexão" e "sem atividade".
--
-- Incidente 16→21/09/2026 (empresa 1018): o aparelho foi desvinculado, mas o
-- socket da Evolution ficou zumbi — `connectionState` seguiu dizendo `open`,
-- a linha `conexao` seguiu `open`, e ninguém foi avisado por 4,5 dias. O
-- webhook descartava `connection.update`, `ultimo_health_check_*` só era
-- gravado pelo botão "Testar" e nenhum loop do worker olhava conexão.
--
-- A partir daqui um tick do worker (`shared/saude_conexoes.py`, a cada 5 min,
-- uma réplica por vez) combina três sinais por conexão:
--   1. passivo  — o webhook grava `connection.update` (estado + statusReason);
--   2. sonda    — consulta REAL ao WhatsApp com timeout curto (não o
--                 `whatsappNumbers`, que tem cache e respondeu pela instância
--                 morta); 2 sondas ruins seguidas = conexão caída;
--   3. silêncio — mensagens esperadas na janela sem inbound, pela média por
--                 (dia da semana, hora local) das últimas 4 semanas
--                 (`conexao_atividade`); esperadas ≥ 8 e recebidas 0 = alerta.
-- Episódios em `conexao_alerta` (mesma máquina da `ia_alerta`, mig 180:
-- dedup, cooldown 6 h, auto-resolve), aviso agrupado no canal da plataforma.

-- Tabelas com empresa_id têm FORCE RLS; o runner de migração pode rodar com
-- papel comum em produção (padrão das migs 161/189).
SELECT set_config('app.bypass_rls', 'true', true);

-- 1) Sinais persistidos na própria conexão.
ALTER TABLE conexao
    ADD COLUMN IF NOT EXISTS ultimo_inbound_em     TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS sonda_falhas_seguidas INT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS desconexao_codigo     INT,
    ADD COLUMN IF NOT EXISTS desconexao_em         TIMESTAMPTZ;

COMMENT ON COLUMN conexao.ultimo_inbound_em IS
    'Última mensagem recebida de cliente nesta conexão (o tick de saúde deriva de message_queue).';
COMMENT ON COLUMN conexao.sonda_falhas_seguidas IS
    'Sondas ativas consecutivas com falha; >= 2 abre o episódio conexao_caida (anti-flap).';
COMMENT ON COLUMN conexao.desconexao_codigo IS
    'statusReason do último connection.update com state=close (401 = aparelho desvinculado).';
COMMENT ON COLUMN conexao.desconexao_em IS
    'Quando a conexão foi vista fechada pela primeira vez (webhook ou sonda); NULL quando aberta.';

-- 2) Atividade recebida por hora (UTC) — sobrevive à retenção de message_queue
--    e é a régua da baseline de silêncio.
CREATE TABLE IF NOT EXISTS conexao_atividade (
    conexao_id  BIGINT NOT NULL REFERENCES conexao(id) ON DELETE CASCADE,
    empresa_id  BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    hora        TIMESTAMPTZ NOT NULL,
    recebidas   INT NOT NULL DEFAULT 0,
    PRIMARY KEY (conexao_id, hora)
);
CREATE INDEX IF NOT EXISTS idx_conexao_atividade_hora ON conexao_atividade (hora);
COMMENT ON TABLE conexao_atividade IS
    'Mensagens recebidas de clientes por conexão e hora (date_trunc hour, UTC); alimentada pelo tick de saúde.';

ALTER TABLE conexao_atividade ENABLE ROW LEVEL SECURITY;
ALTER TABLE conexao_atividade FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON conexao_atividade;
CREATE POLICY tenant_isolation ON conexao_atividade
    USING (_rls_tenant_match(empresa_id)) WITH CHECK (_rls_tenant_match(empresa_id));

-- 3) Episódios por conexão — espelho da ia_alerta (mig 180) com empresa/conexão.
CREATE TABLE IF NOT EXISTS conexao_alerta (
    id            BIGSERIAL PRIMARY KEY,
    empresa_id    BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    conexao_id    BIGINT NOT NULL REFERENCES conexao(id) ON DELETE CASCADE,
    tipo          TEXT NOT NULL CHECK (tipo IN ('conexao_caida', 'sem_atividade')),
    detalhe       JSONB NOT NULL DEFAULT '{}'::jsonb,
    criado_em     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    resolvido_em  TIMESTAMPTZ,
    notificado_em TIMESTAMPTZ
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_conexao_alerta_ativo
    ON conexao_alerta (tipo, conexao_id) WHERE resolvido_em IS NULL;
CREATE INDEX IF NOT EXISTS idx_conexao_alerta_recentes ON conexao_alerta (criado_em DESC);
COMMENT ON TABLE conexao_alerta IS
    'Episódios de saúde por conexão: conexao_caida | sem_atividade. Uma linha ativa por (tipo, conexao).';

ALTER TABLE conexao_alerta ENABLE ROW LEVEL SECURITY;
ALTER TABLE conexao_alerta FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON conexao_alerta;
CREATE POLICY tenant_isolation ON conexao_alerta
    USING (_rls_tenant_match(empresa_id)) WITH CHECK (_rls_tenant_match(empresa_id));

-- 4) Estado do tick: claim entre as réplicas do worker + marca d'água da
--    atividade. Recurso de plataforma, sem empresa_id/RLS (padrão mig 178).
CREATE TABLE IF NOT EXISTS saude_conexoes_estado (
    id                            INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    proximo_tick_em               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ultimo_tick_em                TIMESTAMPTZ,
    ultimo_tick_ok                BOOLEAN,
    ultimo_erro                   TEXT,
    marca_atividade               TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    evolution_indisponivel_desde  TIMESTAMPTZ
);
COMMENT ON COLUMN saude_conexoes_estado.marca_atividade IS
    'Até onde message_queue já foi acumulada em conexao_atividade (o tick recomputa a hora da marca).';

-- 5) Backfill: 28 dias de baseline no primeiro dia e a última mensagem
--    recebida por conexão. Predicado canônico de "recebida do cliente"
--    (o mesmo de shared/atendimento_visualizacao.py); starts_with em vez
--    de LIKE por causa dos placeholders do psycopg no código que o repete.
INSERT INTO conexao_atividade (conexao_id, empresa_id, hora, recebidas)
SELECT conexao_id, empresa_id, date_trunc('hour', created_at), count(*)
  FROM message_queue
 WHERE conexao_id IS NOT NULL
   AND created_at >= NOW() - interval '28 days'
   AND created_at <  date_trunc('hour', NOW())
   AND incoming_message IS NOT NULL AND incoming_message <> ''
   AND COALESCE(interna, FALSE) = FALSE
   AND NOT starts_with(COALESCE(message_id, ''), 'synthetic:')
 GROUP BY 1, 2, 3
ON CONFLICT (conexao_id, hora) DO NOTHING;

UPDATE conexao c
   SET ultimo_inbound_em = m.max_at
  FROM (SELECT conexao_id, max(created_at) AS max_at
          FROM message_queue
         WHERE conexao_id IS NOT NULL
           AND created_at >= NOW() - interval '90 days'
           AND incoming_message IS NOT NULL AND incoming_message <> ''
           AND COALESCE(interna, FALSE) = FALSE
           AND NOT starts_with(COALESCE(message_id, ''), 'synthetic:')
         GROUP BY conexao_id) m
 WHERE c.id = m.conexao_id
   AND c.ultimo_inbound_em IS NULL;

INSERT INTO saude_conexoes_estado (id, marca_atividade)
VALUES (1, date_trunc('hour', NOW()))
ON CONFLICT (id) DO NOTHING;
