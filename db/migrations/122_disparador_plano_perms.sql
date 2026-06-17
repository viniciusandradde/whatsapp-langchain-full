-- Disparador (gating de plano + permissões).
--
-- Semeia as features de plano que o preview já lê defensivamente
-- (`features['disparador_max_contatos']`) e as permissões do módulo. Sem isto,
-- `_limite_plano` retorna None (ilimitado) e o gate Free fica inativo.
--
-- Política:
--   Free       → disparador on, sem mídia, cap 25 contatos por disparo.
--   Pro/Enter. → disparador on, com mídia, sem cap (ilimitado).
--
-- Idempotente: merge no JSONB (||) + ON CONFLICT DO NOTHING.

UPDATE plano
   SET features = features || '{"disparador": true, "disparador_media": false, "disparador_max_contatos": 25}'::jsonb
 WHERE slug = 'free';

UPDATE plano
   SET features = features || '{"disparador": true, "disparador_media": true}'::jsonb
 WHERE slug IN ('pro', 'enterprise');

-- Permissões do módulo (RBAC).
INSERT INTO permissao (codigo, descricao, modulo) VALUES
    ('disparador.capturar', 'Capturar contatos/grupos do WhatsApp', 'disparador'),
    ('disparador.disparar', 'Disparar campanhas em massa', 'disparador'),
    ('disparador.api_key.manage', 'Gerenciar API keys do Disparador', 'disparador'),
    ('disparador.template.manage', 'Gerenciar templates do Disparador', 'disparador')
ON CONFLICT (codigo) DO NOTHING;

-- Admin recebe todas; Gestor recebe capturar + disparar.
INSERT INTO perfil_permissao (perfil_id, permissao_codigo)
SELECT pa.id, c.codigo
  FROM perfil_acesso pa
 CROSS JOIN (VALUES
    ('disparador.capturar'),
    ('disparador.disparar'),
    ('disparador.api_key.manage'),
    ('disparador.template.manage')
 ) AS c(codigo)
 WHERE pa.is_system AND pa.nome = 'Admin'
ON CONFLICT DO NOTHING;

INSERT INTO perfil_permissao (perfil_id, permissao_codigo)
SELECT pa.id, c.codigo
  FROM perfil_acesso pa
 CROSS JOIN (VALUES ('disparador.capturar'), ('disparador.disparar')) AS c(codigo)
 WHERE pa.is_system AND pa.nome = 'Gestor'
ON CONFLICT DO NOTHING;
