-- Desacopla atendimento da conexão (persistência estilo ZigChat).
--
-- Antes: atendimento.conexao_id NOT NULL + FK ON DELETE RESTRICT → pra apagar um
-- número era obrigatório apagar todos os atendimentos dele (perda de histórico).
--
-- Agora: conexao_id nullable + FK ON DELETE SET NULL, e o atendimento guarda um
-- SNAPSHOT do canal (nome/número/provider) gravado na abertura. Apagar a conexão
-- preserva o histórico — os reads preferem o dado vivo e caem no snapshot quando
-- a conexão sumiu.

-- 1) Snapshot do canal (nomes batem com os aliases que historico.py já emite).
ALTER TABLE atendimento
    ADD COLUMN IF NOT EXISTS conexao_nome TEXT,
    ADD COLUMN IF NOT EXISTS conexao_numero TEXT,
    ADD COLUMN IF NOT EXISTS conexao_provider TEXT;

-- 2) conexao_id nullable + FK RESTRICT → SET NULL.
ALTER TABLE atendimento ALTER COLUMN conexao_id DROP NOT NULL;

-- Dropa QUALQUER FK em (atendimento, conexao_id), independente do nome, pra não
-- deixar a RESTRICT antiga viva caso o nome divirja do default.
DO $$
DECLARE
    fk_name TEXT;
BEGIN
    FOR fk_name IN
        SELECT conname FROM pg_constraint
         WHERE conrelid = 'atendimento'::regclass
           AND contype = 'f'
           AND conkey = (
               SELECT array_agg(attnum)
                 FROM pg_attribute
                WHERE attrelid = 'atendimento'::regclass
                  AND attname = 'conexao_id'
           )
    LOOP
        EXECUTE format('ALTER TABLE atendimento DROP CONSTRAINT %I', fk_name);
    END LOOP;
END $$;

ALTER TABLE atendimento
    ADD CONSTRAINT atendimento_conexao_id_fkey
    FOREIGN KEY (conexao_id) REFERENCES conexao(id) ON DELETE SET NULL;

-- 3) Backfill dos snapshots a partir do dado vivo (idempotente: só onde NULL).
UPDATE atendimento a
   SET conexao_nome     = cx.display_name,
       conexao_numero   = cx.from_number,
       conexao_provider = cx.provider
  FROM conexao cx
 WHERE cx.id = a.conexao_id
   AND a.conexao_nome IS NULL;

-- Nota: o índice único parcial (empresa_id, cliente_id, conexao_id) WHERE
-- status IN ('aguardando','em_andamento') (mig 010) não muda — NULLs são
-- distintos no unique, então um atendimento aberto cuja conexão foi apagada
-- (conexao_id → NULL) sai da garantia "1 aberto por canal" (aceitável: vira
-- histórico read-only).
