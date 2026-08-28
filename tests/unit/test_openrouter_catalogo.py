"""Unit do sync do catálogo OpenRouter (shared/openrouter_catalogo.py).

HTTP mockado com respx usando o FORMATO REAL dos payloads (capturado da API
em 2026-08-25); o banco é mockado — o que se prova aqui é o parsing e o
contrato das chamadas, não SQL.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import respx

from whatsapp_langchain.shared.openrouter_catalogo import (
    _slug_base,
    coletar_metricas,
    modelos_em_uso,
    sync_catalogo,
    sync_rankings,
)

_PROVIDERS = {
    "data": [
        {
            "name": "Google AI Studio",
            "slug": "google-ai-studio",
            "privacy_policy_url": "https://policies.google.com/privacy",
            "terms_of_service_url": None,
            "status_page_url": None,
            "headquarters": "US",
            "datacenters": ["US"],
        }
    ]
}

_MODELS = {
    "data": [
        {
            "id": "google/gemini-3.1-flash-lite",
            "canonical_slug": "google/gemini-3.1-flash-lite-20260507",
            "name": "Google: Gemini 3.1 Flash Lite",
            "description": "d",
            "created": 1747000000,
            "context_length": 1048576,
            "architecture": {
                "input_modalities": ["text", "image", "audio"],
                "output_modalities": ["text"],
            },
            "pricing": {"prompt": "0.0000001", "completion": "0.0000004"},
            "supported_parameters": ["tools", "temperature"],
            "benchmarks": {"artificial_analysis": {"intelligence_index": 42.1}},
        }
    ]
}

_ENDPOINTS = {
    "data": {
        "endpoints": [
            {
                "provider_name": "Google AI Studio",
                "tag": "google-ai-studio",
                "quantization": None,
                "status": 0,
                "uptime_last_5m": 100.0,
                "uptime_last_30m": 99.3,
                "uptime_last_1d": 99.8,
                "latency_last_30m": {"p50": 500, "p75": 700, "p90": 900, "p99": 2000},
                "throughput_last_30m": {"p50": 120, "p75": 140, "p90": 160, "p99": 200},
                "pricing": {"prompt": "0.0000001"},
            }
        ]
    }
}


def _pool_mock() -> tuple[MagicMock, AsyncMock]:
    """Pool falso: pool.connection() → conn com execute/commit registráveis."""
    conn = AsyncMock()
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=conn)
    cm.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.connection = MagicMock(return_value=cm)
    return pool, conn


class TestSyncCatalogo:
    @respx.mock
    async def test_sync_grava_provedores_e_modelos(self, respx_mock):
        respx_mock.get(url__regex=r".*/providers").mock(
            return_value=httpx.Response(200, json=_PROVIDERS)
        )
        respx_mock.get(url__regex=r".*/models$").mock(
            return_value=httpx.Response(200, json=_MODELS)
        )
        pool, conn = _pool_mock()
        out = await sync_catalogo(pool)
        assert out == {"provedores": 1, "modelos": 1}
        sqls = " ".join(str(c.args[0]) for c in conn.execute.await_args_list)
        assert "INSERT INTO openrouter_provedor" in sqls
        assert "INSERT INTO openrouter_modelo" in sqls
        # retenção roda junto do sync — sem cron novo
        assert "DELETE FROM openrouter_endpoint_metrica" in sqls

    @respx.mock
    async def test_item_quebrado_nao_derruba_o_lote(self, respx_mock):
        quebrado = {"data": _MODELS["data"] + [{"id": None, "created": "não-é-epoch"}]}
        respx_mock.get(url__regex=r".*/providers").mock(
            return_value=httpx.Response(200, json=_PROVIDERS)
        )
        respx_mock.get(url__regex=r".*/models$").mock(
            return_value=httpx.Response(200, json=quebrado)
        )
        pool, conn = _pool_mock()

        # o execute do item ruim explode; o do bom passa
        async def _execute(sql, *a, **kw):
            if "openrouter_modelo" in str(sql) and a and a[0][0] is None:
                raise RuntimeError("slug nulo")
            return MagicMock()

        conn.execute = AsyncMock(side_effect=_execute)
        out = await sync_catalogo(pool)
        assert out["modelos"] == 1  # só o válido contou


class TestColetarMetricas:
    @respx.mock
    async def test_grava_percentis_e_marca_sync(self, respx_mock):
        respx_mock.get(url__regex=r".*/models/google/gemini-2\.5-flash/endpoints").mock(
            return_value=httpx.Response(200, json=_ENDPOINTS)
        )
        pool, conn = _pool_mock()
        n = await coletar_metricas(pool, ["google/gemini-2.5-flash"])
        assert n == 1
        chamadas = conn.execute.await_args_list
        insert = next(
            c for c in chamadas if "openrouter_endpoint_metrica" in str(c.args[0])
        )
        params = insert.args[1]
        assert params[0] == "google/gemini-2.5-flash"
        assert params[1] == "google-ai-studio"  # tag, não display name
        assert '"p50": 500' in params[8]  # latência serializada

    @respx.mock
    async def test_chamada_leva_a_chave(self, respx_mock):
        """Sem auth o OpenRouter devolve latência NULL em silêncio — a chave
        no header é o que torna a coleta útil (provado 2026-08-25)."""
        route = respx_mock.get(url__regex=r".*/endpoints").mock(
            return_value=httpx.Response(200, json=_ENDPOINTS)
        )
        pool, _ = _pool_mock()
        from pydantic import SecretStr

        from whatsapp_langchain.shared.config import settings

        with patch.object(settings, "openrouter_api_key", SecretStr("sk-or-t")):
            await coletar_metricas(pool, ["a/b"])
        assert route.calls.last.request.headers.get("Authorization") == "Bearer sk-or-t"

    @respx.mock
    async def test_modelo_404_nao_cala_os_demais(self, respx_mock):
        """Slug aposentado no curado não pode derrubar a coleta do resto."""
        respx_mock.get(url__regex=r".*/models/x-ai/morto/endpoints").mock(
            return_value=httpx.Response(404, json={"error": "not found"})
        )
        respx_mock.get(url__regex=r".*/models/google/vivo/endpoints").mock(
            return_value=httpx.Response(200, json=_ENDPOINTS)
        )
        pool, _ = _pool_mock()
        n = await coletar_metricas(pool, ["x-ai/morto", "google/vivo"])
        assert n == 1


class TestModelosEmUso:
    async def test_em_uso_vem_antes_dos_curados_sem_duplicar(self):
        pool, conn = _pool_mock()
        cur = AsyncMock()
        cur.fetchall = AsyncMock(return_value=[("google/gemini-3.1-flash-lite",)])
        conn.execute = AsyncMock(return_value=cur)
        with patch("whatsapp_langchain.shared.openrouter_catalogo.settings") as st:
            st.openrouter_model = "google/gemini-2.5-flash-lite"
            st.openrouter_midia_model = "google/gemini-2.5-flash-lite"
            st.tts_model = "openai/gpt-audio-mini"
            slugs = await modelos_em_uso(pool)
        assert slugs[0] == "google/gemini-2.5-flash-lite"  # settings primeiro
        assert "openai/gpt-audio-mini" in slugs
        assert "google/gemini-3.1-flash-lite" in slugs  # do agente_ia
        assert len(slugs) == len(set(slugs))  # sem duplicatas


_RANKINGS = {
    "data": [
        # permaslug DATADO — formato real do dataset (capturado 2026-08-28)
        {
            "date": "2026-08-27",
            "model_permaslug": "deepseek/deepseek-v4-flash-20260731",
            "total_tokens": "2001400000000",
        },
        {
            "date": "2026-08-27",
            "model_permaslug": "xiaomi/mimo-v2.5-20260422",
            "total_tokens": "1921600000000",
        },
    ]
}


class TestSlugBase:
    def test_remove_sufixo_datado(self):
        assert (
            _slug_base("deepseek/deepseek-v4-flash-20260731")
            == "deepseek/deepseek-v4-flash"
        )

    def test_slug_sem_sufixo_fica_intacto(self):
        assert _slug_base("google/gemini-2.5-flash") == "google/gemini-2.5-flash"

    def test_data_antes_da_variante_free(self):
        # visto nos dados reais: a data fica ANTES do :free
        assert (
            _slug_base("minimax/minimax-m3-20260531:free") == "minimax/minimax-m3:free"
        )

    def test_numero_no_meio_nao_e_sufixo(self):
        # só o -YYYYMMDD FINAL é versão; dígitos no nome fazem parte do slug
        assert (
            _slug_base("tencent/hy3-20260706-preview") == "tencent/hy3-20260706-preview"
        )


class TestSyncRankings:
    @respx.mock
    async def test_upsert_com_slug_base_e_carimbo(self, respx_mock):
        respx_mock.get(url__regex=r".*/datasets/rankings-daily").mock(
            return_value=httpx.Response(200, json=_RANKINGS)
        )
        pool, conn = _pool_mock()
        n = await sync_rankings(pool)
        assert n == 2
        inserts = [
            c
            for c in conn.execute.await_args_list
            if "openrouter_ranking_diario" in str(c.args[0])
        ]
        params = inserts[0].args[1]
        assert params[1] == "deepseek/deepseek-v4-flash-20260731"  # permaslug cru
        assert params[2] == "deepseek/deepseek-v4-flash"  # base derivada
        assert params[3] == 2001400000000  # BIGINT, não string
        sqls = " ".join(str(c.args[0]) for c in conn.execute.await_args_list)
        assert "rankings_sync_at = NOW()" in sqls

    @respx.mock
    async def test_linha_quebrada_nao_derruba_o_lote(self, respx_mock):
        quebrado = {
            "data": _RANKINGS["data"] + [{"date": "2026-08-27"}]  # sem permaslug
        }
        respx_mock.get(url__regex=r".*/datasets/rankings-daily").mock(
            return_value=httpx.Response(200, json=quebrado)
        )
        pool, _ = _pool_mock()
        n = await sync_rankings(pool)
        assert n == 2  # só as válidas contaram
