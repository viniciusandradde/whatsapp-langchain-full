-- Avisar (ou nao) o cliente quando um atendente assume o atendimento.
--
-- Ate aqui o `POST /atendimentos/{id}/claim` SEMPRE enviava "Voce foi
-- transferido para o atendente *X*" (Sprint E.3), sem opcao. Isso nao serve pro
-- modelo de atendimento em uso na empresa 1018, que e co-piloto: a IA responde
-- e o operador entra e sai da conversa quando quer. Anunciar cada entrada expoe
-- ao cliente uma mecanica interna que nao muda nada pra ele — e com o botao
-- "Atender" no celular, um toque errado virava mensagem enviada.
--
-- Vira config por empresa em vez de remocao: o aviso faz sentido em operacao de
-- fila classica, onde o cliente esperava e passa a falar com uma pessoa.
--
-- DEFAULT FALSE (silencioso) e a mudanca de comportamento pedida. Empresa que
-- quiser o anuncio liga no cadastro. Nao ha empresa em producao dependendo do
-- anuncio: a 1018 nunca teve atendimento em `em_andamento` (zero linhas em
-- 2026-07-30), e a 1 e a propria VSA.

ALTER TABLE empresa
    ADD COLUMN IF NOT EXISTS anuncia_atendente_assumiu BOOLEAN NOT NULL DEFAULT FALSE;

COMMENT ON COLUMN empresa.anuncia_atendente_assumiu IS
    'TRUE envia ao cliente "Voce foi transferido para o atendente X" quando um '
    'operador assume (claim). FALSE (default) assume em silencio. Nao afeta a '
    'transferencia de setor, que anuncia por conta propria.';
