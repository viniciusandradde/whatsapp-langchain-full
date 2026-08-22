"""Custo das chamadas multimodais visível à governança.

Contexto: toda transcrição de áudio, descrição de imagem e OCR passa por
`chat_completion_media` (ou pelo POST do `shared/ocr.py`) — POSTs crus ao
OpenRouter que não registravam nada. O gasto não aparecia em `ia_execucao`
nem somava no teto mensal `ia_budget` (mig 161): uma empresa em modo manual
com `transcrever_audio_sempre` ligado gastava todo mês sem que o teto visse
um centavo. Só o caminho do agente (llm_callback) era medido.

A correção segue o padrão do llm_callback: `usage.cost` da OpenRouter é a
verdade (mig 139), tabela `modelo_llm` fica de fallback marcado em
`custo_fonte`. E tudo best-effort — falha no registro NUNCA quebra o
processamento da mídia (contrato da mig 164).
"""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from pydantic import SecretStr

from whatsapp_langchain.shared import midia_processing as mp
from whatsapp_langchain.shared.governanca_ia import (
    CUSTO_FONTE_OPENROUTER,
    CUSTO_FONTE_TABELA,
)

_MSGS = [{"role": "user", "content": "oi"}]

# Resposta típica do OpenRouter com `usage` completo (inclui o `cost` real
# cobrado — é o que "usage": {"include": true} pede).
_RESPOSTA_COM_COST = {
    "id": "gen-123",
    "model": "google/gemini-2.5-flash",
    "choices": [{"message": {"content": "texto extraído"}}],
    "usage": {
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "prompt_tokens_details": {"cached_tokens": 10},
        "cost": 0.0042,
    },
}


def _fake_async_client(resposta: dict, captura: dict | None = None):
    """Substitui httpx.AsyncClient — mesmo padrão de test_media_preprocess."""

    class _FakeResp:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return resposta

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, *a, **kw):
            if captura is not None:
                captura.update(kw)
            return _FakeResp()

    return lambda *a, **kw: _FakeClient()


def _patch_api_key():
    return patch.object(mp.settings, "openrouter_api_key", SecretStr("sk-or-v1-teste"))


class TestRegistroComUsageCost:
    """Com `usage.cost` presente, grava o valor MEDIDO (mig 139)."""

    async def test_registra_execucao_e_consumo_com_valores_da_resposta(self):
        pool = object()
        registrar = AsyncMock(return_value=1)
        acrescentar = AsyncMock()

        with (
            patch.object(httpx, "AsyncClient", _fake_async_client(_RESPOSTA_COM_COST)),
            _patch_api_key(),
            patch.object(mp, "registrar_execucao", registrar),
            patch.object(mp, "acrescentar_consumo", acrescentar),
        ):
            texto = await mp.chat_completion_media(_MSGS, pool=pool, empresa_id=42)

        assert texto == "texto extraído"

        registrar.assert_awaited_once()
        kwargs = registrar.await_args.kwargs
        assert registrar.await_args.args == (pool,)
        assert kwargs["empresa_id"] == 42
        # Modelo vem de `result["model"]` (o que atendeu de fato), split
        # provedor/nome igual ao llm_callback.
        assert kwargs["modelo_provedor"] == "google"
        assert kwargs["modelo_nome"] == "gemini-2.5-flash"
        assert kwargs["tokens_input"] == 100
        assert kwargs["tokens_output"] == 20
        assert kwargs["tokens_cached"] == 10
        assert kwargs["custo_total"] == pytest.approx(0.0042)
        assert kwargs["custo_fonte"] == CUSTO_FONTE_OPENROUTER
        assert kwargs["openrouter_generation_id"] == "gen-123"
        assert kwargs["metadata"] == {"finalidade": "midia"}

        acrescentar.assert_awaited_once()
        assert acrescentar.await_args.args == (pool, 42, pytest.approx(0.0042))

    async def test_wrapper_de_audio_marca_finalidade_transcricao(self):
        """A proveniência por finalidade é o que separa mídia de agente
        no relatório — transcrição era exatamente o gasto invisível."""
        pool = object()
        registrar = AsyncMock(return_value=1)

        with (
            patch.object(httpx, "AsyncClient", _fake_async_client(_RESPOSTA_COM_COST)),
            _patch_api_key(),
            patch.object(mp, "registrar_execucao", registrar),
            patch.object(mp, "acrescentar_consumo", AsyncMock()),
        ):
            await mp.transcribe_audio_bytes(
                b"audio-bytes", "audio/ogg", pool=pool, empresa_id=7
            )

        assert registrar.await_args.kwargs["metadata"] == {
            "finalidade": "transcricao_audio"
        }

    async def test_sem_cost_cai_no_fallback_da_tabela(self):
        """Sem `usage.cost`, estima pela tabela e MARCA como estimado."""
        resposta = {
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 1_000_000, "completion_tokens": 0},
        }
        registrar = AsyncMock(return_value=1)

        with (
            patch.object(httpx, "AsyncClient", _fake_async_client(resposta)),
            _patch_api_key(),
            patch.object(mp, "registrar_execucao", registrar),
            patch.object(mp, "acrescentar_consumo", AsyncMock()),
            patch.object(
                mp, "get_custo_modelo", AsyncMock(return_value=(0.269, 0.4, None))
            ),
        ):
            await mp.chat_completion_media(
                _MSGS, model="deepseek/deepseek-v3.2", pool=object(), empresa_id=1
            )

        kwargs = registrar.await_args.kwargs
        assert kwargs["custo_fonte"] == CUSTO_FONTE_TABELA
        assert kwargs["custo_total"] == pytest.approx(0.269)
        # Sem `model` na resposta, usa o solicitado.
        assert kwargs["modelo_provedor"] == "deepseek"
        assert kwargs["modelo_nome"] == "deepseek-v3.2"


