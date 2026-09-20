-- Nome real do arquivo que o OPERADOR mandou.
--
-- A mig 164 guardou o nome do arquivo que o CLIENTE manda (`media_filename`);
-- o lado de saída (mig 146, `response_media_*`) nunca teve o equivalente. O
-- `POST /responder-midia` recebia `arquivo.filename`, passava ao Evolution
-- como `fileName` (o cliente vê o nome certo no WhatsApp) e descartava — e a
-- timeline do painel mostrava "application/pdf" no lugar de "orcamento.pdf".
-- Reportado pelo dono em 2026-09-19.
--
-- Nullable de propósito: nota de voz não tem nome que interesse (o navegador
-- grava "nota-de-voz.webm" e o servidor converte para OGG), e toda row
-- anterior fica NULL e cai no rótulo por tipo, como hoje.

ALTER TABLE message_queue
    ADD COLUMN IF NOT EXISTS response_media_filename TEXT;

COMMENT ON COLUMN message_queue.response_media_filename IS
    'Nome do arquivo enviado pelo operador (anexo do painel/app). NULL = nota de voz ou row antiga; a UI rotula pelo tipo.';
