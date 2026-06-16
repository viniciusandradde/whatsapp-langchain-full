-- Disparador (Task 6) — jitter anti-ban + variáveis por destinatário.
--
-- O produto-fonte (Baileys ZDGText.js) usa intervalo ALEATÓRIO entre min e max
-- por destinatário como principal técnica anti-bloqueio — cadência fixa é
-- assinatura de bot. Substituímos o `intervalo_ms` fixo por uma faixa.
--
-- Default 3000–8000ms (≈ 1 msg a cada 3–8s): conservador para WhatsApp
-- não-oficial (Evolution/Baileys), onde volume alto + cadência regular = ban.
-- Campanhas existentes herdam uma faixa derivada do seu intervalo_ms atual.
--
-- `variaveis` JSONB por destinatário permite personalização via CSV
-- (placeholders {{nome}}/{{empresa}} ou [campo]); o dispatcher resolve por linha.

ALTER TABLE campanha
    ADD COLUMN IF NOT EXISTS intervalo_min_ms INT,
    ADD COLUMN IF NOT EXISTS intervalo_max_ms INT;

-- Backfill das campanhas existentes a partir do intervalo_ms fixo.
UPDATE campanha
   SET intervalo_min_ms = GREATEST(intervalo_ms - 200, 100),
       intervalo_max_ms = intervalo_ms + 200
 WHERE intervalo_min_ms IS NULL;

-- Default anti-ban para novas campanhas.
ALTER TABLE campanha
    ALTER COLUMN intervalo_min_ms SET DEFAULT 3000,
    ALTER COLUMN intervalo_max_ms SET DEFAULT 8000;

-- min <= max (defesa em profundidade; a UI também valida).
ALTER TABLE campanha
    DROP CONSTRAINT IF EXISTS chk_campanha_intervalo_valido;
ALTER TABLE campanha
    ADD CONSTRAINT chk_campanha_intervalo_valido
    CHECK (
        intervalo_min_ms IS NULL OR intervalo_max_ms IS NULL
        OR intervalo_min_ms <= intervalo_max_ms
    );

-- Variáveis por destinatário (personalização por CSV).
ALTER TABLE campanha_destinatario
    ADD COLUMN IF NOT EXISTS variaveis JSONB NOT NULL DEFAULT '{}'::jsonb;
