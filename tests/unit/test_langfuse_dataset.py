"""Auto-dataset via Langfuse — idempotência do ingest (Fase 1)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytestmark = pytest.mark.asyncio


def _pool_com_linhas(linhas):
    """Pool mock: SELECT retorna `linhas`; INSERT retorna rowcount conforme
    o set de traces já vistos (simula ON CONFLICT DO NOTHING)."""
    vistos: set = set()

    async def _execute(sql, params=None):
        cur = MagicMock()
        if "SELECT" in sql and "message_queue" in sql:
            cur.fetchall = AsyncMock(return_value=linhas)
        else:  # INSERT
            trace = params[6] if params else None
            if trace in vistos:
                cur.rowcount = 0
            else:
                vistos.add(trace)
                cur.rowcount = 1
        return cur

    conn = MagicMock()
    conn.execute = AsyncMock(side_effect=_execute)
    conn.commit = AsyncMock()
    pool = MagicMock()
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool


SCORES = [
    {"traceId": "t1", "value": 9.0, "name": "nps"},
    {"traceId": "t2", "value": 10.0, "name": "nps"},
    {"traceId": "t3", "value": 5.0, "name": "nps"},  # abaixo do min
]
LINHAS = [
    ("t1", "quanto custa a DP?", "A DP é com a Tesouraria.", "ag", 10),
    ("t2", "quando abre rematrícula?", "Em julho.", "ag", 11),
]


class TestIngestIdempotente:
    async def test_primeira_run_insere_bons(self):
        from whatsapp_langchain.shared.langfuse_dataset import ingest_from_langfuse

        pool = _pool_com_linhas(LINHAS)
        with patch(
            "whatsapp_langchain.shared.langfuse_dataset.langfuse_client.list_scores",
            return_value=SCORES,
        ):
            r = await ingest_from_langfuse(pool, 1)
        assert r["scores_lidos"] == 3
        assert r["cruzados"] == 2
        assert r["novos"] == 2  # t3 filtrado por min_score
        assert r["skipped"] == 0

    async def test_rerun_nao_duplica(self):
        from whatsapp_langchain.shared.langfuse_dataset import ingest_from_langfuse

        pool = _pool_com_linhas(LINHAS)
        with patch(
            "whatsapp_langchain.shared.langfuse_dataset.langfuse_client.list_scores",
            return_value=SCORES,
        ):
            await ingest_from_langfuse(pool, 1)  # popula "vistos"
            r2 = await ingest_from_langfuse(pool, 1)  # re-run
        assert r2["novos"] == 0
        assert r2["skipped"] == 2

    async def test_dry_run_nao_insere(self):
        from whatsapp_langchain.shared.langfuse_dataset import ingest_from_langfuse

        pool = _pool_com_linhas(LINHAS)
        with patch(
            "whatsapp_langchain.shared.langfuse_dataset.langfuse_client.list_scores",
            return_value=SCORES,
        ):
            r = await ingest_from_langfuse(pool, 1, dry_run=True)
        assert r["dry_run"] is True
        assert r["novos"] == 2  # conta, mas não persiste

    async def test_sem_scores_bons_noop(self):
        from whatsapp_langchain.shared.langfuse_dataset import ingest_from_langfuse

        pool = _pool_com_linhas(LINHAS)
        with patch(
            "whatsapp_langchain.shared.langfuse_dataset.langfuse_client.list_scores",
            return_value=[{"traceId": "x", "value": 2.0, "name": "nps"}],
        ):
            r = await ingest_from_langfuse(pool, 1)
        assert r["novos"] == 0 and r["cruzados"] == 0


class TestIngestGoldProviderLangsmith:
    """O branch LangSmith do ingest_gold — a fonte nova de 2026-08-20.

    Antes deste branch existir, provider=langsmith gerava só um aviso de
    limitação ("só guardamos o id de trace do Langfuse") e a fonte nunca
    contribuía. Estes testes fixam o contrato novo: a função é CHAMADA, o
    resultado dela entra em `por_fonte`, e os dois modos de silêncio são
    distinguíveis (zero feedback ≠ provedor quebrado).
    """

    async def _gold(self, langsmith_result=None, langsmith_erro=None):
        from whatsapp_langchain.shared import langfuse_dataset as mod

        async def _fake_ingest(pool, empresa_id, **kw):
            if langsmith_erro:
                raise langsmith_erro
            return langsmith_result

        with (
            patch.object(
                mod,
                "ingest_from_csat",
                new=AsyncMock(return_value={"novos": 2, "skipped": 0}),
            ),
            patch.object(mod, "ingest_from_langsmith", new=_fake_ingest),
            patch(
                "whatsapp_langchain.shared.obs_provider.provider_efetivo",
                new=AsyncMock(return_value="langsmith"),
            ),
            patch(
                "whatsapp_langchain.shared.obs_provider.langfuse_configurado",
                return_value=False,
            ),
        ):
            return await mod.ingest_gold(MagicMock(), 1018)

    async def test_langsmith_com_feedback_soma_na_fonte(self):
        r = await self._gold(
            langsmith_result={
                "feedbacks_lidos": 3,
                "cruzados": 2,
                "novos": 2,
                "skipped": 0,
            }
        )
        assert r["por_fonte"]["langsmith"]["novos"] == 2
        assert r["novos"] == 4  # 2 csat + 2 langsmith
        # com feedback presente, nenhum aviso de "sem feedback"
        assert not any("feedback" in a for a in r["avisos"])

    async def test_langsmith_sem_feedback_avisa_como_agir(self):
        r = await self._gold(
            langsmith_result={
                "feedbacks_lidos": 0,
                "cruzados": 0,
                "novos": 0,
                "skipped": 0,
            }
        )
        assert r["por_fonte"]["langsmith"]["novos"] == 0
        # o zero vem explicado: falta anotar, não falta integração
        assert any("feedback" in a and "anote" in a for a in r["avisos"])

    async def test_langsmith_quebrado_nao_derruba_a_rodada(self):
        r = await self._gold(langsmith_erro=RuntimeError("api fora"))
        # CSAT continua contribuindo e o aviso diz que a consulta falhou
        assert r["novos"] == 2
        assert any("falhou" in a for a in r["avisos"])
