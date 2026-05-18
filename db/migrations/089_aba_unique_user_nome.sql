-- Sprint Atendimento UX — UNIQUE parcial em (user_id, nome) ativo.
--
-- Garante que cada user não tem 2 abas pessoais ATIVAS com mesmo nome.
-- Permite reuso após soft-delete (ativo=FALSE). Não restringe abas
-- compartilhadas da empresa (user_id IS NULL, comportamento mig 050).
--
-- Idempotente. Antes de aplicar em prod: sem duplicatas hoje (validado).

CREATE UNIQUE INDEX IF NOT EXISTS uq_aba_user_nome_ativo
    ON aba (user_id, nome)
    WHERE ativo AND user_id IS NOT NULL;
