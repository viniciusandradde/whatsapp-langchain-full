-- 169: transcrição de áudio para o OPERADOR (independente do agente IA).
--
-- Contexto: a transcrição só existia dentro do preprocess do agente
-- (normalized_input) — conexão em modo manual (default desde a mig 132),
-- whitelist, menu e workflow retornam ANTES do preprocess, então o áudio
-- nunca vira texto pra quem atende pelo painel.
--
-- message_queue.transcricao: texto da nota de voz, visível na timeline.
--   Preenchida pelo botão "Transcrever" do painel (sob demanda) ou pelo
--   worker quando a conexão liga a transcrição automática. NÃO confundir
--   com normalized_input, que é o input montado PARA O AGENTE.
ALTER TABLE message_queue ADD COLUMN IF NOT EXISTS transcricao TEXT;

-- conexao.transcrever_audio_sempre: liga a transcrição automática de todo
-- áudio recebido na conexão, mesmo quando nenhum agente vai responder
-- (modo manual/whitelist/menu). Default OFF: transcrição custa chamada de
-- LLM por áudio — quem quer, liga no painel da conexão.
ALTER TABLE conexao
  ADD COLUMN IF NOT EXISTS transcrever_audio_sempre BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN message_queue.transcricao IS
  'Transcrição da nota de voz para leitura humana no painel (mig 169). Independe do agente.';
COMMENT ON COLUMN conexao.transcrever_audio_sempre IS
  'Transcreve automaticamente todo áudio recebido, mesmo sem agente responder (mig 169).';
