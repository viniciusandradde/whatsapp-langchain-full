-- Sprint 3 — Paridade ZigChat (Atendimento — protocolo + métricas).
--
-- Documentação: docs/zigchat/depara/03_gap_grande.md
--
-- Adiciona ao atendimento:
--   - protocolo: número de protocolo único por empresa (ex: "1-000123")
--     pra cliente referenciar em contatos posteriores
--   - qtde_resposta_invalida: counter de respostas inválidas no menu
--     (sinaliza UX ruim ou cliente confuso)
--   - iniciado_cliente: TRUE se cliente abriu via inbound, FALSE se foi
--     outbound (campanha, primeiro contato pelo operador)
--   - finalizado_por_user_id: quem fechou o atendimento (operador ou
--     NULL = automático via menu/timeout)
--   - solicitou_encerramento: cliente pediu pra encerrar (CSAT trigger)

ALTER TABLE atendimento
    ADD COLUMN IF NOT EXISTS protocolo TEXT,
    ADD COLUMN IF NOT EXISTS qtde_resposta_invalida INT NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS iniciado_cliente BOOLEAN NOT NULL DEFAULT TRUE,
    ADD COLUMN IF NOT EXISTS finalizado_por_user_id TEXT,
    ADD COLUMN IF NOT EXISTS solicitou_encerramento BOOLEAN NOT NULL DEFAULT FALSE;

-- Sequence única por empresa pra protocolo (formato: "<empresa_id>-<NNNNNN>")
CREATE SEQUENCE IF NOT EXISTS atendimento_protocolo_seq;

-- Trigger pra auto-gerar protocolo no INSERT.
-- Quem fizer INSERT explicitamente passando protocolo (backfill manual) é respeitado.
CREATE OR REPLACE FUNCTION gerar_protocolo_atendimento()
RETURNS trigger AS $$
BEGIN
    IF NEW.protocolo IS NULL THEN
        NEW.protocolo := NEW.empresa_id::text || '-' ||
                         LPAD(nextval('atendimento_protocolo_seq')::text, 6, '0');
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS atendimento_protocolo_trigger ON atendimento;
CREATE TRIGGER atendimento_protocolo_trigger
    BEFORE INSERT ON atendimento
    FOR EACH ROW EXECUTE FUNCTION gerar_protocolo_atendimento();

-- Backfill: gera protocolo pra atendimentos pré-mig
UPDATE atendimento
   SET protocolo = empresa_id::text || '-' ||
                   LPAD(nextval('atendimento_protocolo_seq')::text, 6, '0')
 WHERE protocolo IS NULL;

CREATE INDEX IF NOT EXISTS idx_atendimento_protocolo
    ON atendimento (empresa_id, protocolo) WHERE protocolo IS NOT NULL;
