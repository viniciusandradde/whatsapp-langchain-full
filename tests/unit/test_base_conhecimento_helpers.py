"""Testes dos helpers de BaseConhecimento (M5.c + M5.c.1)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from whatsapp_langchain.shared import base_conhecimento as bc
from whatsapp_langchain.shared.models import DocumentoConhecimentoInput


def _doc_row(
    *,
    doc_id=1,
    empresa_id=1,
    titulo="FAQ Trocas",
    conteudo="Política: 7 dias.",
    tags=None,
    ativo=True,
    user_id=None,
):
    now = datetime.now(UTC)
    return (
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


def _search_row(
    *,
    doc_id=1,
    titulo="FAQ Trocas",
    conteudo_doc="Doc inteiro",
    chunk_idx=0,
    chunk_conteudo="trecho",
    score=0.9,
):
    """Row do JOIN documento_conhecimento_chunk + documento_conhecimento."""
    now = datetime.now(UTC)
    return (
        doc_id,
        1,  # empresa_id
        titulo,
        conteudo_doc,
        [],  # tags
        True,  # ativo
        None,  # user_id
        now,
        now,
        chunk_idx,
        chunk_conteudo,
        score,
    )


def _mock_simple_pool(*results, rowcount: int = 1, multi: bool = False):
    """Pool com 1 cursor compartilhado — pra ops single-statement."""
    cur = AsyncMock()
    if multi:
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


def _mock_upsert_pool(returning_row):
    """Pool pra upsert (transação + INSERT/UPDATE doc + DELETE chunks + N INSERTs)."""
    cur = AsyncMock()
    cur.fetchone = AsyncMock(return_value=returning_row)
    cur.rowcount = 1
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cur)
    # `async with conn.transaction():` retorna um async context manager
    transaction_cm = MagicMock()
    transaction_cm.__aenter__ = AsyncMock(return_value=None)
    transaction_cm.__aexit__ = AsyncMock(return_value=None)
    conn.transaction = MagicMock(return_value=transaction_cm)
    pool = MagicMock()
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


# --- get / list / has_active ---


@pytest.mark.asyncio
async def test_get_documento_returns_none_when_missing():
    pool, _ = _mock_simple_pool(None)
    assert await bc.get_documento(pool, 1, 999) is None


@pytest.mark.asyncio
async def test_get_documento_filters_by_empresa():
    pool, conn = _mock_simple_pool(None)
    await bc.get_documento(pool, 42, 1)
    args = conn.execute.await_args.args
    sql = args[0]
    params = args[1]
    assert "empresa_id = %s" in sql
    assert params == (1, 42)


@pytest.mark.asyncio
async def test_has_active_documents_true_when_row_exists():
    pool, _ = _mock_simple_pool((1,))
    assert await bc.has_active_documents(pool, 1) is True


@pytest.mark.asyncio
async def test_has_active_documents_false_when_empty():
    pool, _ = _mock_simple_pool(None)
    assert await bc.has_active_documents(pool, 1) is False


@pytest.mark.asyncio
async def test_list_documentos_returns_rows():
    pool, _ = _mock_simple_pool(_doc_row(doc_id=1), _doc_row(doc_id=2), multi=True)
    docs = await bc.list_documentos(pool, 1)
    assert [d.id for d in docs] == [1, 2]


@pytest.mark.asyncio
async def test_list_documentos_apenas_ativos_filters_in_sql():
    pool, conn = _mock_simple_pool(multi=True)
    await bc.list_documentos(pool, 1, apenas_ativos=True)
    sql = conn.execute.await_args.args[0]
    assert "AND ativo" in sql


# --- upsert (chunks integration) ---


@pytest.mark.asyncio
async def test_upsert_insert_creates_chunks_and_returns_documento():
    pool, conn = _mock_upsert_pool(_doc_row(doc_id=10))
    fake_vec = [0.0] * 1536
    with (
        patch.object(bc, "_embed_batch", AsyncMock(return_value=[fake_vec])),
        patch.object(bc, "split_text", return_value=["chunk único"]),
    ):
        out = await bc.upsert_documento(
            pool,
            1,
            DocumentoConhecimentoInput(titulo="T", conteudo="C"),
            user_id="u1",
        )
    assert out.id == 10
    # 3 execs no insert path: INSERT doc, DELETE chunks, INSERT chunk
    assert conn.execute.await_count >= 3


@pytest.mark.asyncio
async def test_upsert_update_uses_doc_id_and_empresa_in_where():
    pool, conn = _mock_upsert_pool(_doc_row(doc_id=5, titulo="T2"))
    with (
        patch.object(bc, "_embed_batch", AsyncMock(return_value=[[0.1] * 1536])),
        patch.object(bc, "split_text", return_value=["chunk"]),
    ):
        await bc.upsert_documento(
            pool,
            7,
            DocumentoConhecimentoInput(titulo="T2", conteudo="C2"),
            doc_id=5,
        )
    # Procura UPDATE com WHERE id e empresa_id
    update_call = next(
        c
        for c in conn.execute.await_args_list
        if "UPDATE documento_conhecimento" in c.args[0]
    )
    assert "WHERE id = %s AND empresa_id = %s" in update_call.args[0]
    params = update_call.args[1]
    assert params[-2] == 5
    assert params[-1] == 7


@pytest.mark.asyncio
async def test_upsert_raises_when_row_missing():
    pool, _ = _mock_upsert_pool(None)
    with (
        patch.object(bc, "_embed_batch", AsyncMock(return_value=[[0.0] * 1536])),
        patch.object(bc, "split_text", return_value=["chunk"]),
    ):
        with pytest.raises(ValueError, match="não encontrado"):
            await bc.upsert_documento(
                pool,
                1,
                DocumentoConhecimentoInput(titulo="T", conteudo="C"),
                doc_id=999,
            )


@pytest.mark.asyncio
async def test_upsert_chunks_n_inserts_when_multiple():
    """Doc longo → split em N chunks → N inserts no chunk table."""
    pool, conn = _mock_upsert_pool(_doc_row(doc_id=1))
    chunks = ["c1", "c2", "c3", "c4"]
    with (
        patch.object(
            bc,
            "_embed_batch",
            AsyncMock(return_value=[[0.0] * 1536] * 4),
        ),
        patch.object(bc, "split_text", return_value=chunks),
    ):
        await bc.upsert_documento(
            pool, 1, DocumentoConhecimentoInput(titulo="T", conteudo="big")
        )
    chunk_inserts = [
        c
        for c in conn.execute.await_args_list
        if "INSERT INTO documento_conhecimento_chunk" in c.args[0]
    ]
    assert len(chunk_inserts) == 4


# --- delete ---


@pytest.mark.asyncio
async def test_delete_returns_true_when_deleted():
    pool, _ = _mock_simple_pool(rowcount=1)
    assert await bc.delete_documento(pool, 1, 1) is True


@pytest.mark.asyncio
async def test_delete_returns_false_when_missing():
    pool, _ = _mock_simple_pool(rowcount=0)
    assert await bc.delete_documento(pool, 1, 999) is False


# --- search (chunks + reranker) ---


@pytest.mark.asyncio
async def test_search_relevant_no_rerank_returns_top_k_cosine():
    """rerank=False pula LLM e retorna direto top-k filtrados por min_score."""
    rows = [
        _search_row(doc_id=1, chunk_idx=0, score=0.95),
        _search_row(doc_id=1, chunk_idx=1, score=0.5),
        _search_row(doc_id=2, chunk_idx=0, score=0.1),  # filtra
    ]
    pool, _ = _mock_simple_pool(*rows, multi=True)
    with patch.object(bc, "_embed", AsyncMock(return_value=[0.0] * 1536)):
        out = await bc.search_relevant(pool, 1, "query", rerank=False)
    assert [r.score for r in out] == pytest.approx([0.95, 0.5])
    assert out[0].chunk_idx == 0
    assert out[1].chunk_idx == 1


@pytest.mark.asyncio
async def test_search_relevant_returns_search_result_objects():
    rows = [_search_row(doc_id=1, chunk_idx=0, score=0.9)]
    pool, _ = _mock_simple_pool(*rows, multi=True)
    with patch.object(bc, "_embed", AsyncMock(return_value=[0.0] * 1536)):
        out = await bc.search_relevant(pool, 1, "query", rerank=False)
    assert len(out) == 1
    assert isinstance(out[0], bc.SearchResult)
    assert out[0].documento.id == 1
    assert out[0].chunk_idx == 0


@pytest.mark.asyncio
async def test_search_relevant_skips_rerank_when_candidates_le_top_k():
    """Reranker NÃO é chamado quando temos ≤ k candidatos (otimização)."""
    rows = [_search_row(score=0.9)]
    pool, _ = _mock_simple_pool(*rows, multi=True)
    rerank_mock = AsyncMock()
    with (
        patch.object(bc, "_embed", AsyncMock(return_value=[0.0] * 1536)),
        patch.object(bc, "create_chat_model", rerank_mock),
    ):
        out = await bc.search_relevant(pool, 1, "query", k=3)
    assert len(out) == 1
    rerank_mock.assert_not_called()


@pytest.mark.asyncio
async def test_search_relevant_calls_reranker_when_more_candidates():
    """Reranker é chamado quando temos > k candidatos."""
    rows = [_search_row(doc_id=i, score=0.9 - i * 0.05) for i in range(5)]
    pool, _ = _mock_simple_pool(*rows, multi=True)

    fake_response = MagicMock()
    fake_response.content = (
        '{"ranking": [{"idx": 2, "reason": "bate exato"}, '
        '{"idx": 0, "reason": "complementa"}]}'
    )
    fake_model = MagicMock()
    fake_model.ainvoke = AsyncMock(return_value=fake_response)

    with (
        patch.object(bc, "_embed", AsyncMock(return_value=[0.0] * 1536)),
        patch.object(bc, "create_chat_model", return_value=fake_model),
    ):
        out = await bc.search_relevant(pool, 1, "query", k=2)
    # docs criados com doc_id=i → ids [0,1,2,3,4]; reranker pediu idx=2 e idx=0
    assert [r.documento.id for r in out] == [2, 0]
    assert out[0].reason == "bate exato"


@pytest.mark.asyncio
async def test_search_relevant_falls_back_to_cosine_when_reranker_fails():
    rows = [_search_row(doc_id=i, score=0.9 - i * 0.05) for i in range(5)]
    pool, _ = _mock_simple_pool(*rows, multi=True)

    fake_model = MagicMock()
    fake_model.ainvoke = AsyncMock(side_effect=RuntimeError("provider down"))
    with (
        patch.object(bc, "_embed", AsyncMock(return_value=[0.0] * 1536)),
        patch.object(bc, "create_chat_model", return_value=fake_model),
    ):
        out = await bc.search_relevant(pool, 1, "query", k=3)
    # Fallback: top 3 cosine sem reason
    assert len(out) == 3
    assert all(r.reason is None for r in out)


@pytest.mark.asyncio
async def test_search_relevant_handles_json_in_code_fences():
    """Reranker às vezes embrulha em ```json ...``` — tem que parsear."""
    rows = [_search_row(doc_id=i, score=0.9) for i in range(5)]
    pool, _ = _mock_simple_pool(*rows, multi=True)

    fake_response = MagicMock()
    fake_response.content = (
        '```json\n{"ranking": [{"idx": 1, "reason": "ok"}]}\n```'
    )
    fake_model = MagicMock()
    fake_model.ainvoke = AsyncMock(return_value=fake_response)
    with (
        patch.object(bc, "_embed", AsyncMock(return_value=[0.0] * 1536)),
        patch.object(bc, "create_chat_model", return_value=fake_model),
    ):
        out = await bc.search_relevant(pool, 1, "query", k=1)
    assert len(out) == 1
    # docs com doc_id=i (i in 0..4); reranker pediu idx=1 → docs[1] → doc_id=1
    assert out[0].documento.id == 1


@pytest.mark.asyncio
async def test_search_relevant_returns_empty_when_min_score_filters_all():
    rows = [_search_row(doc_id=1, score=0.1), _search_row(doc_id=2, score=0.2)]
    pool, _ = _mock_simple_pool(*rows, multi=True)
    with patch.object(bc, "_embed", AsyncMock(return_value=[0.0] * 1536)):
        out = await bc.search_relevant(pool, 1, "x", min_score=0.5)
    assert out == []


def test_vector_literal_format():
    assert bc._vector_literal([1, 2.5, 3]).startswith("[")
    assert bc._vector_literal([1, 2.5, 3]).endswith("]")
