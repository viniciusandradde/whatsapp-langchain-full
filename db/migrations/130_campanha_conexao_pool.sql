-- Disparo com rotação de números — pool de conexões por campanha (anti-ban).
--
-- Antes: campanha.conexao_id = UMA conexão. Agora `conexao_ids` é um pool; o
-- dispatcher alterna (round-robin por mensagem) entre os números, respeitando o
-- teto diário/aquecimento (mig 126) de CADA um → espalha o volume e cada número
-- aquece sozinho. `conexao_id` continua (compat + reads atuais); quando o pool
-- tem 1, é o comportamento single de sempre.

ALTER TABLE campanha
    ADD COLUMN IF NOT EXISTS conexao_ids BIGINT[];
