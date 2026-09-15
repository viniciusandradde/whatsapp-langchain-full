-- Fase B do object storage: a mensagem passa a referenciar o arquivo no bucket
-- em vez de carregar o base64 em `media_url`.
--
-- Quando o storage está ligado (`storage_ativo()`), o webhook sobe a mídia pro
-- bucket (tabela `arquivo`, mig 183) e grava aqui só o `uuid`; `media_url` fica
-- NULL. Com o storage desligado, nada muda: a mídia continua em base64 em
-- `media_url` e esta coluna fica NULL — os dois caminhos convivem, então a
-- transição é incremental e reversível.

ALTER TABLE message_queue
    ADD COLUMN IF NOT EXISTS media_arquivo_uuid UUID;

COMMENT ON COLUMN message_queue.media_arquivo_uuid IS
    'Referência ao objeto no storage (arquivo.uuid). Preenchido quando a mídia '
    'foi pro bucket; nesse caso media_url fica NULL. Mutuamente exclusivo com '
    'o base64 em media_url (fluxo antigo).';
