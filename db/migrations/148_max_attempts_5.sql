-- Mais tentativas de envio: 3 -> 5.
--
-- Medido na empresa 1018 entre 20 e 30/07: **13 falhas de envio em 1.658
-- respostas (~0,8%)**, todas `EvolutionSendError`. Das 13, 6 se recuperaram no
-- retry e **7 esgotaram as 3 tentativas** — nessas o cliente ficou sem nenhuma
-- resposta, em silencio: ninguem e avisado, e so aparece se alguem abrir aquela
-- conversa no painel.
--
-- Descartado com dados, nao por suposicao:
--   - numero invalido: os 4 numeros que falharam existem no WhatsApp (testado
--     em /chat/whatsappNumbers);
--   - servidor fora do ar: nas janelas de falha havia envios OK no mesmo minuto
--     e para o mesmo numero;
--   - rajada / limite de taxa: a falha e ate um pouco MAIS comum quando os
--     envios estao distantes (1,1%) do que em sequencia (0,8%).
-- Sobra instabilidade aleatoria do provedor, na casa de 1%.
--
-- Com falha independente de ~1%, 3 tentativas deixam passar 1 em 1e6 por
-- mensagem; o que se ve nos dados e pior que isso, entao as falhas nao sao
-- totalmente independentes (janelas curtas de instabilidade). Duas tentativas a
-- mais alongam a janela coberta de ~15s (5+10) para ~60s (5+10+15+20), que
-- cobre o padrao observado sem risco: o backoff e `attempts * 5s`, e mensagem
-- que falha nao ocupa worker enquanto espera.
--
-- Muda o DEFAULT DA COLUNA porque e ele que governa: o INSERT de
-- `enqueue_or_buffer` nao lista `max_attempts`, e `mark_failed` le o valor DA
-- LINHA. Mexer so em `MAX_ATTEMPTS` do env nao teria efeito nenhum.

ALTER TABLE message_queue ALTER COLUMN max_attempts SET DEFAULT 5;

COMMENT ON COLUMN message_queue.max_attempts IS
    'Tentativas antes de desistir. Default 5 desde a mig 148 (era 3): ~1% de '
    'falha aleatoria no envio Evolution fazia 7 de 13 mensagens morrerem em '
    'silencio. Backoff e attempts*5s, entao 5 tentativas cobrem ~60s.';

-- Linhas ainda na fila herdam o teto novo. Sem isto, o que ja esta enfileirado
-- continuaria desistindo em 3 e a mudanca so valeria pro trafego futuro.
UPDATE message_queue
   SET max_attempts = 5
 WHERE status IN ('queued', 'processing')
   AND max_attempts = 3;
