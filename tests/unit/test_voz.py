"""Testes de `shared/voz.py` — síntese TTS sem tocar no OpenRouter real.

O HTTP é mockado com respx (SSE completo, incluindo usage no último evento);
a conversão PCM16→OGG/Opus roda de verdade com PyAV — é justamente o que
queremos provar: o SSE mockado vira um OGG com magic `OggS`.
"""

from __future__ import annotations

import base64
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
import respx

from whatsapp_langchain.shared.voz import (
    SYSTEM_PROMPT_VOZ,
    VOZ_TEXTO_MAX_CHARS,
    VOZES,
    VozError,
    VozTextoLongoError,
    sintetizar,
)

# 0,2s de silêncio PCM16 24kHz mono — o suficiente pro libopus emitir frames.
_PCM_SILENCIO = b"\x00" * (24000 * 2 // 5)


def _sse_body(*, com_audio: bool = True, usage: dict | None = None) -> str:
    """Monta um corpo SSE no formato observado na prova real (prova_tts3.py)."""
    b64 = base64.b64encode(_PCM_SILENCIO).decode("ascii")
    meio = len(b64) // 2
    eventos = []
    if com_audio:
        eventos.append({"choices": [{"delta": {"audio": {"data": b64[:meio]}}}]})
    ultimo: dict = {
        "choices": [{"delta": {"audio": {"data": b64[meio:]}}} if com_audio else {}],
    }
    if usage is not None:
        ultimo["usage"] = usage
    eventos.append(ultimo)
    linhas = [f"data: {json.dumps(e)}" for e in eventos]
    linhas.append("data: [DONE]")
    return "\n\n".join(linhas) + "\n\n"


def _mock_tts(respx_mock, *, status: int = 200, body: str | None = None):
    return respx_mock.post(url__regex=r".*/chat/completions").mock(
        return_value=httpx.Response(
            status, content=(body if body is not None else _sse_body())
        )
    )


@pytest.fixture(autouse=True)
def _api_key_presente():
    """Garante chave resolvida sem depender do .env da máquina."""
    from pydantic import SecretStr

    from whatsapp_langchain.shared.config import settings

    with patch.object(
        type(settings),
        "resolved_tts_api_key",
        new=property(lambda self: SecretStr("sk-or-v1-teste")),
    ):
        yield


class TestSintetizar:
    @respx.mock
    async def test_sse_mockado_vira_ogg_valido(self, respx_mock):
        _mock_tts(respx_mock)
        ogg = await sintetizar("Olá, tudo bem?")
        assert ogg.startswith(b"OggS")
        assert len(ogg) > 40  # tem páginas além do header

    async def test_texto_longo_recusa_sem_chamar_http(self):
        # Sem respx ativo: se tentasse HTTP, explodiria com erro de conexão —
        # a recusa tem que vir ANTES.
        with pytest.raises(VozTextoLongoError):
            await sintetizar("a" * (VOZ_TEXTO_MAX_CHARS + 1))

    @respx.mock
    async def test_voz_invalida_cai_em_alloy(self, respx_mock):
        route = _mock_tts(respx_mock)
        ogg = await sintetizar("Oi", voz="darth-vader")
        assert ogg.startswith(b"OggS")
        payload = json.loads(route.calls.last.request.content)
        assert payload["audio"]["voice"] == "alloy"

    @respx.mock
    async def test_falha_http_vira_voz_error(self, respx_mock):
        _mock_tts(respx_mock, status=500, body="boom")
        with pytest.raises(VozError, match="HTTP 500"):
            await sintetizar("Oi")

    @respx.mock
    async def test_envelope_de_erro_em_200_vira_voz_error(self, respx_mock):
        # Gotcha conhecido: OpenRouter devolve 200 com envelope de erro.
        corpo = 'data: {"error": {"message": "rate limited"}}\n\ndata: [DONE]\n\n'
        _mock_tts(respx_mock, body=corpo)
        with pytest.raises(VozError, match="provedor"):
            await sintetizar("Oi")

    @respx.mock
    async def test_sem_audio_no_sse_vira_voz_error(self, respx_mock):
        _mock_tts(respx_mock, body=_sse_body(com_audio=False))
        with pytest.raises(VozError, match="não devolveu áudio"):
            await sintetizar("Oi")

    @respx.mock
    async def test_system_prompt_anti_comentario_e_estilo(self, respx_mock):
        route = _mock_tts(respx_mock)
        await sintetizar("Oi", estilo="fale com calma, tom acolhedor")
        payload = json.loads(route.calls.last.request.content)
        system = payload["messages"][0]
        assert system["role"] == "system"
        assert SYSTEM_PROMPT_VOZ in system["content"]
        assert "sem adicionar, comentar ou responder nada" in system["content"]
        assert "fale com calma, tom acolhedor" in system["content"]
        # Contrato da prova: stream + pcm16 são obrigatórios no gpt-audio-mini.
        assert payload["stream"] is True
        assert payload["audio"]["format"] == "pcm16"

    @respx.mock
    async def test_custo_registrado_com_pool_e_empresa(self, respx_mock):
        _mock_tts(
            respx_mock,
            body=_sse_body(
                usage={"prompt_tokens": 30, "completion_tokens": 100, "cost": 0.0006}
            ),
        )
        with (
            patch(
                "whatsapp_langchain.shared.voz.registrar_execucao",
                new_callable=AsyncMock,
            ) as mock_reg,
            patch(
                "whatsapp_langchain.shared.voz.acrescentar_consumo",
                new_callable=AsyncMock,
            ) as mock_consumo,
        ):
            await sintetizar("Oi", pool=MagicMock(), empresa_id=42)

        mock_reg.assert_awaited_once()
        kwargs = mock_reg.await_args.kwargs
        assert kwargs["empresa_id"] == 42
        assert kwargs["custo_total"] == 0.0006
        assert kwargs["custo_fonte"] == "openrouter"
        mock_consumo.assert_awaited_once()
        assert mock_consumo.await_args.args[1:] == (42, 0.0006)

    @respx.mock
    async def test_sem_pool_nao_registra_custo(self, respx_mock):
        _mock_tts(
            respx_mock,
            body=_sse_body(usage={"cost": 0.0006}),
        )
        with (
            patch(
                "whatsapp_langchain.shared.voz.registrar_execucao",
                new_callable=AsyncMock,
            ) as mock_reg,
            patch(
                "whatsapp_langchain.shared.voz.acrescentar_consumo",
                new_callable=AsyncMock,
            ) as mock_consumo,
        ):
            await sintetizar("Oi")

        mock_reg.assert_not_awaited()
        mock_consumo.assert_not_awaited()

    @respx.mock
    async def test_falha_no_registro_de_custo_nao_propaga(self, respx_mock):
        """Contrato mig 164: custo é best-effort — a resposta falada vence."""
        _mock_tts(respx_mock, body=_sse_body(usage={"cost": 0.0006}))
        with patch(
            "whatsapp_langchain.shared.voz.registrar_execucao",
            new=AsyncMock(side_effect=RuntimeError("db fora")),
        ):
            ogg = await sintetizar("Oi", pool=MagicMock(), empresa_id=1)
        assert ogg.startswith(b"OggS")


class TestCatalogo:
    def test_oito_vozes_com_rotulo(self):
        assert len(VOZES) == 8
        assert set(VOZES) == {
            "alloy",
            "ash",
            "ballad",
            "coral",
            "echo",
            "sage",
            "shimmer",
            "verse",
        }
        assert all(v for v in VOZES.values())
