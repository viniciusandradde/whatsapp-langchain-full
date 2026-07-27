-- 140 — Gemini Flash Lite: troca o slug quebrado e cadastra o 2.5.
--
-- Dois problemas, um deles ATIVO em produção:
--
-- 1. `gemini-3.1-flash-lite-preview` devolve HTTP 404 com a nossa chave:
--
--      "No endpoints available matching your guardrail restrictions and
--       data policy"
--
--    O sufixo `-preview` exige opt-in de compartilhamento de dados em
--    openrouter.ai/settings/privacy. A variante GA
--    `google/gemini-3.1-flash-lite` tem PREÇO IDÊNTICO (0.25/1.50), mesma
--    janela (1M) e as mesmas modalidades — e responde 200 sem mexer em
--    política nenhuma. Testado com a chave de produção.
--
--    Situação em 2026-07-27: o agente 80 (`assistente-luis-fernando`, ligado
--    à conexão 1044) chegou a ficar apontado pro slug quebrado e foi
--    corrigido à mão pro `gemini-2.5-flash` antes de processar mensagem. O
--    agente 1 (`atendimento`) segue apontado pro preview, mas está órfão —
--    nenhuma conexão o referencia. Risco ativo: zero. Risco latente: quem
--    escolher "Gemini 3.1 Flash Lite" no editor hoje pega o slug quebrado,
--    porque o catálogo ainda oferece o `-preview`.
--
-- 2. `gemini-2.5-flash-lite` estava só no CURATED_MODELS como tipo "media",
--    e ausente de `modelo_llm` — por isso não aparecia no select de chat do
--    editor de agente, embora o agente 1 já o use pelo campo legado
--    `modelo`.
--
-- Preços conferidos em openrouter.ai/api/v1/models nesta data.

-- ── 1. Slug GA no lugar do preview ───────────────────────────────────────
-- Sem ON CONFLICT: `nome` não é único isolado, e o UPDATE é idempotente
-- (roda 2x, a segunda não acha linha).
UPDATE modelo_llm
   SET nome = 'gemini-3.1-flash-lite',
       descricao = 'Gemini 3.1 Flash Lite — menor latência, 1M de contexto, '
                   'muito barato (variante GA; a -preview exige opt-in de '
                   'dados na conta OpenRouter e devolve 404 sem ele)',
       updated_at = NOW()
 WHERE provedor = 'google'
   AND nome = 'gemini-3.1-flash-lite-preview';

-- Agentes que já apontavam pro slug quebrado. Sem isto o UPDATE acima
-- deixaria os agentes órfãos: `resolve_agente_runtime` monta
-- `modelo_provedor/modelo_nome` e chamaria um modelo inexistente no catálogo.
UPDATE agente_ia
   SET modelo_nome = 'gemini-3.1-flash-lite',
       updated_at = NOW()
 WHERE modelo_provedor = 'google'
   AND modelo_nome = 'gemini-3.1-flash-lite-preview';

-- Campo legado `modelo` (usado quando provedor/nome estão vazios).
UPDATE agente_ia
   SET modelo = 'google/gemini-3.1-flash-lite',
       updated_at = NOW()
 WHERE modelo = 'google/gemini-3.1-flash-lite-preview';

-- ── 2. Gemini 2.5 Flash Lite no catálogo de chat ─────────────────────────
INSERT INTO modelo_llm
    (empresa_id, provedor, nome, descricao, tipo,
     custo_input_mtok, custo_output_mtok, custo_cache_mtok, janela_contexto)
SELECT NULL, 'google', 'gemini-2.5-flash-lite',
       'Gemini 2.5 Flash Lite — o mais barato da linha 2.5, 1M de contexto, '
       'multimodal (texto/imagem/áudio/vídeo)',
       'chat', 0.10, 0.40, 0.01, 1048576
 WHERE NOT EXISTS (
     SELECT 1 FROM modelo_llm
      WHERE provedor = 'google' AND nome = 'gemini-2.5-flash-lite'
        AND empresa_id IS NULL
 );

-- ── 3. Preço de cache (mig 139 só populou o deepseek) ────────────────────
-- Só entra no FALLBACK: o caminho normal grava `usage.cost` da OpenRouter,
-- e os dois modelos devolvem esse campo (verificado via `create_chat_model`:
-- 2.5-flash-lite cost=9e-07, 3.1-flash-lite cost=2.75e-06).
-- Preenchido mesmo assim pra rede de segurança não mentir se a OpenRouter
-- omitir o custo em alguma chamada.
UPDATE modelo_llm
   SET custo_cache_mtok = 0.025, updated_at = NOW()
 WHERE provedor = 'google' AND nome = 'gemini-3.1-flash-lite'
   AND custo_cache_mtok IS NULL;

UPDATE modelo_llm
   SET custo_cache_mtok = 0.0075, updated_at = NOW()
 WHERE provedor = 'google' AND nome = 'gemini-2.5-flash'
   AND custo_cache_mtok IS NULL;
