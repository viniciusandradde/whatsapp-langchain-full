-- Midia enviada PELO OPERADOR (audio gravado, foto, documento).
--
-- Ate aqui o operador so mandava texto: `send_outbound_manual` recebe
-- `conteudo: str` e a linha outbound guarda tudo em `response`. O app Android
-- pediu gravar audio e anexar arquivo, e nao havia onde registrar isso.
--
-- Por que colunas novas em vez de reusar `media_url`/`media_type`: essas duas
-- sao do lado INBOUND. Quem renderiza a timeline decide o lado da bolha pela
-- origem do campo — `incoming_message`/`media_url` viram bolha de ENTRADA,
-- `response` vira bolha de SAIDA. Uma foto enviada pelo operador gravada em
-- `media_url` apareceria como se o CLIENTE tivesse mandado.
--
-- Formato do conteudo: data-URL base64, o mesmo que o worker ja usa no inbound
-- (`data:audio/ogg;base64,...`). Nao e a escolha ideal — a linha fica com
-- megabytes e `/mensagens` devolve tudo inline — mas e o formato que o
-- renderizador do painel e do app ja entendem, e inventar armazenamento
-- separado agora criaria dois caminhos de midia pra manter.

ALTER TABLE message_queue
    ADD COLUMN IF NOT EXISTS response_media_url TEXT;

ALTER TABLE message_queue
    ADD COLUMN IF NOT EXISTS response_media_type TEXT;

COMMENT ON COLUMN message_queue.response_media_url IS
    'Midia enviada pelo operador, como data-URL base64. Contraparte outbound '
    'de media_url (que e inbound). NULL na maioria das linhas.';

COMMENT ON COLUMN message_queue.response_media_type IS
    'MIME da midia outbound (audio/ogg, image/jpeg, application/pdf...). '
    'Decide se a bolha virou player, imagem ou rotulo de anexo.';
