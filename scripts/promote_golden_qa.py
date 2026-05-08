"""Sprint P.4 — Auto-evolução do dataset golden.

Lê queries reais com outcome conhecido e propõe atualizações pro YAML golden:
- outcome=success + alta similaridade com docs reais → promove pra golden
- outcome=transferred/escalated → adiciona como caso "a corrigir"

Roda standalone via:
    python scripts/promote_golden_qa.py [--dry-run] [--days 30]

Idempotente: skip queries cujo texto já existe no golden_qa.yaml.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from whatsapp_langchain.shared.db import close_pool, get_pool

GOLDEN_PATH = (
    Path(__file__).parent.parent / "tests" / "rag" / "dataset" / "golden_qa.yaml"
)


async def fetch_promotion_candidates(pool, empresa_id: int, days: int) -> list[dict]:
    """Queries reais com outcome=success E hits>0 nos últimos N dias."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT DISTINCT ON (query_text)
              query_text, agente_slug, pasta_ids, top_score,
              outcome, created_at
            FROM rag_query_log
            WHERE empresa_id = %s
              AND created_at > NOW() - INTERVAL '%s days'
              AND outcome = 'success'
              AND hits > 0
              AND top_score > 0.5
              AND char_length(query_text) BETWEEN 8 AND 200
            ORDER BY query_text, created_at DESC
            LIMIT 100
            """,
            (empresa_id, days),
        )
        return [
            {
                "query": r[0],
                "setor": r[1],
                "pasta_id": int(r[2][0]) if r[2] else None,
                "score": float(r[3]) if r[3] else None,
                "outcome": r[4],
            }
            for r in await cur.fetchall()
        ]


async def fetch_correction_candidates(pool, empresa_id: int, days: int) -> list[dict]:
    """Queries com outcome ruim — adicionadas como TODOs."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT DISTINCT ON (query_text)
              query_text, agente_slug, pasta_ids, hits, outcome
            FROM rag_query_log
            WHERE empresa_id = %s
              AND created_at > NOW() - INTERVAL '%s days'
              AND outcome IN ('transferred','escalated','abandoned')
              AND char_length(query_text) BETWEEN 8 AND 200
            ORDER BY query_text, created_at DESC
            LIMIT 50
            """,
            (empresa_id, days),
        )
        return [
            {
                "query": r[0], "setor": r[1],
                "pasta_id": int(r[2][0]) if r[2] else None,
                "hits": int(r[3]),
                "outcome": r[4],
            }
            for r in await cur.fetchall()
        ]


def load_existing(path: Path) -> tuple[dict, set[str]]:
    if not path.exists():
        return {"queries": []}, set()
    with path.open() as f:
        data = yaml.safe_load(f) or {"queries": []}
    existing = {q["query"].strip().lower() for q in data.get("queries", [])}
    return data, existing


def append_promotions(data: dict, candidates: list[dict], existing: set[str]) -> int:
    added = 0
    for c in candidates:
        if c["query"].strip().lower() in existing:
            continue
        new_id = f"auto-{c['setor']}-{added + len(data['queries']) + 1}"
        data["queries"].append({
            "id": new_id,
            "setor": c["setor"],
            "pasta_id": c["pasta_id"],
            "query": c["query"],
            "expected_doc_id": None,
            "must_contain": [],
            "auto_imported": True,
            "score_observed": c["score"],
        })
        existing.add(c["query"].strip().lower())
        added += 1
    return added


def append_corrections(data: dict, candidates: list[dict], existing: set[str]) -> int:
    """Adiciona casos a corrigir como expected_doc_id=null + outcome=transferred."""
    added = 0
    for c in candidates:
        if c["query"].strip().lower() in existing:
            continue
        new_id = f"todo-{c['setor']}-{added + len(data['queries']) + 1}"
        data["queries"].append({
            "id": new_id,
            "setor": c["setor"],
            "pasta_id": c["pasta_id"],
            "query": c["query"],
            "expected_doc_id": None,
            "must_contain": [],
            "todo_correction": True,
            "outcome_observed": c["outcome"],
            "hits_observed": c["hits"],
        })
        existing.add(c["query"].strip().lower())
        added += 1
    return added


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--empresa-id", type=int,
                        default=int(os.environ.get("EMPRESA_ID", "1")))
    args = parser.parse_args()

    pool = await get_pool()
    try:
        promotions = await fetch_promotion_candidates(pool, args.empresa_id, args.days)
        corrections = await fetch_correction_candidates(pool, args.empresa_id, args.days)
    finally:
        await close_pool()

    data, existing = load_existing(GOLDEN_PATH)

    added_p = append_promotions(data, promotions, existing)
    added_c = append_corrections(data, corrections, existing)

    print(f"Candidatos sucesso: {len(promotions)} → adicionados {added_p}")
    print(f"Casos a corrigir:   {len(corrections)} → adicionados {added_c}")
    print(f"Total no dataset:   {len(data['queries'])}")

    if args.dry_run:
        print("[dry-run] não escreveu arquivo")
        return 0

    if added_p == 0 and added_c == 0:
        print("nada novo pra adicionar")
        return 0

    GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    with GOLDEN_PATH.open("w") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False, width=200)
    print(f"escrito: {GOLDEN_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
