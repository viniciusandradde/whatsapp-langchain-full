"""Testes unitários do pré-processamento de mídia antes do agente."""

from unittest.mock import AsyncMock, patch

import pytest
from pydantic import SecretStr

from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.worker.media import (
    AUTO_RESPONSE_MEDIA_FAILURE,
    preprocess_incoming_message,
)


class TestMediaPreprocess:
    """Cenários de normalização de entrada para texto."""

    async def test_no_media_keeps_text(self):
        result = await preprocess_incoming_message(
            body="Olá",
            media_url=None,
            media_type=None,
        )
        assert result.should_invoke_agent is True
        assert result.normalized_text == "Olá"
        assert result.media_processing_status == "none"

    async def test_image_disabled_ainda_invoca_agente(self):
        """Desligado não é erro: o agente responde citando o que chegou.

        Até 2026-08-05 este caminho devolvia `should_invoke_agent=False` com uma
        frase fixa que o worker mandava direto ao cliente — por fora dos portões
        de fila do departamento, modo manual e whitelist.
        """
        with patch.object(settings, "media_image_enabled", False):
            result = await preprocess_incoming_message(
                body="Veja",
                media_url="https://example.com/i.png",
                media_type="image/png",
            )
        assert result.should_invoke_agent is True
        assert result.auto_response is None
        assert result.media_processing_status == "disabled"
        assert "uma imagem" in (result.normalized_text or "")
        assert "Veja" in (result.normalized_text or "")

    async def test_audio_disabled_ainda_invoca_agente(self):
        with patch.object(settings, "media_audio_enabled", False):
            result = await preprocess_incoming_message(
                body="Ouça",
                media_url="https://example.com/a.ogg",
                media_type="audio/ogg",
            )
        assert result.should_invoke_agent is True
        assert result.media_processing_status == "disabled"
        assert "um áudio" in (result.normalized_text or "")

    async def test_tipo_sem_parser_ainda_invoca_agente(self):
        # video/* não é imagem/áudio/documento → kind "unsupported".
        result = await preprocess_incoming_message(
            body="arquivo",
            media_url="https://example.com/clip.mp4",
            media_type="video/mp4",
        )
        assert result.should_invoke_agent is True
        assert result.media_processing_status == "unsupported"
        assert "Arquivo recebido" in (result.normalized_text or "")

    async def test_payload_incompleto_ainda_invoca_agente(self):
        result = await preprocess_incoming_message(
            body="arquivo",
            media_url="https://example.com/file.ogg",
            media_type=None,
        )
        assert result.should_invoke_agent is True
        assert result.media_processing_status == "unsupported"

    async def test_nome_do_arquivo_aparece_no_texto(self):
        """O nome real é o que o cliente reconhece na resposta."""
        with patch.object(settings, "media_document_enabled", False):
            result = await preprocess_incoming_message(
                body="",
                media_url="https://example.com/x",
                media_type="application/pdf",
                filename="orcamento-julho.pdf",
            )
        assert result.should_invoke_agent is True
        assert "orcamento-julho.pdf" in (result.normalized_text or "")
        # O agente não pode supor o conteúdo que não leu.
        assert "NÃO invente" in (result.normalized_text or "")

    async def test_agente_sem_permissao_nao_baixa_o_arquivo(self):
        """Custo zero quando o agente não lê: nem download acontece."""
        baixou = AsyncMock(return_value=b"x")
        with patch("whatsapp_langchain.worker.media.download_media", new=baixou):
            result = await preprocess_incoming_message(
                body="",
                media_url="https://example.com/x.pdf",
                media_type="application/pdf",
                filename="contrato.pdf",
                aceita_documento=False,
            )
        assert result.should_invoke_agent is True
        assert result.media_processing_status == "disabled"
        baixou.assert_not_awaited()

    async def test_image_processed_to_text(self):
        with (
            patch.object(settings, "media_image_enabled", True),
            patch(
                "whatsapp_langchain.worker.media.download_media",
                new=AsyncMock(return_value=b"img-bytes"),
            ),
            patch(
                "whatsapp_langchain.worker.media._describe_image",
                new=AsyncMock(return_value="um diagrama de arquitetura"),
            ),
        ):
            result = await preprocess_incoming_message(
                body="Descreva",
                media_url="https://example.com/i.png",
                media_type="image/png",
            )

        assert result.should_invoke_agent is True
        assert result.media_processing_status == "processed"
        assert "[Descrição de imagem]: um diagrama de arquitetura" in (
            result.normalized_text or ""
        )

    async def test_audio_preprocess_failure_returns_auto_response(self):
        """Falha TRANSITÓRIA continua saindo pela retentativa — não regride.

        É o caminho que recupera áudio quando o provedor tropeça por segundos.
        """
        with (
            patch.object(settings, "media_audio_enabled", True),
            patch(
                "whatsapp_langchain.worker.media.download_media",
                new=AsyncMock(side_effect=RuntimeError("network error")),
            ),
        ):
            result = await preprocess_incoming_message(
                body="Transcreva",
                media_url="https://example.com/a.ogg",
                media_type="audio/ogg",
            )

        assert result.should_invoke_agent is False
        assert result.media_processing_status == "failed"
        assert result.auto_response == AUTO_RESPONSE_MEDIA_FAILURE
        assert "network error" in (result.media_processing_error or "")

    async def test_extensao_sem_parser_nao_vira_failed(self):
        """O defeito do atendimento 1018-000664, em forma de teste.

        `.doc` sem antiword (e qualquer extensão sem parser) é recusa
        PERMANENTE. Enquanto isso caía no `failed` genérico, a mensagem era
        retentada 5 vezes — 59 segundos para chegar à mesma desculpa.
        """
        from whatsapp_langchain.shared.file_extractor import UnsupportedFileTypeError

        with (
            patch.object(settings, "media_document_enabled", True),
            patch(
                "whatsapp_langchain.worker.media.download_media",
                new=AsyncMock(return_value=b"conteudo"),
            ),
            patch(
                "whatsapp_langchain.shared.file_extractor.extract_text",
                new=AsyncMock(side_effect=UnsupportedFileTypeError("extensão .doc")),
            ),
        ):
            result = await preprocess_incoming_message(
                body="",
                media_url="https://example.com/x",
                media_type="application/msword",
                filename="proposta.doc",
            )

        assert result.media_processing_status != "failed"
        assert result.should_invoke_agent is True
        assert "proposta.doc" in (result.normalized_text or "")


