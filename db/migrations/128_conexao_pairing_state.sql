-- Conexão por código de pareamento (alternativa ao QR) — Evolution.
--
-- O Evolution v2 conecta um número via QR (escanear) OU via pairing code (o
-- user digita um código de 8 chars no WhatsApp). Reusamos a coluna `qr_code`
-- pra guardar o código (é só string) e um estado distinto pra diferenciar da
-- espera por QR. Única mudança de schema: ampliar o CHECK de connection_state.

ALTER TABLE conexao DROP CONSTRAINT IF EXISTS conexao_connection_state_check;
ALTER TABLE conexao
    ADD CONSTRAINT conexao_connection_state_check
    CHECK (connection_state IN (
        'pending', 'qr_pending', 'pairing_code_pending', 'open', 'connecting',
        'disconnected', 'error', 'ready'
    ));
