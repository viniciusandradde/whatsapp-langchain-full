"""Sprint T.1 — Sincroniza fewshots da sandbox pro LangSmith.

Cópia normalizada (não migra): fewshot_example continua sendo fonte de
verdade local. LangSmith vira mirror externo pra análise + eval.

Idempotente via metadata.fewshot_id.

Uso:
    LANGCHAIN_API_KEY=ls_... python scripts/sync_dataset_to_langsmith.py [--dry-run] [--filter-success]
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from whatsapp_langchain.shared.db import close_pool, get_pool
from whatsapp_langchain.shared.langsmith_sync import (
    DEFAULT_DATASET_NAME,
    sync_to_langsmith,
)


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--empresa-id", type=int, default=999)
    parser.add_argument("--dataset-name", default=DEFAULT_DATASET_NAME)
    parser.add_argument(
        "--filter-success",
        action="store_true",
        help="Só sincroniza outcome=success (curado, ~2.5k vs 9k)",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--batch", type=int, default=200)
    args = parser.parse_args()

    api_key = os.environ.get("LANGCHAIN_API_KEY") or os.environ.get("LANGSMITH_API_KEY")
    if not api_key:
        print(
            "ERRO: LANGCHAIN_API_KEY (ou LANGSMITH_API_KEY) não setada.",
            file=sys.stderr,
        )
        return 2

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    print("=== Sprint T.1 LangSmith Sync ===")
    print(f"empresa_id: {args.empresa_id}")
    print(f"dataset: {args.dataset_name}")
    print(f"filter_success: {args.filter_success}")
    print(f"dry_run: {args.dry_run}")
    print()

    pool = await get_pool()
    try:
        result = await sync_to_langsmith(
            pool,
            api_key=api_key,
            empresa_id=args.empresa_id,
            dataset_name=args.dataset_name,
            filter_success=args.filter_success,
            dry_run=args.dry_run,
            batch_size=args.batch,
        )
    finally:
        await close_pool()

    print()
    print("=== RESULT ===")
    print(f"  total_db:       {result.total_db}")
    print(f"  already_synced: {result.already_synced}")
    print(f"  created:        {result.created}")
    print(f"  errors:         {len(result.errors)}")
    if result.errors:
        for e in result.errors[:5]:
            print(f"    - {e}")
    print(f"  dataset_id:  {result.dataset_id}")
    print(f"  dataset_url: {result.dataset_url}")
    return 0 if not result.errors else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
