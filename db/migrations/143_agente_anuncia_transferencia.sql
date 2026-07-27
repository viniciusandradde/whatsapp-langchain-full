-- 143 — `agente_ia.anuncia_transferencia`: controla a mensagem de setor.
--
-- Ao transferir, `transfer_to_human` manda uma mensagem oficial ao cliente:
--
--   "Seu atendimento foi transferido para o departamento de *Atendimento*.
--    Em breve um atendente dará continuidade. Protocolo: 1018-000499.
--    Caso deseje finalizar o atendimento digite: *encerrar atendimento*"
--
-- Faz sentido em operação de call center. Não faz num assistente pessoal de
-- professor: ali o cliente deve ler só a frase de acolhimento do próprio
-- agente ("vou encaminhar ao Luis Fernando"), sem vocabulário corporativo de
-- departamento.
--
-- Default TRUE preserva o comportamento de todos os agentes existentes — só
-- quem desmarcar no painel deixa de anunciar.
--
-- Efeito colateral de desligar, aceito conscientemente: some junto o número
-- do protocolo e a dica "digite *encerrar atendimento*". A mecânica de
-- departamento (roteamento, fila, auto-claim) continua igual — o que muda é
-- só o que o cliente lê.

ALTER TABLE agente_ia
    ADD COLUMN IF NOT EXISTS anuncia_transferencia BOOLEAN NOT NULL DEFAULT TRUE;

COMMENT ON COLUMN agente_ia.anuncia_transferencia IS
    'Quando FALSE, transfer_to_human nao envia a mensagem de sistema citando '
    'o departamento. A transferencia acontece igual; muda so o que o cliente le.';

-- Agente 80 (assistente-luis-fernando, empresa 1018): decisão do dono em
-- 2026-07-27 — "não vamos mais usar setor para o agente do Luis".
UPDATE agente_ia
   SET anuncia_transferencia = FALSE, updated_at = NOW()
 WHERE id = 80 AND slug = 'assistente-luis-fernando';
