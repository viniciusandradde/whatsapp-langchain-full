"""Eval framework pra RAG (Sprint N.3).

Roda contra `tests/rag/dataset/golden_qa.yaml` em 3 modos (vector, hybrid,
hybrid_hyde) e calcula:
  - hit@1: doc esperado é o top-1?
  - hit@5: doc esperado está no top-5?
  - must_contain_pass: snippets contém todas as strings exigidas?

Gera relatório JSON em `tests/reports/rag_eval/<timestamp>_<mode>.json`.

Uso:
    make test-rag-eval                   # roda os 3 modos
    pytest tests/rag/test_rag_eval.py    # idem
"""

from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path

import pytest
import yaml

DATASET = Path(__file__).parent / "dataset" / "golden_qa.yaml"
REPORTS_DIR = Path(__file__).resolve().parent.parent / "reports" / "rag_eval"

MODES = ["vector", "hybrid", "hybrid_hyde"]


def _load_dataset() -> list[dict]:
    if not DATASET.exists():
        pytest.skip(f"Dataset nao encontrado: {DATASET}")
    with DATASET.open() as f:
        data = yaml.safe_load(f) or {}
    return data.get("queries") or []


async def _run_query(qa: dict, mode: str, empresa_id: int) -> dict:
    from whatsapp_langchain.shared.base_conhecimento import search_relevant
    from whatsapp_langchain.shared.db import get_pool

    pool = await get_pool()
    pasta_ids = [qa["pasta_id"]] if qa.get("pasta_id") else None

    started = datetime.utcnow()
    try:
        results = await search_relevant(
            pool, empresa_id, qa["query"],
            pasta_ids=pasta_ids,
            mode=mode,
            rerank=True,
        )
    except Exception as e:
        return {
            "id": qa["id"],
            "query": qa["query"],
            "expected_doc_id": qa.get("expected_doc_id"),
            "mode": mode,
            "error": str(e)[:500],
            "hit@1": False,
            "hit@5": False,
            "must_contain_pass": False,
            "duration_ms": 0,
            "hits": [],
        }
    duration_ms = int((datetime.utcnow() - started).total_seconds() * 1000)

    expected = qa.get("expected_doc_id")
    hit_at_1 = bool(results and expected and results[0].documento.id == expected)
    hit_at_5 = bool(
        expected and any(r.documento.id == expected for r in results[:5])
    )

    must_contain = qa.get("must_contain") or []
    snippets_blob = " ".join(r.chunk_conteudo for r in results[:3]).lower()
    must_pass = (
        all(s.lower() in snippets_blob for s in must_contain)
        if must_contain else True
    )

    if expected is None:
        hit_at_1 = bool(results and results[0].score < 0.5)
        hit_at_5 = hit_at_1
        must_pass = True

    return {
        "id": qa["id"],
        "query": qa["query"],
        "expected_doc_id": expected,
        "mode": mode,
        "hit@1": hit_at_1,
        "hit@5": hit_at_5,
        "must_contain_pass": must_pass,
        "duration_ms": duration_ms,
        "hits": [
            {
                "doc_id": r.documento.id,
                "titulo": r.documento.titulo,
                "score": float(r.score),
            }
            for r in results[:5]
        ],
    }


def _aggregate(results: list[dict]) -> dict:
    n = len(results)
    if n == 0:
        return {"n": 0}
    return {
        "n": n,
        "hit@1": sum(1 for r in results if r["hit@1"]) / n,
        "hit@5": sum(1 for r in results if r["hit@5"]) / n,
        "must_contain_pass": sum(1 for r in results if r["must_contain_pass"]) / n,
        "errors": sum(1 for r in results if r.get("error")),
        "avg_duration_ms": sum(r["duration_ms"] for r in results) / n,
    }


@pytest.mark.parametrize("mode", MODES)
def test_rag_pipeline(mode: str) -> None:
    """Roda dataset golden e gera relatorio JSON por modo."""
    dataset = _load_dataset()
    if not dataset:
        pytest.skip("Dataset vazio")

    empresa_id = int(os.getenv("EVAL_EMPRESA_ID", "1"))

    async def run_all() -> list[dict]:
        out: list[dict] = []
        for qa in dataset:
            r = await _run_query(qa, mode, empresa_id)
            out.append(r)
        return out

    results = asyncio.run(run_all())
    summary = _aggregate(results)

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    report_path = REPORTS_DIR / f"{ts}_{mode}.json"
    report = {
        "mode": mode,
        "timestamp": ts,
        "empresa_id": empresa_id,
        "summary": summary,
        "results": results,
    }
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(
        f"\n[{mode}] hit@1={summary['hit@1']:.1%} hit@5={summary['hit@5']:.1%} "
        f"must={summary['must_contain_pass']:.1%} errs={summary['errors']} "
        f"-> {report_path}"
    )

    min_hit1 = float(os.getenv("RAG_EVAL_MIN_HIT1", "0.0"))
    assert summary["hit@1"] >= min_hit1, (
        f"hit@1 {summary['hit@1']:.1%} < min {min_hit1:.1%}"
    )
