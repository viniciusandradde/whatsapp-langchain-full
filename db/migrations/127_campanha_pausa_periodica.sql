-- Disparador (anti-ban) — pausa longa periódica na campanha (descanso).
--
-- Best-practice (docs/DISPARO_MASSA_BEST_PRACTICES.md item 4): a cada N envios,
-- pausar 10-15 min reduz o sinal de spam num número não-oficial. Hoje o
-- dispatcher só tem jitter por mensagem; estas colunas dão o descanso periódico.
--
--   pausa_a_cada    — pausa após cada N envios (0 = desligado).
--   pausa_segundos  — duração da pausa em segundos.
--
-- Default 0 (desligado) pra não mudar o comportamento de campanhas existentes;
-- a UI sugere valores anti-ban (ex.: 50 envios → 600s) em campanhas novas.

ALTER TABLE campanha
    ADD COLUMN IF NOT EXISTS pausa_a_cada INT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS pausa_segundos INT NOT NULL DEFAULT 0;

ALTER TABLE campanha
    DROP CONSTRAINT IF EXISTS chk_campanha_pausa_nao_negativa;
ALTER TABLE campanha
    ADD CONSTRAINT chk_campanha_pausa_nao_negativa
    CHECK (pausa_a_cada >= 0 AND pausa_segundos >= 0);
