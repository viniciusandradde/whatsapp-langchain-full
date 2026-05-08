-- Seed reproduzível pra Sprint K (testes E2E + CI).
-- Idempotente — pode rodar múltiplas vezes sem erro.
-- Cria: empresa, 7 deptos, 8 agentes, 1 menu + 8 items, 1 conexao,
-- 7 atendentes test-atd-*, atribuições.

-- 1. Empresa raiz
INSERT INTO empresa (id, nome, slug, status)
VALUES (1, 'VSA Tech (test)', 'vsa-tech', 'active')
ON CONFLICT (id) DO UPDATE SET nome = EXCLUDED.nome;

-- 2. Conexão default (provider mock pra não enviar mensagens reais)
INSERT INTO conexao (id, empresa_id, provider, from_number, status, default_agent_id, display_name)
VALUES (1, 1, 'twilio_sandbox', '+14155238886', 'active', 'atendimento', 'Sandbox Teste')
ON CONFLICT (id) DO UPDATE SET status = 'active';

-- 3. Departamentos (7 setores) — IDs fixos pros testes referenciarem
INSERT INTO departamento (id, empresa_id, nome, ativo) VALUES
    (1, 1, 'Ouvidoria', TRUE),
    (2, 1, 'Tesouraria', TRUE),
    (3, 1, 'Atendimento ao Cliente', TRUE),
    (4, 1, 'Recrutamento e Seleção', TRUE),
    (5, 1, 'Agendamentos', TRUE),
    (6, 1, 'Orçamento', TRUE),
    (7, 1, 'Exames', TRUE)
ON CONFLICT (id) DO UPDATE SET nome = EXCLUDED.nome, ativo = TRUE;

-- 4. Agentes IA (8 — 1 sem dep_default pra testar fallback)
INSERT INTO agente_ia (
    empresa_id, slug, nome, template_catalog,
    estilo_resposta, ativo, is_default, departamento_default_id
) VALUES
    (1, 'atendimento', 'Atendimento ao Cliente', 'atendimento_completo', 'equilibrado', TRUE, TRUE, 3),
    (1, 'atendimento-cliente', 'Atendimento Cliente VSA', 'atendimento_completo', 'equilibrado', TRUE, FALSE, NULL),
    (1, 'agendamentos', 'Agendamentos', 'atendimento_completo', 'equilibrado', TRUE, FALSE, 5),
    (1, 'exames', 'Exames', 'atendimento_completo', 'equilibrado', TRUE, FALSE, 7),
    (1, 'orcamento', 'Orçamento', 'atendimento_completo', 'equilibrado', TRUE, FALSE, 6),
    (1, 'ouvidoria', 'Ouvidoria', 'atendimento_completo', 'equilibrado', TRUE, FALSE, 1),
    (1, 'rh-recrutamento-selecao', 'Recrutamento e Seleção', 'atendimento_completo', 'equilibrado', TRUE, FALSE, 4),
    (1, 'tesouraria', 'Tesouraria', 'atendimento_completo', 'equilibrado', TRUE, FALSE, 2)
ON CONFLICT (empresa_id, slug) DO UPDATE SET
    departamento_default_id = EXCLUDED.departamento_default_id,
    template_catalog = EXCLUDED.template_catalog,
    ativo = TRUE;

-- 5. Menu chatbot principal — 1 menu + 8 items raiz com chamar_agente
INSERT INTO menu_chatbot (id, empresa_id, conexao_id, nome, ativo, mensagem_boas_vindas)
VALUES (1, 1, NULL, 'Triagem inicial', TRUE,
        'Olá! Sou a IA da VSA Tech. Como posso te ajudar hoje?')
ON CONFLICT (id) DO UPDATE SET ativo = TRUE;

