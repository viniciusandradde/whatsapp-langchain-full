"""Testes dos helpers de BaseConhecimento (M5.c)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from whatsapp_langchain.shared import base_conhecimento as bc
from whatsapp_langchain.shared.models import DocumentoConhecimentoInput


def _row(
    *,
    doc_id=1,
    empresa_id=1,
    titulo="FAQ Trocas",
    conteudo="Política: 7 dias.",
    tags=None,
    ativo=True,
    user_id=None,
    score=None,
):
    now = datetime.now(UTC)
    base = (
        doc_id,
        empresa_id,
        titulo,
        conteudo,
        tags or [],
        ativo,
        user_id,
        now,
        now,
    )
    if score is None:
        return base
    return (*base, score)


def _mock_pool(*results, rowcount: int = 1, multi: bool = False):
    cur = AsyncMock()
    if multi:
        # `results` is the list of rows fetchall should return
        cur.fetchall = AsyncMock(return_value=list(results))
    else:
        fetchone_seq = list(results) if results else [None]
        cur.fetchone = AsyncMock(side_effect=fetchone_seq)
    cur.rowcount = rowcount
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cur)
    pool = MagicMock()
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


@pytest.mark.asyncio
async def test_get_documento_returns_none_when_missing():
    pool, _ = _mock_pool(None)
    assert await bc.get_documento(pool, 1, 999) is None


@pytest.mark.asyncio
async def test_get_documento_filters_by_empresa():
    """Cross-tenant guard — empresa_id no WHERE blinda o lookup."""
    pool, conn = _mock_pool(None)
    await bc.get_documento(pool, 42, 1)
    args = conn.execute.await_args.args
    sql = args[0]
    params = args[1]
    assert "empresa_id = %s" in sql
    assert params == (1, 42)


@pytest.mark.asyncio
async def test_has_active_documents_true_when_row_exists():
    pool, _ = _mock_pool((1,))
    assert await bc.has_active_documents(pool, 1) is True


@pytest.mark.asyncio
async def test_has_active_documents_false_when_empty():
    pool, _ = _mock_pool(None)
    assert await bc.has_active_documents(pool, 1) is False


@pytest.mark.asyncio
async def test_list_documentos_returns_rows():
    pool, _ = _mock_pool(_row(doc_id=1), _row(doc_id=2), multi=True)
    docs = await bc.list_documentos(pool, 1)
    assert [d.id for d in docs] == [1, 2]


@pytest.mark.asyncio
async def test_list_documentos_apenas_ativos_filters_in_sql():
    pool, conn = _mock_pool(multi=True)
    await bc.list_documentos(pool, 1, apenas_ativos=True)
    sql = conn.execute.await_args.args[0]
    assert "AND ativo" in sql


@pytest.mark.asyncio
async def test_upsert_insert_calls_embed_and_returns_documento():
    pool, conn = _mock_pool(_row(doc_id=10, titulo="T", conteudo="C"))
    fake_vec = [0.0] * 1536
    with patch.object(bc, "_embed", AsyncMock(return_value=fake_vec)) as mock_embed:
        out = await bc.upsert_documento(
            pool,
            1,
            DocumentoConhecimentoInput(titulo="T", conteudo="C"),
            user_id="u1",
        )
    assert out.id == 10
    mock_embed.assert_awaited_once()
    embed_arg = mock_embed.await_args.args[0]
    assert embed_arg == "T\n\nC"
    sql = conn.execute.await_args.args[0]
    assert "INSERT INTO documento_conhecimento" in sql


@pytest.mark.asyncio
async def test_upsert_update_passes_doc_id_and_empresa_in_where():
    pool, conn = _mock_pool(_row(doc_id=5, titulo="T2", conteudo="C2"))
    fake_vec = [0.1] * 1536
    with patch.object(bc, "_embed", AsyncMock(return_value=fake_vec)):
        await bc.upsert_documento(
            pool,
            7,
            DocumentoConhecimentoInput(titulo="T2", conteudo="C2"),
            doc_id=5,
        )
    sql = conn.execute.await_args.args[0]
    params = conn.execute.await_args.args[1]
    assert "UPDATE documento_conhecimento" in sql
    assert "WHERE id = %s AND empresa_id = %s" in sql
    # Os dois últimos params são (doc_id, empresa_id)
    assert params[-2] == 5
    assert params[-1] == 7


@pytest.mark.asyncio
async def test_upsert_update_raises_when_row_missing():
    pool, _ = _mock_pool(None)
    with patch.object(bc, "_embed", AsyncMock(return_value=[0.0] * 1536)):
        with pytest.raises(ValueError, match="não encontrado"):
            await bc.upsert_documento(
                pool,
                1,
                DocumentoConhecimentoInput(titulo="T", conteudo="C"),
                doc_id=999,
            )


@pytest.mark.asyncio
async def test_delete_returns_true_when_deleted():
    pool, _ = _mock_pool(rowcount=1)
    assert await bc.delete_documento(pool, 1, 1) is True


@pytest.mark.asyncio
async def test_delete_returns_false_when_missing():
    pool, _ = _mock_pool(rowcount=0)
    assert await bc.delete_documento(pool, 1, 999) is False


@pytest.mark.asyncio
async def test_search_relevant_filters_min_score_and_returns_pairs():
    rows = [
        _row(doc_id=1, titulo="A", score=0.95),
        _row(doc_id=2, titulo="B", score=0.5),
        _row(doc_id=3, titulo="C", score=0.1),  # abaixo do threshold default
    ]
    pool, _ = _mock_pool(*rows, multi=True)
    with patch.object(bc, "_embed", AsyncMock(return_value=[0.0] * 1536)):
        out = await bc.search_relevant(pool, 1, "trocas")
    assert [d.id for d, _ in out] == [1, 2]
    assert out[0][1] == pytest.approx(0.95)


@pytest.mark.asyncio
async def test_search_relevant_respects_custom_min_score():
    rows = [_row(doc_id=1, score=0.4), _row(doc_id=2, score=0.2)]
    pool, _ = _mock_pool(*rows, multi=True)
    with patch.object(bc, "_embed", AsyncMock(return_value=[0.0] * 1536)):
        out = await bc.search_relevant(pool, 1, "x", min_score=0.5)
    assert out == []


def test_vector_literal_format():
    assert bc._vector_literal([1, 2.5, 3]).startswith("[")
    assert bc._vector_literal([1, 2.5, 3]).endswith("]")
    assert bc._vector_literal([0.1]).count(",") == 0
