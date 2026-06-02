-- White-label por empresa: logo + nome de marca + cores.
--
-- Cada empresa que contrata o sistema pode subir a própria identidade visual,
-- exibida no topo do sidebar (substitui o "Chat Nexus" + /vsa-logo.png padrão).
-- Espelha o ZigChat (Empresa.logo + tema) e excede com cores por tenant.
--
-- logo_path: caminho relativo servido como estático (/uploads/logos/{id}.png).
-- nome_exibicao: marca mostrada ao lado da logo (NULL = usa `nome`).
-- cor_primaria/secundaria: HEX (#RRGGBB) injetadas como CSS vars no front.

ALTER TABLE empresa
    ADD COLUMN IF NOT EXISTS logo_path TEXT,
    ADD COLUMN IF NOT EXISTS nome_exibicao TEXT,
    ADD COLUMN IF NOT EXISTS cor_primaria TEXT,
    ADD COLUMN IF NOT EXISTS cor_secundaria TEXT;
