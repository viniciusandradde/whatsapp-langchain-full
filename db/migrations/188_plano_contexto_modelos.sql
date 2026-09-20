-- 188: gate por plano do tamanho do contexto e dos modelos premium (ADR-004).
--
-- A PR B entregou "Premium/BLOQUEADO" só visual. Decisão do dono (20/09):
-- o tier de contexto liberado para os agentes depende do plano contratado.
-- Duas chaves novas em `plano.features` (mesmo padrão da mig 177, voz):
--   contexto_max     — maior tier que a empresa pode salvar/usar
--                      (lite < regular < medium < large < extended)
--   modelos_premium  — libera modelos com preço de entrada > US$ 5/Mtok
-- O gate lê isto em 3 lugares: PUT do agente (402), catálogo (a tela trava
-- o que o plano não tem) e o loader do worker (aplica o MENOR entre o tier
-- do agente e o do plano — downgrade rebaixa sozinho, sem tocar em
-- `agente_ia.contexto_tamanho`). Plano sem a chave = `lite`, sem premium.
--
-- `plano` é catálogo global (fora do FORCE RLS). Idempotente: merge no JSONB.

UPDATE plano
   SET features = coalesce(features, '{}'::jsonb)
                  || '{"contexto_max": "lite", "modelos_premium": false}'::jsonb
 WHERE slug = 'free';

UPDATE plano
   SET features = coalesce(features, '{}'::jsonb)
                  || '{"contexto_max": "regular", "modelos_premium": false}'::jsonb
 WHERE slug = 'pessoal';

UPDATE plano
   SET features = coalesce(features, '{}'::jsonb)
                  || '{"contexto_max": "large", "modelos_premium": true}'::jsonb
 WHERE slug = 'pro';

UPDATE plano
   SET features = coalesce(features, '{}'::jsonb)
                  || '{"contexto_max": "extended", "modelos_premium": true}'::jsonb
 WHERE slug = 'enterprise';
