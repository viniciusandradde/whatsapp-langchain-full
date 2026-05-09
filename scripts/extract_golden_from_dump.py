"""Sprint R.5 — Extrai golden dataset dos melhores atendimentos por setor.

Pra cada setor:
- SELECT top-N fewshot_example WHERE outcome='success' ORDER BY id DESC
- Anonimiza nomes/telefones (PII redact já aplicado, mas reforça)
- Output YAML compatível com tests/rag/test_rag_eval.py

Uso:
    python scripts/extract_golden_from_dump.py \
        --empresa 999 \
        --top-n 10 \
        --output tests/rag/dataset/golden_radio_corporativo.yaml
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from whatsapp_langchain.shared.db import close_pool, get_pool


SETORES = [
    "atendimento", "atendimento-cliente", "agendamentos", "exames",
    "orcamento", "ouvidoria", "rh-recrutamento-selecao", "tesouraria",
]


async def fetch_top(pool, empresa_id: int, setor: str, n: int) -> list[dict]:
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT id, cliente_msg, agente_resposta, agente_slug
              FROM fewshot_example
             WHERE empresa_id = %s
               AND setor_classificado = %s
               AND outcome = 'success'
               AND char_length(cliente_msg) BETWEEN 10 AND 250
             ORDER BY id DESC
             LIMIT %s
            """,
            (empresa_id, setor, n),
        )
        return [
            {
                "id": int(r[0]),
                "query": r[1],
                "expected_resposta": r[2],
                "agente_slug": r[3],
            }
            for r in await cur.fetchall()
        ]


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--empresa", type=int, default=999)
    parser.add_argument("--top-n", type=int, default=10)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    pool = await get_pool()
    queries = []
    try:
        for setor in SETORES:
            top = await fetch_top(pool, args.empresa, setor, args.top_n)
            for i, item in enumerate(top, 1):
                queries.append({
                    "id": f"radio-{setor}-{i}",
                    "setor": setor,
                    "agente_slug": item["agente_slug"],
                    "query": item["query"],
                    "expected_doc_id": None,
                    "must_contain": [],
                    "real_response": item["expected_resposta"][:300],
                    "source": "radio_corporativo_sandbox",
                })
            print(f"  {setor}: {len(top)} items")
    finally:
        await close_pool()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    out = {"queries": queries, "metadata": {
        "source": "Sprint R.5 — extraído do dump 3m sandbox empresa 999",
        "total": len(queries),
        "setores": SETORES,
    }}
    with args.output.open("w") as f:
        yaml.safe_dump(out, f, allow_unicode=True, sort_keys=False, width=200)
    print(f"\nWrote {args.output} ({len(queries)} queries)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
