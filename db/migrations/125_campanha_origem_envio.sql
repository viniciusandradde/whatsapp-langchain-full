-- Origem do ENVIO da campanha — distingue disparo via backend (Evolution/WABA)
-- do disparo in-browser pela extensão (WPPConnect na sessão do operador).
-- Campanhas origem_envio='extensao' NÃO são pegas pelo dispatcher/poller do
-- backend (o navegador envia e reporta os acks via /ext/campanha/{id}/report).

ALTER TABLE campanha
    ADD COLUMN IF NOT EXISTS origem_envio TEXT NOT NULL DEFAULT 'backend'
        CHECK (origem_envio IN ('backend', 'extensao'));
