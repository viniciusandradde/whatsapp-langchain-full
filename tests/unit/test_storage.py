"""Fachada do object storage (mig 183) — comportamento sem tocar num bucket real.

boto3 é mockado; a prova de que sobe/assina/apaga de verdade contra o MinIO
está no smoke do dev. Aqui travamos o contrato: gate `storage_ativo`, formato
da object_key, e que `guardar_midia` calcula sha256/tamanho e registra o
`Arquivo`.
"""

from __future__ import annotations

import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from whatsapp_langchain.shared import storage
from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.models import Arquivo

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _storage_config(monkeypatch):
    """Configura o storage e zera o cache do cliente boto3 entre testes."""
    from pydantic import SecretStr

    monkeypatch.setattr(settings, "s3_bucket", "test-bucket", raising=False)
    monkeypatch.setattr(settings, "s3_access_key", SecretStr("k"), raising=False)
    monkeypatch.setattr(settings, "s3_secret_key", SecretStr("s"), raising=False)
    monkeypatch.setattr(settings, "s3_endpoint_url", "http://minio:9000", raising=False)
    storage._client.cache_clear()
    storage._bucket_garantido = False
    yield
    storage._bucket_garantido = False
    # Alguns testes trocam `storage._client` por um lambda (monkeypatch desfaz
    # depois deste teardown), então checa antes de limpar o cache.
    if hasattr(storage._client, "cache_clear"):
        storage._client.cache_clear()


class TestStorageAtivo:
    def test_ativo_com_bucket_e_creds(self):
        assert storage.storage_ativo() is True

    def test_inativo_sem_bucket(self, monkeypatch):
        monkeypatch.setattr(settings, "s3_bucket", "", raising=False)
        assert storage.storage_ativo() is False

    def test_inativo_sem_credencial(self, monkeypatch):
        monkeypatch.setattr(settings, "s3_secret_key", None, raising=False)
        assert storage.storage_ativo() is False


class TestObjectKey:
    def test_formato_com_empresa_data_uuid_ext(self):
        # audio/ogg -> mimetypes devolve .oga em alguns sistemas; a extensão é
        # cosmética (mime_type é a fonte da verdade), o que importa é o formato.
        key = storage.gerar_object_key(42, "audio/ogg; codecs=opus", None)
        assert re.match(r"^empresa/42/\d{4}/\d{2}/[0-9a-f]{32}\.(ogg|oga)$", key), key

    def test_extensao_do_nome_original(self):
        key = storage.gerar_object_key(1, "application/octet-stream", "laudo.pdf")
        assert key.endswith(".pdf")

    def test_extensao_fallback_bin(self):
        key = storage.gerar_object_key(1, None, None)
        assert key.endswith(".bin")


class TestGuardarMidia:
    async def test_sobe_e_registra_com_sha256_e_tamanho(self, monkeypatch):
        conteudo = b"OggS-fake-audio-bytes"
        client = MagicMock()
        monkeypatch.setattr(storage, "_client", lambda: client)

        criado = {}

        async def _fake_criar(pool, **kw):
            criado.update(kw)
            return Arquivo(uuid="abc", **{k: v for k, v in kw.items()})

        with patch.object(storage.arquivo_lib, "criar_arquivo", new=_fake_criar):
            arq = await storage.guardar_midia(
                MagicMock(), 7, conteudo, "audio/ogg", "nota.ogg"
            )

        # subiu pro bucket com ContentType limpo (sem o '; codecs=')
        client.put_object.assert_called_once()
        _, kwargs = client.put_object.call_args
        assert kwargs["Bucket"] == "test-bucket"
        assert kwargs["Body"] == conteudo
        assert kwargs["ContentType"] == "audio/ogg"
        # registrou com tamanho e sha256 corretos
        import hashlib

        assert criado["size_bytes"] == len(conteudo)
        assert criado["sha256"] == hashlib.sha256(conteudo).hexdigest()
        assert criado["empresa_id"] == 7
        assert arq.uuid == "abc"

    async def test_sem_storage_configurado_levanta(self, monkeypatch):
        monkeypatch.setattr(settings, "s3_bucket", "", raising=False)
        with pytest.raises(storage.StorageNaoConfigurado):
            await storage.guardar_midia(MagicMock(), 1, b"x", "image/png")


class TestUrlAssinada:
    def test_gera_presigned_get(self, monkeypatch):
        client = MagicMock()
        client.generate_presigned_url.return_value = "https://minio/signed?x=1"
        monkeypatch.setattr(storage, "_client", lambda: client)
        arq = Arquivo(uuid="u", empresa_id=1, bucket="test-bucket", object_key="k.ogg")
        url = storage.url_assinada(arq, ttl=120)
        assert url == "https://minio/signed?x=1"
        _, kwargs = client.generate_presigned_url.call_args
        assert kwargs["Params"] == {"Bucket": "test-bucket", "Key": "k.ogg"}
        assert kwargs["ExpiresIn"] == 120


class TestApagarMidia:
    async def test_apaga_objeto_e_registro(self, monkeypatch):
        client = MagicMock()
        monkeypatch.setattr(storage, "_client", lambda: client)
        del_reg = AsyncMock(return_value=True)
        with patch.object(storage.arquivo_lib, "delete_arquivo", new=del_reg):
            arq = Arquivo(uuid="u", empresa_id=1, bucket="b", object_key="k")
            await storage.apagar_midia(MagicMock(), arq)
        client.delete_object.assert_called_once_with(Bucket="b", Key="k")
        del_reg.assert_awaited_once()

    async def test_objeto_ja_sumido_ainda_apaga_registro(self, monkeypatch):
        client = MagicMock()
        client.delete_object.side_effect = RuntimeError("NoSuchKey")
        monkeypatch.setattr(storage, "_client", lambda: client)
        del_reg = AsyncMock(return_value=True)
        with patch.object(storage.arquivo_lib, "delete_arquivo", new=del_reg):
            arq = Arquivo(uuid="u", empresa_id=1, bucket="b", object_key="k")
            await storage.apagar_midia(MagicMock(), arq)  # não levanta
        del_reg.assert_awaited_once()
