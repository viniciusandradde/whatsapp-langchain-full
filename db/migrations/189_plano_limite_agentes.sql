-- ADR-005, leva A — limites que já existem passam a valer + limite de agentes.
--
-- `limite_usuarios`, `limite_atendimentos_mes` e `limite_documentos_kb` já
-- estavam semeados (mig 059/134) e eram só CONTADOS no /billing — nenhuma rota
-- bloqueava. A leva A liga o `require_plano_limit` neles e acrescenta o único
-- limite que faltava na tabela: agentes de IA por empresa (a matriz da ADR-005
-- §3: Free 1 · Pessoal 1 · Pro 5 · Enterprise ilimitado). NULL = ilimitado,
-- como as outras colunas de limite.
ALTER TABLE plano
    ADD COLUMN IF NOT EXISTS limite_agentes INT;

UPDATE plano
   SET limite_agentes = CASE slug
                            WHEN 'free' THEN 1
                            WHEN 'pessoal' THEN 1
                            WHEN 'pro' THEN 5
                            ELSE NULL
                        END,
       updated_at = NOW()
 WHERE limite_agentes IS NULL
   AND slug IN ('free', 'pessoal', 'pro');

COMMENT ON COLUMN plano.limite_agentes IS
    'ADR-005 leva A — máximo de agentes de IA ativos por empresa. NULL = ilimitado. '
    'Aplicado em POST /api/v1/agentes (require_plano_limit("agentes")).';

-- Aviso de 80 % dos atendimentos do mês (ADR-005 D5): o worker avisa a empresa
-- UMA vez por mês pelo WhatsApp do resumo diário. A marca é um timestamp para
-- o claim ser atômico entre as réplicas do worker (UPDATE ... WHERE marca IS
-- NULL OR marca < início do mês) — o mesmo desenho do `resumo_diario_last_sent`.
ALTER TABLE empresa
    ADD COLUMN IF NOT EXISTS plano_alerta_atendimentos_em TIMESTAMPTZ;

COMMENT ON COLUMN empresa.plano_alerta_atendimentos_em IS
    'ADR-005 D5 — quando o aviso de 80 % dos atendimentos do mês foi enviado '
    '(um por mês; NULL = nunca).';

-- Grandfathering (ADR-005 D3): exceção por empresa vive em `feature_flag` com
-- a chave `plano.<nome>` e sobrepõe o plano na leitura (`get_plano_info`).
-- Levantamento em produção (20/09/2026): a única empresa acima de um limite
-- desta leva é a sandbox 999 (Free, 8 agentes de avaliação). `'null'::jsonb`
-- = ilimitado, como NULL na coluna do plano. O INSERT só acontece onde a
-- empresa existe (no dev ela também é a sandbox).
--
-- `feature_flag` tem empresa_id e FORCE RLS: o runner de migração pode rodar
-- com papel comum em produção, então o bypass é explícito (padrão da mig 161).
SELECT set_config('app.bypass_rls', 'true', true);

INSERT INTO feature_flag (empresa_id, key, value, descricao)
SELECT 999, 'plano.limite_agentes', 'null'::jsonb,
       'ADR-005 D3 — sandbox de avaliação já tinha 8 agentes quando o limite entrou (20/09/2026)'
 WHERE EXISTS (SELECT 1 FROM empresa WHERE id = 999)
ON CONFLICT (empresa_id, key) DO NOTHING;
