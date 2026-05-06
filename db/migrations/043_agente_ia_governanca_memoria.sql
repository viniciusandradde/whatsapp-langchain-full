-- Sprint 2 — Paridade ZigChat (governança custo + memória configurável).
--
-- Documentação: docs/zigchat/depara/03_gap_grande.md (na branch feat/webscap)
--
-- Adiciona ao agente_ia:
--   - modelo_provedor + modelo_nome (split de modelo único — ex: "google/gemini-2.5-flash"
--     vira modelo_provedor="google" + modelo_nome="gemini-2.5-flash")
--   - tipo_memoria: configura estratégia LangGraph store (window/buffer/summary/none)
--   - janela_memoria: N mensagens anteriores quando tipo=window
--   - timeout_minutos: TTL conversa idle
--   - acao_limite_menu_id: FK pra menu_chatbot — quando agente atinge limite custo,
--     redireciona cliente pro menu específico (governança)
--
-- Backfill idempotente: split do modelo único existente em modelo_provedor + modelo_nome.

ALTER TABLE agente_ia
    ADD COLUMN IF NOT EXISTS modelo_provedor TEXT,
    ADD COLUMN IF NOT EXISTS modelo_nome TEXT,
    ADD COLUMN IF NOT EXISTS tipo_memoria TEXT NOT NULL DEFAULT 'window'
        CHECK (tipo_memoria IN ('buffer', 'window', 'summary', 'none')),
    ADD COLUMN IF NOT EXISTS janela_memoria INT,
    ADD COLUMN IF NOT EXISTS timeout_minutos INT,
    ADD COLUMN IF NOT EXISTS acao_limite_menu_id BIGINT;

-- FK pra menu_chatbot (definida depois pra evitar dep circular)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints
         WHERE constraint_name = 'fk_agente_ia_acao_limite_menu'
    ) THEN
        ALTER TABLE agente_ia
            ADD CONSTRAINT fk_agente_ia_acao_limite_menu
            FOREIGN KEY (acao_limite_menu_id)
            REFERENCES menu_chatbot(id) ON DELETE SET NULL;
    END IF;
END $$;

-- Backfill: split modelo único → provedor + nome.
-- Idempotente: só atualiza rows onde provedor/nome ainda estão NULL.
UPDATE agente_ia
   SET modelo_provedor = SPLIT_PART(modelo, '/', 1),
       modelo_nome     = SPLIT_PART(modelo, '/', 2)
 WHERE modelo IS NOT NULL
   AND POSITION('/' IN modelo) > 0
   AND modelo_provedor IS NULL
   AND modelo_nome IS NULL;

-- Marca a coluna `modelo` como deprecated.
COMMENT ON COLUMN agente_ia.modelo IS
    'DEPRECATED — usar modelo_provedor + modelo_nome (mig 043). Removido em mig futura.';
