-- 191: ADR-005 leva C1 — módulos passam a depender do plano (matriz da ADR §3).
--
-- As chaves `mcp`, `rbac`, `menu_moderno`, `disparador` e `white_label` já
-- estavam semeadas desde as migs 059/122/134 e o código IGNORAVA todas (só o
-- teto/mídia do disparo era aplicado). Esta migration corrige o que estava
-- fora da matriz e acrescenta as duas que faltavam:
--   disparador    — Free tinha `true` no seed (!) → false. Módulo inteiro
--                   (campanhas, contatos, grupos, extensão) é Pro/Enterprise.
--   webhooks      — hooks de saída (+ DLQ): Pro/Enterprise.
--   waba          — conexão pela API oficial da Meta (Embedded Signup):
--                   Pro/Enterprise. Evolution continua em todo plano.
--   mcp (só Ent) · rbac (Pro/Ent) · white_label (só Ent) · menu_moderno
--   (Pro/Ent) — reafirmados para os 4 planos, para nenhum ficar sem a chave.
--
-- `plano` é catálogo global (fora do FORCE RLS). Idempotente: merge no JSONB.

UPDATE plano
   SET features = coalesce(features, '{}'::jsonb) || '{
        "disparador": false, "webhooks": false, "waba": false,
        "mcp": false, "rbac": false, "white_label": false, "menu_moderno": false}'::jsonb
 WHERE slug IN ('free', 'pessoal');

UPDATE plano
   SET features = coalesce(features, '{}'::jsonb) || '{
        "disparador": true, "webhooks": true, "waba": true,
        "mcp": false, "rbac": true, "white_label": false, "menu_moderno": true}'::jsonb
 WHERE slug = 'pro';

UPDATE plano
   SET features = coalesce(features, '{}'::jsonb) || '{
        "disparador": true, "webhooks": true, "waba": true,
        "mcp": true, "rbac": true, "white_label": true, "menu_moderno": true}'::jsonb
 WHERE slug = 'enterprise';

-- Grandfathering (ADR-005 D3) — levantamento em produção (20/09/2026):
-- white-label (logo/cores/nome de marca) está configurado em 4 empresas fora
-- da matriz — 1012 (Free), 1013, 1016 e 1018 (Pro). O gate é no SALVAR
-- (PUT/logo); o que está gravado continua sendo exibido. A flag deixa essas
-- empresas continuarem editando a marca que já têm. Campanhas, MCP, hooks e
-- WABA: zero uso fora da matriz. Perfil customizado: só na 1018 (Pro, tem
-- `rbac`). Menu moderno: só na 1 (Enterprise).
SELECT set_config('app.bypass_rls', 'true', true);

INSERT INTO feature_flag (empresa_id, key, value, descricao)
SELECT e.id, 'plano.white_label', 'true'::jsonb,
       'ADR-005 D3 — white-label já configurado antes do gate (20/09/2026)'
  FROM empresa e
 WHERE e.id IN (1012, 1013, 1016, 1018)
ON CONFLICT (empresa_id, key) DO NOTHING;