-- Items raiz: ordem 1-8 mapeando direto pros agentes
-- IDs fixos pra simplicidade (4-11 — pulando 1-3 que nem existem antes)
INSERT INTO menu_item (id, menu_id, parent_id, ordem, label, acao_tipo, acao_payload, ativo) VALUES
    (1, 1, NULL, 1, 'Atendimento ao Cliente', 'chamar_agente',
     '{"agente_slug":"atendimento","mensagem_pre":"Vou te conectar com Atendimento ao Cliente…"}',
     TRUE),
    (2, 1, NULL, 2, 'Atendimento Cliente VSA', 'chamar_agente',
     '{"agente_slug":"atendimento-cliente","mensagem_pre":"Vou te conectar com Atendimento Cliente VSA…"}',
     TRUE),
    (3, 1, NULL, 3, 'Agendamentos', 'chamar_agente',
     '{"agente_slug":"agendamentos","mensagem_pre":"Vou te conectar com Agendamentos…"}',
     TRUE),
    (4, 1, NULL, 4, 'Exames', 'chamar_agente',
     '{"agente_slug":"exames","mensagem_pre":"Vou te conectar com Exames…"}',
     TRUE),
    (5, 1, NULL, 5, 'Orçamento', 'chamar_agente',
     '{"agente_slug":"orcamento","mensagem_pre":"Vou te conectar com Orçamento…"}',
     TRUE),
    (6, 1, NULL, 6, 'Ouvidoria', 'chamar_agente',
     '{"agente_slug":"ouvidoria","mensagem_pre":"Vou te conectar com Ouvidoria…"}',
     TRUE),
    (7, 1, NULL, 7, 'Recrutamento e Seleção', 'chamar_agente',
     '{"agente_slug":"rh-recrutamento-selecao","mensagem_pre":"Vou te conectar com RH…"}',
     TRUE),
    (8, 1, NULL, 8, 'Tesouraria', 'chamar_agente',
     '{"agente_slug":"tesouraria","mensagem_pre":"Vou te conectar com Tesouraria…"}',
     TRUE)
ON CONFLICT (id) DO UPDATE SET
    label = EXCLUDED.label,
    acao_payload = EXCLUDED.acao_payload,
    ativo = TRUE;

-- 6. Atendentes de teste (auth.user) + empresa_membro + usuario_departamento
INSERT INTO auth."user" (id, name, email, "emailVerified", "createdAt", "updatedAt", status,
                         atendente_status, atendente_status_at, atendente_max_paralelos)
VALUES
    ('test-atd-atendimento', 'Atendente Atendimento', 'atendente.atendimento@vsanexus.test', TRUE, NOW(), NOW(), 'active', 'online', NOW(), 5),
    ('test-atd-agendamentos', 'Atendente Agendamentos', 'atendente.agendamentos@vsanexus.test', TRUE, NOW(), NOW(), 'active', 'online', NOW(), 5),
    ('test-atd-exames', 'Atendente Exames', 'atendente.exames@vsanexus.test', TRUE, NOW(), NOW(), 'active', 'online', NOW(), 5),
    ('test-atd-tesouraria', 'Atendente Tesouraria', 'atendente.tesouraria@vsanexus.test', TRUE, NOW(), NOW(), 'active', 'online', NOW(), 5),
    ('test-atd-orcamento', 'Atendente Orcamento', 'atendente.orcamento@vsanexus.test', TRUE, NOW(), NOW(), 'active', 'online', NOW(), 5),
    ('test-atd-rh', 'Atendente RH', 'atendente.rh@vsanexus.test', TRUE, NOW(), NOW(), 'active', 'online', NOW(), 5),
    ('test-atd-ouvidoria', 'Atendente Ouvidoria', 'atendente.ouvidoria@vsanexus.test', TRUE, NOW(), NOW(), 'active', 'online', NOW(), 5)
ON CONFLICT (id) DO UPDATE SET
    atendente_status = 'online',
    atendente_status_at = NOW(),
    "updatedAt" = NOW();

INSERT INTO empresa_membro (empresa_id, user_id, role, is_default)
SELECT 1, id, 'operator', FALSE FROM auth."user" WHERE id LIKE 'test-atd-%'
ON CONFLICT DO NOTHING;

INSERT INTO usuario_departamento (empresa_id, user_id, departamento_id) VALUES
    (1, 'test-atd-atendimento', 3),
    (1, 'test-atd-agendamentos', 5),
    (1, 'test-atd-exames', 7),
    (1, 'test-atd-tesouraria', 2),
    (1, 'test-atd-orcamento', 6),
    (1, 'test-atd-rh', 4),
    (1, 'test-atd-ouvidoria', 1)
ON CONFLICT DO NOTHING;

-- 7. Sequences ajustadas pra continuar acima dos IDs fixos
SELECT setval('departamento_id_seq', GREATEST((SELECT MAX(id) FROM departamento), 100));
SELECT setval('menu_chatbot_id_seq', GREATEST((SELECT MAX(id) FROM menu_chatbot), 100));
SELECT setval('menu_item_id_seq', GREATEST((SELECT MAX(id) FROM menu_item), 100));
SELECT setval('conexao_id_seq', GREATEST((SELECT MAX(id) FROM conexao), 100));
SELECT setval('empresa_id_seq', GREATEST((SELECT MAX(id) FROM empresa), 100));
