-- Fecha o par do codigo: o Twilio sai do banco depois de sair da aplicacao.
--
-- O Twilio foi marcado como legado na mig 114 (WABA-first) e nesta mesma
-- branch o codigo perdeu o `TwilioClient`, o webhook e o cliente da Content
-- API. Uma conexao `twilio_*` que sobrevivesse aqui seria uma linha que o
-- painel lista, o operador seleciona e o worker nao consegue usar: o envio
-- morre em `OutboundError` na hora em que o cliente espera resposta. Enquanto
-- o CHECK aceitar o valor, nada impede alguem de criar uma.
--
-- Verificado contra o espelho de producao (2026-07-31, saneado da mig 151):
--   1. `conexao`       -> 3 linhas, TODAS `evolution`. Zero `twilio_*`.
--   2. `waba_template` -> 0 linhas. Nenhum `content_sid` a perder.
--   3. `menu_chatbot`  -> 2 menus, um generico e um na conexao 1044
--                         (evolution). Nenhum preso a Twilio.
-- Em producao esta migration e no-op. O DELETE existe pelas bases NOVAS: as
-- migs 009 e 072 semeiam conexoes `twilio_sandbox` (o sandbox +14155238886 da
-- empresa 1 e o da sandbox 999) e elas violariam o CHECK novo.
--
-- Por que um guard antes do DELETE: das 9 FKs que apontam pra `conexao`,
-- quatro sao ON DELETE CASCADE. Tres levam dados derivados que devem morrer
-- junto mesmo (`waba_template`, `usuario_conexao`, `conexao_envio_diario`),
-- mas `menu_chatbot` guarda MENU ESCRITO A MAO — apagar em silencio seria
-- perder trabalho de configuracao no meio de um deploy. Preferimos travar o
-- startup da API e obrigar a decisao explicita.
--
-- Promover esse menu pra generico (conexao_id = NULL) foi considerado e
-- descartado: NULL significa "vale pra TODAS as conexoes da empresa", entao o
-- menu do numero Twilio passaria a atender o numero Evolution — mudanca de
-- comportamento silenciosa, pior que o erro.

DO $$
DECLARE
    n_menus INT;
    n_conexoes INT;
BEGIN
    SELECT count(*) INTO n_menus
      FROM menu_chatbot m
      JOIN conexao c ON c.id = m.conexao_id
     WHERE c.provider IN ('twilio_sandbox', 'twilio_prod');

    IF n_menus > 0 THEN
        RAISE EXCEPTION
            'Migration 153: % menu(s) de chatbot presos a conexoes Twilio. '
            'O DELETE abaixo os apagaria em CASCADE. Reaponte cada menu pra '
            'uma conexao WABA/Evolution (ou apague-o) e rode de novo.',
            n_menus;
    END IF;

    DELETE FROM conexao
     WHERE provider IN ('twilio_sandbox', 'twilio_prod');
    GET DIAGNOSTICS n_conexoes = ROW_COUNT;

    IF n_conexoes > 0 THEN
        RAISE NOTICE 'Migration 153: % conexao(oes) Twilio removida(s).',
            n_conexoes;
    END IF;
END $$;

-- `atendimento` e `message_queue` apontam pra `conexao` com ON DELETE SET
-- NULL desde a mig 129, que guardou um snapshot do canal justamente pra isto:
-- apagar o numero preserva o historico da conversa.

ALTER TABLE conexao DROP CONSTRAINT IF EXISTS conexao_provider_check;
ALTER TABLE conexao
    ADD CONSTRAINT conexao_provider_check
    CHECK (provider IN ('waba', 'evolution'));

COMMENT ON COLUMN conexao.provider IS
    'Canal de saida da conexao. "waba" = Meta Cloud API (Embedded Signup); '
    '"evolution" = Evolution API (Baileys). O Twilio saiu na mig 153 junto '
    'com o codigo que falava com ele.';

-- waba_template nasceu so pra WABA, virou multi-provider na mig 109 pra
-- acomodar a Content API do Twilio, e volta a ser so WABA. O nome fisico
-- continua `waba_template` — renomear quebraria FKs, indices e as permissoes
-- RBAC (`waba_template.read`/`.write`), que e o mesmo motivo dado na 109.
ALTER TABLE waba_template DROP CONSTRAINT IF EXISTS waba_template_provider_check;
ALTER TABLE waba_template
    ADD CONSTRAINT waba_template_provider_check
    CHECK (provider IN ('waba'));

COMMENT ON COLUMN waba_template.provider IS
    'Discrimina o canal do template. Desde a mig 153 so aceita "waba" (Meta '
    'Cloud API, via meta_template_id) — os valores "twilio_*" da mig 109'
    ' sairam com o Twilio.';

-- `content_sid` fica: e coluna sempre NULL hoje (a tabela esta vazia) e as
-- rotas de template a leem por posicao de tupla. Removeria mais risco do que
-- entrega; se for limpar, e numa migration propria, junto do ajuste do SELECT.
COMMENT ON COLUMN waba_template.content_sid IS
    'ContentSid da Content API do Twilio (HX...). ORFA desde a mig 153: nada '
    'escreve mais aqui. Mantida pra nao mexer nas rotas que leem a tupla por '
    'posicao; candidata a DROP numa migration propria.';