class TestSemPoolNaoRegistra:
    """Chamador sem empresa (aba Testar, tools do agente) funciona igual."""

    async def test_sem_pool_nem_empresa_nada_e_registrado(self):
        registrar = AsyncMock()
        acrescentar = AsyncMock()

        with (
            patch.object(httpx, "AsyncClient", _fake_async_client(_RESPOSTA_COM_COST)),
            _patch_api_key(),
            patch.object(mp, "registrar_execucao", registrar),
            patch.object(mp, "acrescentar_consumo", acrescentar),
        ):
            texto = await mp.chat_completion_media(_MSGS)

        assert texto == "texto extraído"
        registrar.assert_not_awaited()
        acrescentar.assert_not_awaited()

    async def test_pool_sem_empresa_tambem_nao_registra(self):
        registrar = AsyncMock()

        with (
            patch.object(httpx, "AsyncClient", _fake_async_client(_RESPOSTA_COM_COST)),
            _patch_api_key(),
            patch.object(mp, "registrar_execucao", registrar),
            patch.object(mp, "acrescentar_consumo", AsyncMock()),
        ):
            texto = await mp.chat_completion_media(_MSGS, pool=object())

        assert texto == "texto extraído"
        registrar.assert_not_awaited()


class TestRegistroBestEffort:
    """Falha no registro loga e segue — contrato da mig 164."""

    async def test_excecao_no_registro_nao_propaga(self):
        with (
            patch.object(httpx, "AsyncClient", _fake_async_client(_RESPOSTA_COM_COST)),
            _patch_api_key(),
            patch.object(
                mp,
                "registrar_execucao",
                AsyncMock(side_effect=RuntimeError("banco caiu")),
            ),
            patch.object(mp, "acrescentar_consumo", AsyncMock()),
        ):
            texto = await mp.chat_completion_media(_MSGS, pool=object(), empresa_id=42)

        # A transcrição/descrição chega ao cliente mesmo com o registro morto.
        assert texto == "texto extraído"

    async def test_excecao_no_consumo_nao_propaga(self):
        with (
            patch.object(httpx, "AsyncClient", _fake_async_client(_RESPOSTA_COM_COST)),
            _patch_api_key(),
            patch.object(mp, "registrar_execucao", AsyncMock(return_value=1)),
            patch.object(
                mp,
                "acrescentar_consumo",
                AsyncMock(side_effect=RuntimeError("budget travou")),
            ),
        ):
            texto = await mp.chat_completion_media(_MSGS, pool=object(), empresa_id=42)

        assert texto == "texto extraído"


class TestBodyPedeUsage:
    """O body precisa pedir `usage: {include: true}` — é como o OpenRouter
    devolve o `cost` real na resposta."""

    async def test_body_contem_usage_include_true(self):
        captura: dict = {}

        with (
            patch.object(
                httpx, "AsyncClient", _fake_async_client(_RESPOSTA_COM_COST, captura)
            ),
            _patch_api_key(),
        ):
            await mp.chat_completion_media(_MSGS)

        assert captura["json"]["usage"] == {"include": True}

    async def test_body_do_ocr_tambem_pede_usage(self):
        from whatsapp_langchain.shared import ocr as ocr_mod

        captura: dict = {}
        # PNG 1x1 válido — _resize_if_needed abre com PIL de verdade.
        png_1x1 = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNg"
            "YGBgAAAABQABh6FO1AAAAABJRU5ErkJggg=="
        )

        with (
            patch.object(
                httpx, "AsyncClient", _fake_async_client(_RESPOSTA_COM_COST, captura)
            ),
            patch.object(
                ocr_mod.settings, "openrouter_api_key", SecretStr("sk-or-v1-teste")
            ),
        ):
            await ocr_mod.ocr_image_bytes(png_1x1, mime_type="image/png")

        assert captura["json"]["usage"] == {"include": True}
