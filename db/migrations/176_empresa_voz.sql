-- 176: voz do agente — resposta em ÁUDIO quando o cliente mandou áudio.
--
-- Contexto: cliente do Luis pediu "fala pra ela mandar áudio também". O
-- agente só enviava texto. Quem fala recebe fala; quem escreve recebe
-- texto — o gatilho no worker exige que a mensagem inbound seja áudio.
--
-- Default OFF pelo mesmo motivo da transcrição (mig 169): cada resposta
-- falada custa uma chamada de LLM (TTS via OpenRouter). Liga-se por
-- empresa, manualmente, no cadastro — sem depender do módulo de planos.
--
-- Só Evolution envia nota de voz (send_audio); em conexão WABA/Twilio o
-- recurso simplesmente não dispara (duck-typing no worker).

ALTER TABLE empresa
    ADD COLUMN IF NOT EXISTS voz_ativa BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS voz_nome TEXT NOT NULL DEFAULT 'alloy',
    ADD COLUMN IF NOT EXISTS voz_estilo TEXT NOT NULL DEFAULT '';

COMMENT ON COLUMN empresa.voz_ativa IS
    'Quando true, o agente responde em nota de voz (OGG/Opus) se o cliente '
    'mandou áudio e a conexão suporta (Evolution). Custa uma chamada de TTS '
    'por resposta — por isso é opt-in por empresa (mig 176).';
COMMENT ON COLUMN empresa.voz_nome IS
    'Voz do TTS (openai/gpt-audio-mini): alloy, ash, ballad, coral, echo, '
    'sage, shimmer ou verse. Fonte única do catálogo: shared/voz.py::VOZES.';
COMMENT ON COLUMN empresa.voz_estilo IS
    'Instruções de estilo faladas, em texto livre (ex.: "fale com calma, tom '
    'acolhedor"). Entra no system prompt do sintetizador; vazio = neutro.';
