-- Campanha com mídia (foto) — disparo em massa com imagem + legenda.
-- O texto da campanha (`mensagem`) vira a LEGENDA quando há mídia.
-- MVP: imagem via Evolution (sendMedia). Vídeo/documento ficam suportados no
-- schema (media_tipo) mas a UI expõe imagem por ora.

ALTER TABLE campanha
    ADD COLUMN IF NOT EXISTS media_url TEXT,
    ADD COLUMN IF NOT EXISTS media_tipo TEXT
        CHECK (media_tipo IS NULL OR media_tipo IN ('image', 'video', 'document'));
