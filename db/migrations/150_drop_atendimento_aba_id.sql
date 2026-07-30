-- Remove `atendimento.aba_id` — a pinagem manual que nunca teve tela.
--
-- A mig 085 acrescentou esta coluna para "pinar" conversa a conversa numa aba
-- pessoal. **Nenhuma tela chegou a oferecer isso**: `attachAtendimentoAbaAction`
-- existia no frontend sem nenhum chamador, e em producao havia 6 abas criadas e
-- ZERO conversas dentro.
--
-- Mesmo com o botao o modelo nao se sustentaria: cada nova conversa do mesmo
-- cliente nasceria fora da pasta, e o operador teria que re-pinar para sempre.
-- Por isso a aba virou FILTRO SALVO POR CLIENTE (`aba.filtro->cliente_tags`) —
-- a conversa entra sozinha, e a proxima tambem.
--
-- Havia tambem um defeito de modelagem: `aba_id` e UMA coluna na linha do
-- atendimento, mas abas sao PESSOAIS (`aba.user_id`). Dois operadores pinando a
-- mesma conversa se sobrescreveriam sem aviso.
--
-- Seguro remover: a listagem nao le mais esta coluna desde que a aba virou
-- filtro, e nada mais depende dela.

ALTER TABLE atendimento DROP COLUMN IF EXISTS aba_id;
