-- 177: feature de plano "voz" — resposta em áudio vira recurso de plano.
--
-- A voz do agente (mig 176) nasceu como opt-in por empresa "sem depender do
-- módulo de planos". Decisão do dono: vira feature de PLANO — disponível nos
-- planos Pro e Enterprise; Free e Pessoal ficam sem (cada resposta falada
-- custa uma chamada de TTS). O gate lê `plano.features->>'voz'` em 3 lugares:
-- preview da voz, PUT da empresa (ligar voz_ativa) e o gatilho no worker
-- (get_empresa_voz_config, que passa a trazer a feature no mesmo SELECT) —
-- downgrade de plano desliga a voz sozinho, sem precisar limpar
-- `empresa.voz_*`. A 1018 (plano pro) continua falando.
--
-- `plano` é catálogo global (sem empresa_id; mig 101 o lista como global,
-- fora do FORCE RLS) — não precisa do bypass usado em migs de seed tenant
-- como a 158. Idempotente: merge no JSONB (`||`), mesmo padrão da mig 122.

UPDATE plano
   SET features = coalesce(features, '{}'::jsonb) || '{"voz": true}'::jsonb
 WHERE slug IN ('pro', 'enterprise');

UPDATE plano
   SET features = coalesce(features, '{}'::jsonb) || '{"voz": false}'::jsonb
 WHERE slug IN ('free', 'pessoal');
