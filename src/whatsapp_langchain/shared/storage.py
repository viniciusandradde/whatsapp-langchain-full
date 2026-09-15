"""Fachada do object storage S3-compatível (mig 183).

ÚNICO lugar do projeto que fala com o bucket (boto3). A mídia do cliente sai do
Postgres e vem pra cá; a mensagem guarda só a referência (`arquivo.uuid`), e o
painel lê por URL assinada temporária. Agnóstico de backend: MinIO (self-host),
AWS S3, Cloudflare R2 — muda só a env (`s3_endpoint_url`/credenciais).

Contrato:
- `storage_ativo()` — o storage está configurado? (bucket + credenciais). Os
  chamadores do fluxo de mídia guardam por aqui e caem no comportamento antigo
  (base64) quando False, então mergear a fundação não muda nada em produção até
  o storage ser configurado.
- `guardar_midia(pool, empresa_id, conteudo, mime_type, original_name)` — sobe
  os bytes e registra o `Arquivo`. Devolve o `Arquivo`.
- `url_assinada(arquivo, ttl)` — URL GET assinada (assinatura local, sem I/O).
- `ler_bytes(arquivo)` — baixa o objeto (worker/agente reprocessam mídia).
- `apagar_midia(pool, arquivo)` — apaga o objeto no bucket E o registro.

boto3 é síncrono; como o app é async, as chamadas de rede rodam em
`asyncio.to_thread` pra não travar o event loop.
"""

from __future__ import annotations

import asyncio
import hashlib
import mimetypes
import uuid as _uuid
from datetime import UTC, datetime
from functools import lru_cache
from typing import TYPE_CHECKING, Any

import structlog

from whatsapp_langchain.shared import arquivo as arquivo_lib
from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.models import Arquivo

if TYPE_CHECKING:
    from psycopg_pool import AsyncConnectionPool

logger = structlog.get_logger()

_DISK = "s3"


class StorageNaoConfigurado(RuntimeError):
    """Levantado quando uma operação de storage roda sem bucket/credenciais."""


# Garante o bucket uma vez por processo. Best-effort: se a credencial de
# produção não tiver permissão de CreateBucket (bucket provisionado por fora),
# o create falha em silêncio e seguimos — o bucket já existe. Sem isto seria
# preciso um container `mc` só pra criar o bucket (e o pull dele pode falhar).
_bucket_garantido = False


def storage_ativo() -> bool:
    """O object storage está configurado o suficiente pra ser usado?"""
    return bool(
        settings.s3_bucket.strip()
        and settings.s3_access_key is not None
        and settings.s3_secret_key is not None
    )


@lru_cache(maxsize=1)
def _client() -> Any:
    """Cliente boto3 S3, criado uma vez. Levanta se o storage não está pronto."""
    if not storage_ativo():
        raise StorageNaoConfigurado(
            "S3 não configurado — defina S3_BUCKET/S3_ACCESS_KEY/S3_SECRET_KEY."
        )
    import boto3
    from botocore.config import Config

    addressing = "path" if settings.s3_use_path_style else "virtual"
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url or None,
        region_name=settings.s3_region,
        aws_access_key_id=settings.s3_access_key.get_secret_value(),  # type: ignore[union-attr]
        aws_secret_access_key=settings.s3_secret_key.get_secret_value(),  # type: ignore[union-attr]
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": addressing},
        ),
    )


def _garantir_bucket(bucket: str) -> None:
    """Cria o bucket se faltar (uma vez por processo, best-effort e síncrono)."""
    global _bucket_garantido
    if _bucket_garantido:
        return
    client = _client()
    try:
        client.head_bucket(Bucket=bucket)
    except Exception:  # noqa: BLE001 — 404/403: tenta criar
        try:
            client.create_bucket(Bucket=bucket)
            logger.info("storage_bucket_criado", bucket=bucket)
        except Exception as exc:  # noqa: BLE001 — já existe / sem permissão → segue
            logger.info(
                "storage_bucket_nao_criado", bucket=bucket, motivo=str(exc)[:120]
            )
    _bucket_garantido = True