class TestEnvelopeDeErroDoOpenRouter:
    """HTTP 200 sem `choices` não pode virar `KeyError: 'choices'`.

    O OpenRouter responde 200 com envelope de erro quando o provedor recusa
    (capacidade, rate limit, indisponibilidade). O código acessava
    `result["choices"]` direto, e o log recebia a palavra `'choices'` — que não
    diz nada a quem investiga. Aconteceu no atendimento 574: o áudio do cliente
    foi descartado e o mesmo arquivo transcreveu normalmente minutos depois.
    """

    async def test_erro_com_200_vira_mensagem_legivel(self):
        import httpx

        from whatsapp_langchain.shared import midia_processing as mp

        class _FakeResp:
            status_code = 200

            def raise_for_status(self):
                return None

            def json(self):
                return {"error": {"message": "Provider returned error", "code": 429}}

        class _FakeClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, *a, **kw):
                return _FakeResp()

        with (
            patch.object(httpx, "AsyncClient", lambda *a, **kw: _FakeClient()),
            patch.object(
                mp.settings, "openrouter_api_key", SecretStr("sk-or-v1-teste")
            ),
        ):
            with pytest.raises(RuntimeError) as exc:
                await mp.chat_completion_media([{"role": "user", "content": "oi"}])

        # A mensagem tem que carregar a razão, não a chave que faltou.
        assert "Provider returned error" in str(exc.value)
        assert "choices" not in str(exc.value)


class TestMotivoEspecifico:
    """Motivo vago faz o agente inventar limitação e dizê-la ao cliente.

    Num teste real com celular, um PDF de 13 MB (acima do teto de 10) produziu
    a resposta "não consigo ler o conteúdo de documentos em PDF" — e o agente
    lê PDF. O motivo genérico virou uma limitação de formato que não existe.
    """

    async def test_arquivo_grande_diz_que_e_tamanho(self):
        from whatsapp_langchain.shared.file_extractor import FileTooLargeError

        with (
            patch.object(settings, "media_document_enabled", True),
            patch(
                "whatsapp_langchain.worker.media.download_media",
                new=AsyncMock(return_value=b"x"),
            ),
            patch(
                "whatsapp_langchain.shared.file_extractor.extract_text",
                new=AsyncMock(side_effect=FileTooLargeError("13 MB")),
            ),
        ):
            r = await preprocess_incoming_message(
                body="",
                media_url="https://example.com/x",
                media_type="application/pdf",
                filename="livro.pdf",
            )

        texto = r.normalized_text or ""
        assert "tamanho" in texto
        assert "10 MB" in texto
        # E o agente é instruído a não transformar isso em "não leio PDF".
        assert "não generalize" in texto.lower()

    async def test_formato_desconhecido_diz_que_e_formato(self):
        from whatsapp_langchain.shared.file_extractor import UnsupportedFileTypeError

        with (
            patch.object(settings, "media_document_enabled", True),
            patch(
                "whatsapp_langchain.worker.media.download_media",
                new=AsyncMock(return_value=b"x"),
            ),
            patch(
                "whatsapp_langchain.shared.file_extractor.extract_text",
                new=AsyncMock(side_effect=UnsupportedFileTypeError(".xyz")),
            ),
        ):
            r = await preprocess_incoming_message(
                body="",
                media_url="https://example.com/x",
                media_type="application/msword",
                filename="arquivo.xyz",
            )

        assert "formato" in (r.normalized_text or "")
