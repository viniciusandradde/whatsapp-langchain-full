-- Sprint R.3 — 5 agentes "rádio" setoriais na sandbox empresa 999.
-- Cada um tem pasta KB própria (vazia inicialmente — populada via R.4 cluster).

-- 1. Departamentos (FK pros agentes)
INSERT INTO departamento (id, empresa_id, nome, ativo) VALUES
    (9991, 999, 'Rádio TI', TRUE),
    (9992, 999, 'Rádio Hospitalar', TRUE),
    (9993, 999, 'Rádio Financeiro', TRUE),
    (9994, 999, 'Rádio Diretoria', TRUE),
    (9995, 999, 'Rádio Operacional', TRUE)
ON CONFLICT (id) DO UPDATE SET nome = EXCLUDED.nome, ativo = TRUE;

-- 2. Pastas KB (1 por setor)
INSERT INTO pasta (empresa_id, nome) VALUES
    (999, 'KB Rádio TI'),
    (999, 'KB Rádio Hospitalar'),
    (999, 'KB Rádio Financeiro'),
    (999, 'KB Rádio Diretoria'),
    (999, 'KB Rádio Operacional')
ON CONFLICT DO NOTHING;

-- 3. Agentes IA (5 setoriais)
INSERT INTO agente_ia (
    empresa_id, slug, nome, template_catalog,
    estilo_resposta, ativo, is_default, departamento_default_id
) VALUES
    (999, 'radio-ti', 'Rádio TI', 'atendimento_completo', 'preciso', TRUE, FALSE, 9991),
    (999, 'radio-hospitalar', 'Rádio Hospitalar', 'atendimento_completo', 'equilibrado', TRUE, FALSE, 9992),
    (999, 'radio-financeiro', 'Rádio Financeiro', 'atendimento_completo', 'preciso', TRUE, FALSE, 9993),
    (999, 'radio-diretoria', 'Rádio Diretoria', 'atendimento_completo', 'preciso', TRUE, FALSE, 9994),
    (999, 'radio-operacional', 'Rádio Operacional', 'atendimento_completo', 'equilibrado', TRUE, TRUE, 9995)
ON CONFLICT (empresa_id, slug) DO UPDATE SET
    departamento_default_id = EXCLUDED.departamento_default_id,
    template_catalog = EXCLUDED.template_catalog,
    ativo = TRUE;

-- 4. Vincula agente_ia.base_conhecimento_ids à sua pasta KB
UPDATE agente_ia ai
   SET base_conhecimento_ids = ARRAY[p.id]::bigint[]
  FROM pasta p
 WHERE ai.empresa_id = 999 AND p.empresa_id = 999
   AND (
     (ai.slug = 'radio-ti' AND p.nome = 'KB Rádio TI') OR
     (ai.slug = 'radio-hospitalar' AND p.nome = 'KB Rádio Hospitalar') OR
     (ai.slug = 'radio-financeiro' AND p.nome = 'KB Rádio Financeiro') OR
     (ai.slug = 'radio-diretoria' AND p.nome = 'KB Rádio Diretoria') OR
     (ai.slug = 'radio-operacional' AND p.nome = 'KB Rádio Operacional')
   );

-- Verificação
SELECT 'agentes' as tipo, COUNT(*) FROM agente_ia WHERE empresa_id=999
UNION ALL
SELECT 'pastas', COUNT(*) FROM pasta WHERE empresa_id=999 AND nome LIKE 'KB Rádio%';

SELECT slug, base_conhecimento_ids, departamento_default_id FROM agente_ia WHERE empresa_id=999;
