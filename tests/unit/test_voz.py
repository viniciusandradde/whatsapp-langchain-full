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
    USER_PROMPT_VOZ,
    VOZ_FIDELIDADE_MINIMA,
    VOZ_TEXTO_MAX_CHARS,
    VOZES,
    VozError,
    VozInfielError,
    VozTextoLongoError,
    _normalizar_para_comparar,
    _preambulo_inventado,
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
    async def test_texto_vai_no_system_nunca_no_user(self, respx_mock):
        """Regressão do incidente do atendimento 63.

        Texto no papel de `user` é lido pelo gpt-audio-mini como fala dirigida
        a ele — e ele RESPONDE em vez de ler. O texto tem que ficar no system,
        delimitado, com o user carregando apenas a ordem.
        """
        route = _mock_tts(respx_mock)
        texto = "Sou um assistente virtual da VSA. Qual é o seu papel na escola?"
        await sintetizar(texto, estilo="fale com calma, tom acolhedor")
        payload = json.loads(route.calls.last.request.content)
        system, user = payload["messages"]

        assert system["role"] == "system"
        assert SYSTEM_PROMPT_VOZ in system["content"]
        assert f"<texto>\n{texto}\n</texto>" in system["content"]
        assert "fale com calma, tom acolhedor" in system["content"]

        assert user["role"] == "user"
        assert user["content"] == USER_PROMPT_VOZ
        assert texto not in user["content"]

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


class TestNormalizacaoParaComparar:
    """A comparação tem que ignorar formatação e enxergar só o que é falado."""

    def test_markdown_e_numeracao_somem(self):
        alvo = _normalizar_para_comparar("1. **Agentes de IA** (suporte).")
        assert "*" not in alvo and "1." not in alvo
        assert "agentes de ia" in alvo

    def test_acento_e_caixa_preservam_a_palavra(self):
        assert _normalizar_para_comparar("Vinícius ANDRADE") == "vinícius andrade"

    def test_pontuacao_diferente_nao_conta_como_divergencia(self):
        escrito = _normalizar_para_comparar("Para eu entender: qual é o caso?")
        falado = _normalizar_para_comparar("Para eu entender, qual é o caso")
        assert escrito == falado


class TestPreambuloInventado:
    def test_muleta_de_conversa_e_detectada(self):
        alvo = _normalizar_para_comparar("Boa noite. Na VSA a gente trabalha assim.")
        ouvido = _normalizar_para_comparar(
            "Claro, vou repetir. Boa noite. Na VSA a gente trabalha assim."
        )
        assert _preambulo_inventado(alvo, ouvido) == "claro"

    def test_texto_que_ja_comeca_assim_nao_e_falso_positivo(self):
        """ "Entendido. Só para eu alinhar…" é resposta real do agente."""
        alvo = _normalizar_para_comparar("Entendido. Só para eu alinhar o contexto.")
        ouvido = _normalizar_para_comparar("Entendido, só para eu alinhar o contexto.")
        assert _preambulo_inventado(alvo, ouvido) is None


