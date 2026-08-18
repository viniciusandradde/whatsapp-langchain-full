-- 173 — Relatório de produção: histórico, pedidos sob demanda e agendamento.
--
-- Hoje o relatório existe só no Telegram e no host: não dá para consultar o de
-- ontem, rodar sob demanda, nem mudar o horário sem editar systemd. Estas
-- tabelas trazem o recurso para a gestão da VSA sem mover a COLETA para dentro
-- da aplicação — o container não enxerga docker, disco nem os logs da
-- Evolution, e `df` dentro dele responde o overlay, o que é pior que não
-- responder: número plausível e errado.
--
-- A inversão: o host continua coletando (é quem tem acesso) e passa a
-- PUBLICAR aqui. O painel lê o histórico e enfileira pedidos; o host consome.
--
-- **Escopo de plataforma, sem `empresa_id` e sem RLS** — mesmo desenho de
-- `platform_integration_config` (mig 117). Não é dado de tenant: fala do
-- servidor inteiro. Quem protege é o gate `is_superadmin` nas rotas, como já
-- acontece no relatório de uso por cliente.

CREATE TABLE IF NOT EXISTS relatorio_producao (
    id                BIGSERIAL PRIMARY KEY,
    criado_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- 'agendado' (timer do host) ou 'manual' (botão no painel).
    origem            TEXT NOT NULL CHECK (origem IN ('agendado', 'manual')),
    -- Quem pediu, quando manual. Sem FK: `auth."user"` vive em outro schema e
    -- apagar um usuário não deve levar junto o histórico do servidor.
    solicitado_por    TEXT,
    -- Severidade CALCULADA a partir dos achados, não escrita pelo modelo.
    severidade        TEXT NOT NULL CHECK (severidade IN ('ok', 'atencao', 'critico')),
    -- Os achados das checagens determinísticas: a parte verificável.
    achados           JSONB NOT NULL DEFAULT '[]'::jsonb,
    -- A redação do modelo. NULL quando o LLM falhou ou não está configurado —
    -- e o relatório vale mesmo assim, porque a análise está em `achados`.
    texto             TEXT,
    modelo            TEXT,
    -- Dados crus da coleta, para conferir qualquer conclusão contra a fonte.
    dados             JSONB NOT NULL DEFAULT '{}'::jsonb,
    -- Falha da REDAÇÃO, não da análise.
    erro              TEXT
);

COMMENT ON TABLE relatorio_producao IS
  'Histórico do relatório diário de produção (mig 173). Escopo de plataforma: sem empresa_id, protegido por is_superadmin nas rotas.';
COMMENT ON COLUMN relatorio_producao.achados IS
  'Achados das checagens determinísticas (scripts/producao_checks.py). É a análise; `texto` é só a redação.';

CREATE INDEX IF NOT EXISTS idx_relatorio_producao_criado
    ON relatorio_producao (criado_at DESC);

-- Fila de pedidos sob demanda.
--
-- Existe porque o painel roda em container e NÃO pode disparar o script do
-- host. Em vez de abrir um canal privilegiado (SSH de dentro do container, ou
-- o socket do Docker montado — quem invadisse o container controlaria a
-- máquina), o painel só INSERE aqui e o host, que já roda de minuto em minuto,
-- consome. A fronteira de privilégio continua onde está.
CREATE TABLE IF NOT EXISTS relatorio_producao_pedido (
    id             BIGSERIAL PRIMARY KEY,
    criado_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    solicitado_por TEXT NOT NULL,
    atendido_at    TIMESTAMPTZ,
    relatorio_id   BIGINT REFERENCES relatorio_producao(id) ON DELETE SET NULL
);

COMMENT ON TABLE relatorio_producao_pedido IS
  'Pedidos de "gerar agora" (mig 173). O painel insere; o host consome. Evita dar ao container acesso ao host.';

-- Índice parcial: o host pergunta "há pedido pendente?" a cada ciclo, e essa é
-- a única consulta quente da tabela.
CREATE INDEX IF NOT EXISTS idx_relatorio_producao_pedido_pendente
    ON relatorio_producao_pedido (criado_at)
    WHERE atendido_at IS NULL;

-- Configuração do agendamento — uma linha só.
--
-- O horário sai do systemd e vem para cá pelo mesmo motivo do resumo diário
-- (mig 135): quem opera muda horário pelo painel, não por unit file. O timer
-- do host passa a acordar de minuto em minuto e decidir se é a hora, com
-- `last_run_date` fazendo o claim atômico contra execução dupla — exatamente
-- o padrão de `shared/resumo_diario.py::_claim_envio_hoje`.
CREATE TABLE IF NOT EXISTS relatorio_producao_config (
    id             SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    ativo          BOOLEAN NOT NULL DEFAULT TRUE,
    horario        TIME NOT NULL DEFAULT '05:00',
    tz             TEXT NOT NULL DEFAULT 'America/Campo_Grande',
    -- Data LOCAL do último envio. É o claim: quem consegue o UPDATE, roda.
    last_run_date  DATE,
    atualizado_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON COLUMN relatorio_producao_config.horario IS
  'Hora local do envio agendado. Default 05:00 America/Campo_Grande = as 08:00 GMT que o timer do systemd já usava.';

INSERT INTO relatorio_producao_config (id) VALUES (1)
ON CONFLICT (id) DO NOTHING;
