"""One-shot CLI pra migrar docs de M5.c → M5.c.1 (chunks).

Uso:
    uv run python scripts/backfill_rag_chunks.py            # backfill completo
    uv run python scripts/backfill_rag_chunks.py --doc-id 1 # 1 doc específico

Idempotente: docs que já têm chunks são pulados. Útil em produção depois
de aplicar a migration 018, ou pra recuperar embeddings de docs cujos
chunks foram apagados manualmente.

Roda contra o `DATABASE_URL` do .env / compose. Cada chunk dispara 1
chamada de embedding pro OpenRouter — custo por chunk é baixo
(~$0.00002 cada com text-embedding-3-small) mas ainda contribui pro rate
limit, então rode em horário tranquilo se a base for grande.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import structlog

from whatsapp_langchain.shared import base_conhecimento as bc
from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.db import close_pool, get_pool
from whatsapp_langchain.shared.observability import setup_logging


logger = structlog.get_logger()


async def main(only_doc_id: int | None) -> int:
    setup_logging(log_level=settings.log_level, json_output=False)
    pool = await get_pool()
    try:
        counters = await bc.backfill_chunks(pool, only_doc_id=only_doc_id)
    finally:
        await close_pool()
    print(  # noqa: T201
        f"processed={counters['processed']} "
        f"skipped={counters['skipped']} "
        f"failed={counters['failed']}"
    )
    return 0 if counters["failed"] == 0 else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--doc-id",
        type=int,
        default=None,
        help="Força re-indexar APENAS esse doc (vs todos sem chunks)",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(main(only_doc_id=args.doc_id)))