def _extensao(mime_type: str | None, original_name: str | None) -> str:
    """Extensão do arquivo — do nome original, senão adivinhada do mime."""
    if original_name and "." in original_name:
        ext = original_name.rsplit(".", 1)[-1].lower()
        if 1 <= len(ext) <= 8 and ext.isalnum():
            return ext
    if mime_type:
        # mime pode vir como 'audio/ogg; codecs=opus' — corta no ';'.
        guessed = mimetypes.guess_extension(mime_type.split(";")[0].strip())
        if guessed:
            return guessed.lstrip(".")
    return "bin"


def gerar_object_key(
    empresa_id: int, mime_type: str | None, original_name: str | None
) -> str:
    """Chave do objeto: empresa/<id>/<ano>/<mes>/<uuid>.<ext>.

    Prefixo por empresa+data facilita expurgo por período e inspeção manual.
    """
    agora = datetime.now(UTC)
    ext = _extensao(mime_type, original_name)
    return f"empresa/{empresa_id}/{agora:%Y/%m}/{_uuid.uuid4().hex}.{ext}"


async def guardar_midia(
    pool: AsyncConnectionPool,
    empresa_id: int,
    conteudo: bytes,
    mime_type: str | None,
    original_name: str | None = None,
) -> Arquivo:
    """Sobe os bytes pro bucket e registra o `Arquivo`. Devolve o `Arquivo`."""
    if not storage_ativo():
        raise StorageNaoConfigurado("guardar_midia chamado sem storage configurado.")
    bucket = settings.s3_bucket
    object_key = gerar_object_key(empresa_id, mime_type, original_name)
    sha256 = hashlib.sha256(conteudo).hexdigest()

    def _put() -> None:
        _garantir_bucket(bucket)
        extra: dict[str, Any] = {}
        if mime_type:
            extra["ContentType"] = mime_type.split(";")[0].strip()
        _client().put_object(Bucket=bucket, Key=object_key, Body=conteudo, **extra)

    await asyncio.to_thread(_put)
    registro = await arquivo_lib.criar_arquivo(
        pool,
        empresa_id=empresa_id,
        disk=_DISK,
        bucket=bucket,
        object_key=object_key,
        mime_type=mime_type,
        size_bytes=len(conteudo),
        original_name=original_name,
        sha256=sha256,
    )
    logger.info(
        "storage_midia_guardada",
        empresa_id=empresa_id,
        object_key=object_key,
        bytes=len(conteudo),
        uuid=registro.uuid,
    )
    return registro


def url_assinada(arquivo: Arquivo, ttl: int | None = None) -> str:
    """URL GET assinada temporária pro objeto (assinatura local, sem rede)."""
    if not storage_ativo():
        raise StorageNaoConfigurado("url_assinada chamado sem storage configurado.")
    return _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": arquivo.bucket, "Key": arquivo.object_key},
        ExpiresIn=ttl or settings.s3_signed_url_ttl,
    )


async def ler_bytes(arquivo: Arquivo) -> bytes:
    """Baixa o objeto do bucket (worker/agente reprocessando mídia)."""
    if not storage_ativo():
        raise StorageNaoConfigurado("ler_bytes chamado sem storage configurado.")

    def _get() -> bytes:
        resp = _client().get_object(Bucket=arquivo.bucket, Key=arquivo.object_key)
        return resp["Body"].read()

    return await asyncio.to_thread(_get)


async def apagar_midia(pool: AsyncConnectionPool, arquivo: Arquivo) -> None:
    """Apaga o objeto no bucket E o registro (usado pela retenção)."""
    if storage_ativo():

        def _del() -> None:
            _client().delete_object(Bucket=arquivo.bucket, Key=arquivo.object_key)

        try:
            await asyncio.to_thread(_del)
        except Exception as exc:  # noqa: BLE001 — objeto já sumido não trava o expurgo
            logger.warning(
                "storage_delete_falhou",
                object_key=arquivo.object_key,
                error=str(exc),
            )
    await arquivo_lib.delete_arquivo(pool, arquivo.uuid)
