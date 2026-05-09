-- Sprint R — corrigir agentes sandbox: usar os mesmos do chat-nexus prod.
-- Em vez de radio-ti/hospitalar/etc, usa: atendimento, atendimento-cliente,
-- agendamentos, exames, orcamento, ouvidoria, rh-recrutamento-selecao, tesouraria.

BEGIN;

-- 1. Limpa agentes radio-* da sandbox 999
DELETE FROM agente_ia WHERE empresa_id = 999 AND slug LIKE 'radio-%';

-- 2. Limpa pastas KB Rádio antigas
DELETE FROM pasta WHERE empresa_id = 999 AND nome LIKE 'KB Rádio%';

-- 3. Limpa departamentos antigos (9991-9995)
DELETE FROM departamento WHERE empresa_id = 999 AND id BETWEEN 9991 AND 9995;

-- 4. Departamentos espelho dos da empresa 1 (IDs com offset 999000)
INSERT INTO departamento (id, empresa_id, nome, ativo) VALUES
    (999001, 999, 'Ouvidoria', TRUE),
    (999002, 999, 'Tesouraria', TRUE),
    (999003, 999, 'Atendimento ao Cliente', TRUE),
    (999004, 999, 'Recrutamento e Seleção', TRUE),
    (999005, 999, 'Agendamentos', TRUE),
    (999006, 999, 'Orçamento', TRUE),
    (999007, 999, 'Exames', TRUE)
ON CONFLICT (id) DO UPDATE SET nome = EXCLUDED.nome, ativo = TRUE;

-- 5. Pastas KB (mesmas labels do prod)
INSERT INTO pasta (empresa_id, nome) VALUES
    (999, 'KB Atendimento'),
    (999, 'KB Atendimento Cliente VSA'),
    (999, 'KB Agendamentos'),
    (999, 'KB Exames'),
    (999, 'KB Orçamento'),
    (999, 'KB Ouvidoria'),
    (999, 'KB Recrutamento'),
    (999, 'KB Tesouraria')
ON CONFLICT DO NOTHING;

-- 6. Agentes IA — slugs IDÊNTICOS aos do chat-nexus prod
INSERT INTO agente_ia (
    empresa_id, slug, nome, template_catalog,
    estilo_resposta, ativo, is_default, departamento_default_id
) VALUES
    (999, 'atendimento', 'Atendimento ao Cliente', 'atendimento_completo', 'equilibrado', TRUE, TRUE, 999003),
    (999, 'atendimento-cliente', 'Atendimento Cliente VSA', 'atendimento_completo', 'equilibrado', TRUE, FALSE, NULL),
    (999, 'agendamentos', 'Agendamentos', 'atendimento_completo', 'equilibrado', TRUE, FALSE, 999005),
    (999, 'exames', 'Exames', 'atendimento_completo', 'equilibrado', TRUE, FALSE, 999007),
    (999, 'orcamento', 'Orçamento', 'atendimento_completo', 'equilibrado', TRUE, FALSE, 999006),
    (999, 'ouvidoria', 'Ouvidoria', 'atendimento_completo', 'equilibrado', TRUE, FALSE, 999001),
    (999, 'rh-recrutamento-selecao', 'Recrutamento e Seleção', 'atendimento_completo', 'equilibrado', TRUE, FALSE, 999004),
    (999, 'tesouraria', 'Tesouraria', 'atendimento_completo', 'equilibrado', TRUE, FALSE, 999002)
ON CONFLICT (empresa_id, slug) DO UPDATE SET
    departamento_default_id = EXCLUDED.departamento_default_id,
    template_catalog = EXCLUDED.template_catalog,
    ativo = TRUE;

-- 7. Vincular agente.base_conhecimento_ids → pasta correta
UPDATE agente_ia ai
   SET base_conhecimento_ids = ARRAY[p.id]::bigint[]
  FROM pasta p
 WHERE ai.empresa_id = 999 AND p.empresa_id = 999
   AND (
     (ai.slug = 'atendimento'             AND p.nome = 'KB Atendimento') OR
     (ai.slug = 'atendimento-cliente'     AND p.nome = 'KB Atendimento Cliente VSA') OR
     (ai.slug = 'agendamentos'            AND p.nome = 'KB Agendamentos') OR
     (ai.slug = 'exames'                  AND p.nome = 'KB Exames') OR
     (ai.slug = 'orcamento'               AND p.nome = 'KB Orçamento') OR
     (ai.slug = 'ouvidoria'               AND p.nome = 'KB Ouvidoria') OR
     (ai.slug = 'rh-recrutamento-selecao' AND p.nome = 'KB Recrutamento') OR
     (ai.slug = 'tesouraria'              AND p.nome = 'KB Tesouraria')
   );

-- 8. Re-mapear fewshot_example.agente_slug pros novos slugs
-- Mapeamento setor (R.2 classificou) → agente_slug (chat-nexus):
--   ti        → atendimento (genérico — TI bate em "atendimento técnico")
--   hospitalar → exames (mais comum: marcar/ver exames)
--   financeiro → orcamento (cobranças/preços/parcelamento)
--   diretoria → atendimento (encaminhamento executivo)
--   operacional → atendimento (rotinas, alertas)
--   outro     → atendimento (default)

UPDATE fewshot_example
   SET agente_slug = CASE setor_classificado
        WHEN 'ti'          THEN 'atendimento'
        WHEN 'hospitalar'  THEN 'exames'
        WHEN 'financeiro'  THEN 'orcamento'
        WHEN 'diretoria'   THEN 'atendimento'
        WHEN 'operacional' THEN 'atendimento'
        ELSE 'atendimento'
       END
 WHERE empresa_id = 999;

-- 9. Mesmo update em rag_query_log
UPDATE rag_query_log
   SET agente_slug = CASE
        WHEN agente_slug LIKE 'radio-%' THEN
            CASE
                WHEN agente_slug = 'radio-ti' THEN 'atendimento'
                WHEN agente_slug = 'radio-hospital' THEN 'exames'
                WHEN agente_slug = 'radio-financeiro' THEN 'orcamento'
                WHEN agente_slug = 'radio-faturamento' THEN 'orcamento'
                WHEN agente_slug = 'radio-cobranca' THEN 'tesouraria'
                WHEN agente_slug = 'radio-diretoria' THEN 'atendimento'
                WHEN agente_slug = 'radio-operacional' THEN 'atendimento'
                WHEN agente_slug = 'radio-rh' THEN 'rh-recrutamento-selecao'
                WHEN agente_slug = 'radio-recepcao' THEN 'atendimento'
                WHEN agente_slug = 'radio-suporte' THEN 'atendimento'
                WHEN agente_slug = 'radio-auditoria' THEN 'atendimento'
                WHEN agente_slug = 'radio-compliance' THEN 'ouvidoria'
                WHEN agente_slug = 'radio-engenharia' THEN 'atendimento'
                WHEN agente_slug = 'radio-manutencao' THEN 'atendimento'
                WHEN agente_slug = 'radio-atendimento-geral' THEN 'atendimento'
                ELSE 'atendimento'
            END
        ELSE agente_slug
       END
 WHERE empresa_id = 999;

COMMIT;

-- Verificação
SELECT '=== Agentes 999 ===' as info;
SELECT slug, nome, base_conhecimento_ids FROM agente_ia WHERE empresa_id=999 ORDER BY slug;
SELECT '=== Distribuição agente_slug em fewshot ===' as info;
SELECT agente_slug, COUNT(*) FROM fewshot_example WHERE empresa_id=999 GROUP BY 1 ORDER BY 2 DESC;
