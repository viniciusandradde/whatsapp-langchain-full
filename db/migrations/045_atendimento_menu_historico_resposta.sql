-- Sprint 3 — Paridade ZigChat (observabilidade do menu).
--
-- Documentação: docs/zigchat/depara/03_gap_grande.md
--
-- Adiciona ao atendimento_menu_historico:
--   - nanoid: identificador anti-guess pra exposição externa (URLs públicas)
--   - resposta: texto cru que o cliente respondeu (debug + análise UX)
--
-- Mantém id BIGSERIAL como PK (performance index). nanoid é coluna paralela
-- pra exposição segura externa.

ALTER TABLE atendimento_menu_historico
    ADD COLUMN IF NOT EXISTS nanoid TEXT,
    ADD COLUMN IF NOT EXISTS resposta TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS uq_atendimento_menu_historico_nanoid
    ON atendimento_menu_historico (nanoid)
    WHERE nanoid IS NOT NULL;
