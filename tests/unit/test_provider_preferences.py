"""Política de roteamento OpenRouter (ADR-001) — quem ganha bloco `provider`.

O contrato tem dois lados igualmente importantes:
- modelo de peso aberto ganha piso de quantização (barra host fp4/unknown);
- modelo proprietário NÃO ganha bloco nenhum — preferência explícita desliga
  o load balancing do OpenRouter, que já faz failover entre endpoints
  1st-party. "Adicionar provider pra todo mundo" é regressão, não melhoria.
"""

from __future__ import annotations

import base64
import json
from unittest.mock import patch

import httpx
import pytest
import respx

from whatsapp_langchain.shared.llm import (
    QUANTIZACOES_ACEITAS,
    create_chat_model,
    provider_preferences,
)
from whatsapp_langchain.shared.midia_processing import chat_completion_media

PROPRIETARIOS = [
    "google/gemini-3.1-flash-lite",
    "google/gemini-2.5-flash",
    "openai/gpt-4o-mini",
    "openai/gpt-audio-mini",
    "anthropic/claude-haiku-4.5",
    "x-ai/grok-4.5",
]

ABERTOS = [
    "deepseek/deepseek-v3.2",
    "meta-llama/llama-3.3-70b-instruct",
    "z-ai/glm-4.7-flash",
    "tencent/hy3-preview",
    "qwen/qwen2.5-vl-72b-instruct",
]


class TestProviderPreferences:
    @pytest.mark.parametrize("modelo", PROPRIETARIOS)
    def test_proprietario_nao_ganha_bloco(self, modelo):
        assert provider_preferences(modelo) is None

    @pytest.mark.parametrize("modelo", ABERTOS)
    def test_aberto_ganha_piso_de_quantizacao(self, modelo):
        prefs = provider_preferences(modelo)
        assert prefs == {"quantizations": QUANTIZACOES_ACEITAS}
        # Sem lista nominal: `only`/`order` exigem estudo com tráfego real
        # (gatilho registrado na ADR) e desligariam o load balancing.
        assert "only" not in prefs and "order" not in prefs

    def test_piso_exclui_quantizacao_degradada(self):
        for degradada in ("int4", "fp4", "int8", "unknown"):
            assert degradada not in QUANTIZACOES_ACEITAS


class TestCreateChatModel:
    def test_aberto_leva_extra_body(self):
        m = create_chat_model(model="deepseek/deepseek-v3.2")
        assert m.extra_body == {"provider": {"quantizations": QUANTIZACOES_ACEITAS}}

    def test_proprietario_nao_leva_extra_body(self):
        """O caminho quente (Gemini) tem que ficar byte a byte como era."""
        m = create_chat_model(model="google/gemini-3.1-flash-lite")
        assert not m.extra_body


def _resposta_ok(content: str = "olá") -> dict:
    return {
        "choices": [{"message": {"content": content}}],
        "model": "x",
        "usage": {"cost": 0.0001},
    }


def _mensagens() -> list[dict]:
    return [{"role": "user", "content": "oi"}]


@pytest.fixture(autouse=True)
def _api_key_presente():
    from pydantic import SecretStr

    from whatsapp_langchain.shared.config import settings

    with patch.object(settings, "openrouter_api_key", SecretStr("sk-or-teste")):
        yield


class TestChatCompletionMediaPayload:
    @respx.mock
    async def test_modelo_aberto_envia_bloco_provider(self, respx_mock):
        route = respx_mock.post(url__regex=r".*/chat/completions").mock(
            return_value=httpx.Response(200, json=_resposta_ok())
        )
        await chat_completion_media(_mensagens(), model="deepseek/deepseek-v3.2")
        payload = json.loads(route.calls.last.request.content)
        assert payload["provider"] == {"quantizations": QUANTIZACOES_ACEITAS}

    @respx.mock
    async def test_modelo_proprietario_nao_envia_bloco(self, respx_mock):
        route = respx_mock.post(url__regex=r".*/chat/completions").mock(
            return_value=httpx.Response(200, json=_resposta_ok())
        )
        await chat_completion_media(_mensagens(), model="google/gemini-2.5-flash-lite")
        payload = json.loads(route.calls.last.request.content)
        assert "provider" not in payload
        # Regressão: usage.include continua (mig 139 — custo real).
        assert payload["usage"] == {"include": True}


class TestErroDentroDoChoice:
    """Variante do gotcha do envelope: erro em `choices[0].error` num 200."""

    @respx.mock
    async def test_erro_no_choice_vira_runtime_error(self, respx_mock):
        corpo = {
            "choices": [
                {
                    "error": {"code": 502, "message": "Provider overloaded"},
                    "message": {"content": ""},
                }
            ]
        }
        respx_mock.post(url__regex=r".*/chat/completions").mock(
            return_value=httpx.Response(200, json=corpo)
        )
        with pytest.raises(RuntimeError, match="Provider overloaded"):
            await chat_completion_media(_mensagens())

    @respx.mock
    async def test_resposta_normal_segue_passando(self, respx_mock):
        respx_mock.post(url__regex=r".*/chat/completions").mock(
            return_value=httpx.Response(200, json=_resposta_ok("transcrito"))
        )
        out = await chat_completion_media(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "t"},
                        {
                            "type": "input_audio",
                            "input_audio": {
                                "data": base64.b64encode(b"x").decode(),
                                "format": "ogg",
                            },
                        },
                    ],
                }
            ]
        )
        assert out == "transcrito"
