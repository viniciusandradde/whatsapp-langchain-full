-- 190: ADR-005 leva B — recursos que custam uma chamada de LLM POR MENSAGEM
-- passam a depender do plano (matriz da ADR §3). Mesmo padrão das migs 177 e
-- 188: chaves booleanas em `plano.features`, lidas por `tem_feature`; plano
-- sem a chave = desligado (errar para o custo baixo).
--
--   transcricao_operador — nota de voz vira texto para o OPERADOR
--                          (`conexao.transcrever_audio_sempre` + botão
--                          "Transcrever" na timeline). Pro/Enterprise.
--   documentos_cliente   — o agente lê PDF/DOCX/XLSX que o cliente manda.
--                          Free não; o agente recebe "[Arquivo recebido …]".
--   imagem_cliente       — o agente descreve imagem (visão). Free não.
--                          Áudio do cliente continua liberado em todo plano.
--   fewshot              — exemplos automáticos (dataset) na mensagem.
--                          Pro/Enterprise.
--   catalogo_completo    — o seletor de modelos mostra os 447 do OpenRouter;
--                          sem a chave, só os recomendados (`modelo_llm`).
--
-- `plano` é catálogo global (fora do FORCE RLS). Idempotente: merge no JSONB.

UPDATE plano
   SET features = coalesce(features, '{}'::jsonb) || '{
        "transcricao_operador": false, "documentos_cliente": false,
        "imagem_cliente": false, "fewshot": false, "catalogo_completo": false}'::jsonb
 WHERE slug = 'free';

UPDATE plano
   SET features = coalesce(features, '{}'::jsonb) || '{
        "transcricao_operador": false, "documentos_cliente": true,
        "imagem_cliente": true, "fewshot": false, "catalogo_completo": false}'::jsonb
 WHERE slug = 'pessoal';

UPDATE plano
   SET features = coalesce(features, '{}'::jsonb) || '{
        "transcricao_operador": true, "documentos_cliente": true,
        "imagem_cliente": true, "fewshot": true, "catalogo_completo": true}'::jsonb
 WHERE slug IN ('pro', 'enterprise');

-- Grandfathering (ADR-005 D3) — levantamento em produção (20/09/2026): a
-- sandbox 999 (Free, de avaliação) tem 8 agentes com `aceita_*` e 522
-- exemplos few-shot; nenhum cliente pagante está fora da matriz. Flags
-- `plano.<chave>` sobrepõem o plano na leitura (`get_plano_info`).
SELECT set_config('app.bypass_rls', 'true', true);

INSERT INTO feature_flag (empresa_id, key, value, descricao)
SELECT 999, k, 'true'::jsonb,
       'ADR-005 D3 — sandbox de avaliação (dataset/few-shot e mídia) — 20/09/2026'
  FROM unnest(ARRAY['plano.documentos_cliente', 'plano.imagem_cliente', 'plano.fewshot']) AS k
 WHERE EXISTS (SELECT 1 FROM empresa WHERE id = 999)
ON CONFLICT (empresa_id, key) DO NOTHING;
