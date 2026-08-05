-- Seed reproduzível da bateria E2E (Sprint K + jornadas de documento).
-- Idempotente — pode rodar múltiplas vezes sem erro.
--
-- TUDO vive na EMPRESA 900. Até 2026-08-05 este arquivo escrevia na empresa 1
-- com `ON CONFLICT (id) DO UPDATE`, ou seja: rodar a bateria renomeava para
-- "VSA Tech (test)" a empresa que o painel de desenvolvimento usa, e reescrevia
-- os agentes dela. Isolar por tenant é o que o produto já faz em produção; não
-- há motivo para o teste ser exceção.
--
-- Os ids fixos (900+) são espelhados em `tests/e2e/conftest.py` (EMPRESA_E2E,
-- SETORES, CONEXAO_*). Mudou aqui, muda lá.
--
-- Cria: empresa 900, 7 deptos, 8 agentes, 1 menu + 8 items, 2 conexões,
-- 7 atendentes test-atd-*, atribuições.

-- 1. Empresa da bateria
INSERT INTO empresa (id, nome, slug, status)
VALUES (900, 'E2E Test', 'e2e-test', 'active')
ON CONFLICT (id) DO UPDATE SET nome = EXCLUDED.nome, status = 'active';

-- 2a. Conexão das jornadas de setor.
--
--     `evolution`, não `twilio_sandbox`: a constraint `conexao_provider_check`
--     do banco de desenvolvimento só aceita `waba` e `evolution` — a migration
--     153 (`drop_twilio_provider`) foi aplicada lá. Um seed com Twilio não
--     entra, e era por isso que a bateria estava vermelha desde junho.
--
--     O `from_number` continua sendo o número do sandbox porque as jornadas de
--     setor postam no webhook do Twilio, que resolve a conexão pelo NÚMERO de
--     destino (`get_conexao_by_from_number`) e não olha o provider.
--
--     O envio segue sem sair: `EVOLUTION_OUTBOUND_MODE=mock` no ambiente de
--     desenvolvimento. É o que impede a bateria de mandar WhatsApp de verdade
--     para os números inventados dos testes.
INSERT INTO conexao (id, empresa_id, provider, from_number, status,
                     default_agent_id, display_name, payload_json)
VALUES (900, 900, 'evolution', '+14155238886', 'active', 'atendimento',
        'Sandbox E2E', '{"instance_name": "e2e-sandbox"}'::jsonb)
ON CONFLICT (id) DO UPDATE SET
    status = 'active',
    provider = EXCLUDED.provider,
    empresa_id = EXCLUDED.empresa_id,
    payload_json = EXCLUDED.payload_json;

-- 2b. Conexão das jornadas de DOCUMENTO.
--     Precisa ser `evolution` porque `get_conexao_by_evolution_instance` filtra
--     por provider — e só o webhook Evolution carrega o nome do arquivo
--     (`documentMessage.fileName`), que é o que a mig 164 introduziu.
--     Ela nunca é usada para ENVIAR: as jornadas de documento afirmam sobre a
--     linha da fila, não sobre a saída.
INSERT INTO conexao (id, empresa_id, provider, from_number, status,
                     default_agent_id, display_name, payload_json, tipo_atendimento)
VALUES (901, 900, 'evolution', '+5500000000901', 'active',
        'atendimento-cliente', 'Evolution E2E',
        '{"instance_name": "e2e-docs"}'::jsonb, 'ia')
ON CONFLICT (id) DO UPDATE SET
    status = 'active',
    empresa_id = EXCLUDED.empresa_id,
    payload_json = EXCLUDED.payload_json,
    tipo_atendimento = 'ia';

-- 3. Departamentos (7 setores) — IDs fixos pros testes referenciarem
INSERT INTO departamento (id, empresa_id, nome, ativo) VALUES
    (900, 900, 'Ouvidoria', TRUE),
    (901, 900, 'Tesouraria', TRUE),
    (902, 900, 'Atendimento ao Cliente', TRUE),
    (903, 900, 'Recrutamento e Seleção', TRUE),
    (904, 900, 'Agendamentos', TRUE),
    (905, 900, 'Orçamento', TRUE),
    (906, 900, 'Exames', TRUE)
