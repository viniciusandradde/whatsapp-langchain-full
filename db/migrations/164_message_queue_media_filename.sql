-- Nome real do arquivo que o cliente mandou.
--
-- O `documentMessage.fileName` do Evolution e o `document.filename` do WABA
-- sempre vieram no payload e eram descartados no parser. Sem eles, o worker
-- adivinhava a extensão pelo mime — e a adivinhação mandava planilha para
-- `doc.bin`, que `file_extractor.detect_kind` recusa. Foi o defeito do
-- atendimento 1018-000664: dois documentos no mesmo segundo, o `.docx` lido e o
-- `.doc` recusado, com o cliente recebendo "estamos com dificuldades em
-- processar imagens/audio" depois de 5 tentativas.
--
-- O nome serve a duas coisas: escolher o parser certo (extensão é mais
-- confiável que mime) e citar o arquivo na resposta quando não dá para lê-lo
-- — "recebi o seu orcamento.pdf" em vez de uma desculpa genérica.
--
-- Nullable de propósito: Twilio não manda nome (legado desde a mig 114), e
-- toda row anterior a esta migration fica NULL e cai na inferência por mime.

ALTER TABLE message_queue
    ADD COLUMN IF NOT EXISTS media_filename TEXT;

COMMENT ON COLUMN message_queue.media_filename IS
    'Nome do arquivo informado pelo provedor (Evolution fileName / WABA filename). NULL = inferir do mime.';
