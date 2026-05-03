-- M2.b Evolution API como provider WhatsApp alternativo.
--
-- Relaxa o CHECK de `conexao.provider` pra incluir 'evolution'. As
-- credenciais Evolution-específicas (instance_name) ficam em
-- `conexao.payload_json` (JSONB já existente desde M2).
--
-- Nome da constraint segue a convenção do Postgres
-- (`<table>_<column>_check`). Drop+Add em transação implícita.

ALTER TABLE conexao DROP CONSTRAINT IF EXISTS conexao_provider_check;
ALTER TABLE conexao
    ADD CONSTRAINT conexao_provider_check
    CHECK (provider IN ('twilio_sandbox', 'twilio_prod', 'waba', 'evolution'));
