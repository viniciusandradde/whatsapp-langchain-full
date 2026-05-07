-- 062_atendente_status.sql
-- Status real-time do atendente humano + capacidade de atendimentos paralelos.
--
-- Sprint G — paridade ZigChat (`usuario.disponivel`) + capacidade explícita:
--
-- - `atendente_status`: online|ausente|pausa|offline. NULL = nunca logou
--   ou non-atendente (apenas admin sem fila).
-- - `atendente_status_at`: heartbeat client-side (POST /me/heartbeat) atualiza
--   sem mudar status. Worker job marca offline quando NOW()-status_at > 5min.
-- - `atendente_max_paralelos`: limite de atendimentos abertos simultâneos
--   por user (default 5). Endpoint claim valida.
--
-- Index parcial em (atendente_status='online') acelera o roteamento
-- capacity-based (pick_best_atendente — Sprint I).

ALTER TABLE auth."user"
    ADD COLUMN atendente_status TEXT
        CHECK (atendente_status IS NULL OR atendente_status IN
               ('online', 'ausente', 'pausa', 'offline')),
    ADD COLUMN atendente_status_at TIMESTAMPTZ,
    ADD COLUMN atendente_max_paralelos INT NOT NULL DEFAULT 5
        CHECK (atendente_max_paralelos BETWEEN 1 AND 50);

CREATE INDEX idx_user_atendente_status_online
    ON auth."user" (atendente_status)
    WHERE atendente_status = 'online';
