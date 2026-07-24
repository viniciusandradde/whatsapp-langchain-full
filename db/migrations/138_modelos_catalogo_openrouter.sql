-- Catálogo de modelos LLM — curadoria OpenRouter (jul/2026).
--
-- 1) CORRIGE 2 slugs globais que estavam com traço no lugar de ponto e por
--    isso davam 404 no OpenRouter (o runtime monta o id como "provedor/nome"):
--      anthropic/claude-haiku-4-5  → anthropic/claude-haiku-4.5
--      anthropic/claude-sonnet-4-6 → anthropic/claude-sonnet-4.6
-- 2) ADICIONA modelos baratos/curados pra aparecerem em TODOS os selects
--    (criar/editar agente, teste A/B, catálogo /models). `nome` concatenado
--    com `provedor` = id EXATO do OpenRouter (validado contra o catálogo
--    público em 2026-07-24). Custos em USD por 1M tokens (pricing OpenRouter).
--    Modelos globais: empresa_id NULL.

-- ---- 1) Fix dos slugs Anthropic (só linhas globais) ----
UPDATE modelo_llm SET nome = 'claude-haiku-4.5', updated_at = NOW()
 WHERE empresa_id IS NULL AND provedor = 'anthropic' AND nome = 'claude-haiku-4-5';

UPDATE modelo_llm SET nome = 'claude-sonnet-4.6', updated_at = NOW()
 WHERE empresa_id IS NULL AND provedor = 'anthropic' AND nome = 'claude-sonnet-4-6';

UPDATE modelo_llm SET nome = 'claude-opus-4.7', updated_at = NOW()
 WHERE empresa_id IS NULL AND provedor = 'anthropic' AND nome = 'claude-opus-4-7';

-- ---- 2) Novos modelos globais (chat) ----
INSERT INTO modelo_llm
    (empresa_id, provedor, nome, descricao, tipo, custo_input_mtok, custo_output_mtok, janela_contexto)
VALUES
    (NULL, 'google', 'gemini-3.1-flash-lite-preview',
     'Gemini 3.1 Flash Lite — menor latência, 1M de contexto, muito barato',
     'chat', 0.25, 1.50, 1048576),
    (NULL, 'deepseek', 'deepseek-v3.2',
     'DeepSeek V3.2 — custo por token dos mais baixos, bom pra volume alto',
     'chat', 0.27, 0.40, 163840),
    (NULL, 'z-ai', 'glm-4.5-air',
     'GLM 4.5 Air — baixo custo, boa qualidade conversacional',
     'chat', 0.13, 0.85, 131072),
    (NULL, 'z-ai', 'glm-4.7-flash',
     'GLM 4.7 Flash — baixíssimo custo, rápido pra chat de alto volume',
     'chat', 0.06, 0.40, 202752),
    (NULL, 'tencent', 'hy3-preview',
     'Tencent HY3 Preview — custo mínimo, contexto 256k',
     'chat', 0.06, 0.21, 262144),
    -- ---- Visão (imagens enviadas no WhatsApp) ----
    (NULL, 'qwen', 'qwen2.5-vl-72b-instruct',
     'Qwen2.5 VL 72B — entende imagens/fotos enviadas pelo cliente',
     'imagem', 0.80, 1.00, 128000),
    (NULL, 'qwen', 'qwen3-vl-30b-a3b-instruct',
     'Qwen3 VL 30B — visão, geração mais nova e mais barata',
     'imagem', 0.15, 0.60, 262144)
ON CONFLICT DO NOTHING;