ON CONFLICT (id) DO UPDATE SET nome = EXCLUDED.nome, ativo = TRUE;

-- 4. Agentes IA (8 — 1 sem dep_default pra testar fallback)
--    `template_catalog='agente'`: `vsa_tech` é o nome ANTERIOR ao colapso dos
--    templates e só sobrevive por um shim marcado para remoção. Um seed que
--    depende dele quebra no dia em que o shim sair.
--    O modelo é explícito e não herdado do env: um `OPENROUTER_MODEL` morto
--    (aconteceu — o `.env` de dev tinha `x-ai/grok-4.1-fast`, aposentado pela
--    xAI) derrubaria a bateria inteira com 404, e o erro apontaria para
--    qualquer lugar menos a causa.
INSERT INTO agente_ia (
    empresa_id, slug, nome, template_catalog,
    estilo_resposta, ativo, is_default, departamento_default_id,
    aceita_imagem, aceita_audio, aceita_documento,
    modelo_provedor, modelo_nome
) VALUES
    (900, 'atendimento', 'Atendimento ao Cliente', 'agente', 'equilibrado', TRUE, TRUE, 902, TRUE, TRUE, TRUE, 'google', 'gemini-2.5-flash-lite'),
    (900, 'atendimento-cliente', 'Atendimento Cliente VSA', 'agente', 'equilibrado', TRUE, FALSE, NULL, TRUE, TRUE, TRUE, 'google', 'gemini-2.5-flash-lite'),
    (900, 'agendamentos', 'Agendamentos', 'agente', 'equilibrado', TRUE, FALSE, 904, TRUE, TRUE, TRUE, 'google', 'gemini-2.5-flash-lite'),
    (900, 'exames', 'Exames', 'agente', 'equilibrado', TRUE, FALSE, 906, TRUE, TRUE, TRUE, 'google', 'gemini-2.5-flash-lite'),
    (900, 'orcamento', 'Orçamento', 'agente', 'equilibrado', TRUE, FALSE, 905, TRUE, TRUE, TRUE, 'google', 'gemini-2.5-flash-lite'),
    (900, 'ouvidoria', 'Ouvidoria', 'agente', 'equilibrado', TRUE, FALSE, 900, TRUE, TRUE, TRUE, 'google', 'gemini-2.5-flash-lite'),
    (900, 'rh-recrutamento-selecao', 'Recrutamento e Seleção', 'agente', 'equilibrado', TRUE, FALSE, 903, TRUE, TRUE, TRUE, 'google', 'gemini-2.5-flash-lite'),
    (900, 'tesouraria', 'Tesouraria', 'agente', 'equilibrado', TRUE, FALSE, 901, TRUE, TRUE, TRUE, 'google', 'gemini-2.5-flash-lite')
ON CONFLICT (empresa_id, slug) DO UPDATE SET
    departamento_default_id = EXCLUDED.departamento_default_id,
    template_catalog = EXCLUDED.template_catalog,
    aceita_imagem = TRUE,
    aceita_audio = TRUE,
    -- Reposto a cada run: a jornada 6 desliga isto de propósito e precisa
    -- encontrar o valor de volta na execução seguinte.
    aceita_documento = TRUE,
    modelo_provedor = EXCLUDED.modelo_provedor,
    modelo_nome = EXCLUDED.modelo_nome,
    ativo = TRUE;

-- 5. Menu chatbot principal — 1 menu + 8 items raiz com chamar_agente
-- solicitar_nome=false: testes mandam "oi" e esperam menu direto, não captura de nome.
-- `conexao_id = 900` e não NULL: o menu vale SÓ para as jornadas de setor.
-- Menu genérico (`conexao_id IS NULL`) atende toda conexão da empresa, e a
-- triagem roda ANTES do pré-processamento de mídia — as jornadas de documento
-- recebiam a mensagem de boas-vindas e o arquivo nunca chegava ao extrator.
INSERT INTO menu_chatbot (id, empresa_id, conexao_id, nome, ativo, solicitar_nome, mensagem_boas_vindas)
VALUES (900, 900, 900, 'Triagem inicial', TRUE, FALSE,
        'Olá! Sou a IA da VSA Tech. Como posso te ajudar hoje?')
