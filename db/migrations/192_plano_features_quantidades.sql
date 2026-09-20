-- 192: ADR-005 leva C2 — quantidades e retenção por plano (matriz da ADR §3).
-- Chaves numéricas em `plano.features` (NULL = ilimitado, como as colunas
-- limite_*; ausente = 0/off, errando para o lado barato) e booleanas:
--   departamentos_max 1/2/10/∞ · workflows_max 0/0/3/∞ (workflows ATIVOS)
--   menus_max 1/∞/∞/∞ · retencao_max_dias 30/90/365/∞ · auditoria_dias 30/90/∞/∞
--   csat, resumo_diario, bateria_testes: Pessoal+ · observabilidade (fila de
--   mensagens, traces) e qualidade_ia (RAG/sandbox/Allure): Pro/Enterprise.
-- `plano` é catálogo global (fora do FORCE RLS). Idempotente: merge no JSONB.

UPDATE plano SET features = coalesce(features, '{}'::jsonb) || '{
    "departamentos_max": 1, "workflows_max": 0, "menus_max": 1,
    "retencao_max_dias": 30, "auditoria_dias": 30,
    "csat": false, "resumo_diario": false, "bateria_testes": false,
    "observabilidade": false, "qualidade_ia": false}'::jsonb
 WHERE slug = 'free';

UPDATE plano SET features = coalesce(features, '{}'::jsonb) || '{
    "departamentos_max": 2, "workflows_max": 0, "menus_max": null,
    "retencao_max_dias": 90, "auditoria_dias": 90,
    "csat": true, "resumo_diario": true, "bateria_testes": true,
    "observabilidade": false, "qualidade_ia": false}'::jsonb
 WHERE slug = 'pessoal';

UPDATE plano SET features = coalesce(features, '{}'::jsonb) || '{
    "departamentos_max": 10, "workflows_max": 3, "menus_max": null,
    "retencao_max_dias": 365, "auditoria_dias": null,
    "csat": true, "resumo_diario": true, "bateria_testes": true,
    "observabilidade": true, "qualidade_ia": true}'::jsonb
 WHERE slug = 'pro';

UPDATE plano SET features = coalesce(features, '{}'::jsonb) || '{
    "departamentos_max": null, "workflows_max": null, "menus_max": null,
    "retencao_max_dias": null, "auditoria_dias": null,
    "csat": true, "resumo_diario": true, "bateria_testes": true,
    "observabilidade": true, "qualidade_ia": true}'::jsonb
 WHERE slug = 'enterprise';

-- Grandfathering (ADR-005 D3) — produção 20/09/2026: só a sandbox 999 (Free)
-- está fora da matriz (7 departamentos). Workflows só na 1 (Enterprise),
-- retenção NULL em todas, CSAT/resumo desligados.
SELECT set_config('app.bypass_rls', 'true', true);
INSERT INTO feature_flag (empresa_id, key, value, descricao)
SELECT 999, 'plano.departamentos_max', 'null'::jsonb,
       'ADR-005 D3 — sandbox de avaliação com 7 departamentos antes do limite (20/09/2026)'
 WHERE EXISTS (SELECT 1 FROM empresa WHERE id = 999)
ON CONFLICT (empresa_id, key) DO NOTHING;
