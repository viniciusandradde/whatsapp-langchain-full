-- Campanha agendada — status 'scheduled' + índice pro poller.
-- scheduled_at já existia (mig 051) mas era ignorado; agora um poller no
-- boot da API dispara campanhas 'scheduled' cujo scheduled_at já passou.

ALTER TABLE campanha DROP CONSTRAINT IF EXISTS campanha_status_check;
ALTER TABLE campanha
    ADD CONSTRAINT campanha_status_check
    CHECK (status IN ('draft', 'scheduled', 'running', 'done', 'partial', 'aborted'));

-- Poller seleciona scheduled vencidas por scheduled_at.
CREATE INDEX IF NOT EXISTS idx_campanha_scheduled_due
    ON campanha (scheduled_at)
    WHERE status = 'scheduled';