class TestVerificacaoDeFidelidade:
    """Regressão do incidente: áudio que diz outra coisa não pode sair.

    Os textos e as transcrições abaixo são os do atendimento 63 em produção
    (2026-08-22) — o áudio recusado aqui é literalmente o que o cliente ouviu.
    """

    TEXTO_407 = (
        "Sou um assistente virtual da VSA Tecnologia. Meu papel é entender o "
        "contexto da sua operação e identificar se nossas soluções de IA e "
        "automação fazem sentido para o seu desafio atual.\n\n"
        "Para eu entender melhor o seu caso: qual é o seu papel na escola e "
        "qual é a principal dor que vocês estão enfrentando hoje?"
    )

    def _patch_ouvido(self, transcricao: str):
        return patch(
            "whatsapp_langchain.shared.voz.transcribe_audio_bytes",
            new=AsyncMock(return_value=transcricao),
        )

    @respx.mock
    async def test_audio_que_responde_em_vez_de_ler_e_recusado(self, respx_mock):
        _mock_tts(respx_mock)
        ouvido_real = (
            "Claro, pode me detalhar um pouco mais sobre o seu papel na escola "
            "e qual a principal dor que vocês estão enfrentando agora? Assim, "
            "eu posso ajudar de forma mais eficaz."
        )
        with self._patch_ouvido(ouvido_real):
            with pytest.raises(VozInfielError):
                await sintetizar(self.TEXTO_407, verificar_fidelidade=True)

    @respx.mock
    async def test_leitura_fiel_passa(self, respx_mock):
        _mock_tts(respx_mock)
        # Transcrição real de uma leitura correta: muda pontuação e engole um
        # "eu", mas diz a mesma coisa — não pode virar falso positivo.
        ouvido = (
            "Sou um assistente virtual da VSA Tecnologia. Meu papel é entender "
            "o contexto da sua operação e identificar se nossas soluções de IA "
            "e automação fazem sentido para o seu desafio atual. Para entender "
            "melhor o seu caso, qual é o seu papel na escola e qual é a "
            "principal dor que vocês estão enfrentando hoje?"
        )
        with self._patch_ouvido(ouvido):
            ogg = await sintetizar(self.TEXTO_407, verificar_fidelidade=True)
        assert ogg.startswith(b"OggS")

    @respx.mock
    async def test_preambulo_inventado_recusa_mesmo_com_conteudo_certo(
        self, respx_mock
    ):
        _mock_tts(respx_mock)
        with self._patch_ouvido(
            f"Claro, vou repetir o que você disse. {self.TEXTO_407}"
        ):
            with pytest.raises(VozInfielError, match="preâmbulo"):
                await sintetizar(self.TEXTO_407, verificar_fidelidade=True)

    @respx.mock
    async def test_transcricao_vazia_recusa(self, respx_mock):
        """Sem conseguir ouvir, não dá pra afirmar que o áudio está certo."""
        _mock_tts(respx_mock)
        with self._patch_ouvido("   "):
            with pytest.raises(VozInfielError):
                await sintetizar(self.TEXTO_407, verificar_fidelidade=True)

    @respx.mock
    async def test_sem_verificar_nao_transcreve(self, respx_mock):
        """A amostra da UI não paga a transcrição nem os ~2s dela."""
        _mock_tts(respx_mock)
        mock = AsyncMock(return_value="qualquer coisa")
        with patch("whatsapp_langchain.shared.voz.transcribe_audio_bytes", new=mock):
            ogg = await sintetizar(self.TEXTO_407)
        assert ogg.startswith(b"OggS")
        mock.assert_not_awaited()

    @respx.mock
    async def test_custo_e_registrado_mesmo_quando_o_audio_e_recusado(self, respx_mock):
        """A síntese foi cobrada; esconder isso seria gasto invisível."""
        _mock_tts(respx_mock, body=_sse_body(usage={"cost": 0.0008}))
        with (
            patch(
                "whatsapp_langchain.shared.voz.registrar_execucao", new=AsyncMock()
            ) as mock_reg,
            patch(
                "whatsapp_langchain.shared.voz.acrescentar_consumo", new=AsyncMock()
            ) as mock_consumo,
            self._patch_ouvido("Nada a ver com o texto pedido."),
        ):
            with pytest.raises(VozInfielError):
                await sintetizar(
                    self.TEXTO_407,
                    pool=MagicMock(),
                    empresa_id=1,
                    verificar_fidelidade=True,
                )
        mock_reg.assert_awaited_once()
        mock_consumo.assert_awaited_once()

    def test_limiar_calibrado_no_incidente(self):
        """Guarda do número: mexer nele sem medir é regressão silenciosa."""
        assert VOZ_FIDELIDADE_MINIMA == 0.85


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
