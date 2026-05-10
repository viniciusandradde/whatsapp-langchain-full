-- Sprint X — Módulo NPS de Atendimento.
--
-- Captura automática da nota 0-10 que o cliente envia em resposta à pesquisa
-- de satisfação disparada ao fechar o atendimento (worker/processor.py
-- send_csat_survey). Comentário textual coletado como follow-up opcional.
--
-- Cálculo NPS clássico: %promotores (9-10) − %detratores (0-6).

CREATE TABLE IF NOT EXISTS atendimento_avaliacao (
    id SERIAL PRIMARY KEY,
    atendimento_id BIGINT NOT NULL UNIQUE
        REFERENCES atendimento(id) ON DELETE CASCADE,
    empresa_id BIGINT NOT NULL,
    cliente_id BIGINT REFERENCES cliente(id) ON DELETE SET NULL,
    departamento_id INT REFERENCES departamento(id) ON DELETE SET NULL,
    -- snapshot do operador que estava atribuído quando o close aconteceu
    -- (pode ser NULL se o atendimento foi fechado pela IA/sem atribuição)
    assigned_to_user_id TEXT,
    nota SMALLINT NOT NULL CHECK (nota BETWEEN 0 AND 10),
    comentario TEXT,
    categoria TEXT NOT NULL CHECK (categoria IN ('promotor','neutro','detrator')),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_avaliacao_emp_dt
    ON atendimento_avaliacao (empresa_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_avaliacao_dept
    ON atendimento_avaliacao (departamento_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_avaliacao_user
    ON atendimento_avaliacao (assigned_to_user_id, created_at DESC);

-- Flags de captura: setadas quando worker dispara CSAT, lidas quando cliente
-- responde. Janela de 24h pra nota e 60s pra comentário (manuseado em código).
ALTER TABLE atendimento
    ADD COLUMN IF NOT EXISTS aguardando_avaliacao_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS aguardando_comentario_at TIMESTAMPTZ;

-- Force escala 0-10 (NPS clássico) em todos os menu_items pesquisa_csat
-- ativos. Override do default 1-5 herdado da config antiga.
UPDATE menu_item SET nota_min = 0, nota_max = 10
 WHERE acao_tipo = 'pesquisa_csat';
