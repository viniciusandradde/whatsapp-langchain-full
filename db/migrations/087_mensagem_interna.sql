-- Sprint Atendimento UX (1.3) — Notas internas na timeline da conversa.
--
-- Inspirado em ZigChat `AtendimentoMensagem.interna`. Atendente pode
-- escrever notas que ficam na timeline ao lado das msgs reais, MAS
-- visíveis só pra equipe — NUNCA enviadas pro cliente.
--
-- Mensagens no Nexus vivem em `message_queue` (mig 001) — mesma tabela
-- pra fila inbound e histórico outbound. Adicionar 2 colunas lá.
--
-- Worker filtra `interna=true` no outbound send pra garantir que nunca
-- vaza pro provider Twilio/Evolution.

ALTER TABLE message_queue
    ADD COLUMN IF NOT EXISTS interna BOOLEAN NOT NULL DEFAULT FALSE;

ALTER TABLE message_queue
    ADD COLUMN IF NOT EXISTS criado_por_user_id TEXT;

CREATE INDEX IF NOT EXISTS idx_message_queue_interna
    ON message_queue (atendimento_id, interna) WHERE interna;
