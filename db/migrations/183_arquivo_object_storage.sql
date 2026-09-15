-- Object storage de mídia: a mídia do cliente sai do Postgres pro bucket.
--
-- Hoje `message_queue.media_url` guarda o arquivo INTEIRO em base64 (medido em
-- produção 2026-09-15: 861 MB de 884 MB da tabela, ~33 MB/dia). Diferente dos
-- checkpoints, esse base64 NÃO é peso morto — é a mídia que o painel exibe.
-- A solução: guardar a mídia num bucket S3-compatível e, na mensagem, só a
-- referência (`arquivo.uuid`). O painel lê por URL assinada temporária.
--
-- Esta migração cria só a tabela de metadados dos arquivos. O fluxo (webhook
-- escreve no bucket, painel lê por URL assinada) entra na fase seguinte, e a
-- referência em `message_queue.media_arquivo_uuid` também. Modelo espelha o
-- `Arquivo` do ZigChat (disk/file_key/mime/size/thumbnail), enxugado.

CREATE TABLE IF NOT EXISTS arquivo (
    uuid UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    empresa_id BIGINT NOT NULL REFERENCES empresa(id) ON DELETE CASCADE,
    -- Backend onde o objeto vive (ex.: 's3'). Abstrai MinIO/S3/R2 — o mesmo
    -- código serve qualquer um, o `disk` diz qual foi usado quando gravou.
    disk TEXT NOT NULL DEFAULT 's3',
    bucket TEXT NOT NULL,
    -- Chave do objeto dentro do bucket (ex.: 'empresa/1/2026/09/<uuid>.ogg').
    object_key TEXT NOT NULL,
    mime_type TEXT,
    size_bytes BIGINT,
    original_name TEXT,
    -- Hash do conteúdo — dedup futura e verificação de integridade.
    sha256 TEXT,
    -- Thumbnail (imagens/vídeo). NULL no v1 — a URL assinada da mídia cheia
    -- basta; a coluna fica pronta pra quando gerarmos miniaturas.
    thumbnail_key TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_arquivo_empresa ON arquivo (empresa_id);
-- Um mesmo objeto não deve ser cadastrado duas vezes na mesma empresa.
CREATE UNIQUE INDEX IF NOT EXISTS uq_arquivo_object
    ON arquivo (empresa_id, disk, bucket, object_key);

-- RLS uniforme (Sprint A.2 — bloco canônico, igual dispositivo_push mig 168).
ALTER TABLE arquivo ENABLE ROW LEVEL SECURITY;
ALTER TABLE arquivo FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS tenant_isolation ON arquivo;
CREATE POLICY tenant_isolation ON arquivo
    USING (_rls_tenant_match(empresa_id)) WITH CHECK (_rls_tenant_match(empresa_id));