ON CONFLICT (id) DO UPDATE SET
    ativo = TRUE, solicitar_nome = FALSE, conexao_id = EXCLUDED.conexao_id;

-- Garante zero duplicatas — remove items órfãos fora do range esperado
-- antes de fazer UPSERT. Idempotente em re-runs.
DELETE FROM menu_item WHERE menu_id = 900 AND id NOT IN (900,901,902,903,904,905,906,907);

-- Items raiz: ordem 1-8 mapeando direto pros agentes
INSERT INTO menu_item (id, menu_id, parent_id, ordem, label, acao_tipo, acao_payload, ativo) VALUES
    (900, 900, NULL, 1, 'Atendimento ao Cliente', 'chamar_agente',
     '{"agente_slug":"atendimento","mensagem_pre":"Vou te conectar com Atendimento ao Cliente…"}',
     TRUE),
    (901, 900, NULL, 2, 'Atendimento Cliente VSA', 'chamar_agente',
     '{"agente_slug":"atendimento-cliente","mensagem_pre":"Vou te conectar com Atendimento Cliente VSA…"}',
     TRUE),
    (902, 900, NULL, 3, 'Agendamentos', 'chamar_agente',
     '{"agente_slug":"agendamentos","mensagem_pre":"Vou te conectar com Agendamentos…"}',
     TRUE),
    (903, 900, NULL, 4, 'Exames', 'chamar_agente',
     '{"agente_slug":"exames","mensagem_pre":"Vou te conectar com Exames…"}',
     TRUE),
    (904, 900, NULL, 5, 'Orçamento', 'chamar_agente',
     '{"agente_slug":"orcamento","mensagem_pre":"Vou te conectar com Orçamento…"}',
     TRUE),
    (905, 900, NULL, 6, 'Ouvidoria', 'chamar_agente',
     '{"agente_slug":"ouvidoria","mensagem_pre":"Vou te conectar com Ouvidoria…"}',
     TRUE),
    (906, 900, NULL, 7, 'Recrutamento e Seleção', 'chamar_agente',
     '{"agente_slug":"rh-recrutamento-selecao","mensagem_pre":"Vou te conectar com RH…"}',
     TRUE),
    (907, 900, NULL, 8, 'Tesouraria', 'chamar_agente',
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
SELECT 900, id, 'operator', FALSE FROM auth."user" WHERE id LIKE 'test-atd-%'
ON CONFLICT DO NOTHING;

INSERT INTO usuario_departamento (empresa_id, user_id, departamento_id) VALUES
    (900, 'test-atd-atendimento', 902),
    (900, 'test-atd-agendamentos', 904),
    (900, 'test-atd-exames', 906),
    (900, 'test-atd-tesouraria', 901),
    (900, 'test-atd-orcamento', 905),
    (900, 'test-atd-rh', 903),
    (900, 'test-atd-ouvidoria', 900)
ON CONFLICT DO NOTHING;

-- 7. Sequences ajustadas pra continuar acima dos IDs fixos
SELECT setval('departamento_id_seq', GREATEST((SELECT MAX(id) FROM departamento), 1000));
SELECT setval('menu_chatbot_id_seq', GREATEST((SELECT MAX(id) FROM menu_chatbot), 1000));
SELECT setval('menu_item_id_seq', GREATEST((SELECT MAX(id) FROM menu_item), 1000));
SELECT setval('conexao_id_seq', GREATEST((SELECT MAX(id) FROM conexao), 1100));
SELECT setval('empresa_id_seq', GREATEST((SELECT MAX(id) FROM empresa), 1100));
