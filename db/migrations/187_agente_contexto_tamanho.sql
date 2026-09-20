-- Tamanho do contexto do agente (ADR-004): Lite 6k … Extended 300k caracteres.
-- Substitui, na UI, a "janela de memória (msgs)" da mig 043 — que nunca chegou
-- ao worker. NULL = legado (TRIM_KEEP_TURNS global), até o agente ser salvo
-- pela tela nova. Sem DEFAULT de propósito: ADD COLUMN com default
-- preencheria os agentes existentes, e o legado tem que continuar NULL.
ALTER TABLE agente_ia
    ADD COLUMN IF NOT EXISTS contexto_tamanho TEXT
    CHECK (contexto_tamanho IS NULL OR contexto_tamanho IN ('lite','regular','medium','large','extended'));
COMMENT ON COLUMN agente_ia.contexto_tamanho IS
    'Tier de contexto (ADR-004). Limita o histórico relido pelo agente em caracteres. NULL = legado.';
