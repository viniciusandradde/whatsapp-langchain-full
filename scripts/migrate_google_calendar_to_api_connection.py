"""One-shot: migra rows existentes de empresa_calendar_config → api_connection.

Idempotente: skip empresas que já têm api_connection google_calendar.
Cifra credenciais OAuth com Fernet (chave WARELINE_ENCRYPTION_KEY).

Uso:
    DATABASE_URL=$URL WARELINE_ENCRYPTION_KEY=$KEY \\
        uv run python scripts/migrate_google_calendar_to_api_connection.py

    # Dry-run:
    uv run python scripts/migrate_google_calendar_to_api_connection.py --dry-run

Roda em prod após deploy (uma vez só). Depois disso, novo OAuth callback
+ refresh token escrevem em AMBOS (dual-write) — eventual sprint futura
pode dropar empresa_calendar_config.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from whatsapp_langchain.integrations.google_calendar_storage import (  # noqa: E402
    migrate_legacy_to_api_connection,
)
from whatsapp_langchain.shared.db import close_pool, get_pool  # noqa: E402


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Lista rows que seriam migradas sem executar.",
    )
    args = parser.parse_args()

    pool = await get_pool()
    try:
        if args.dry_run:
            async with pool.connection() as conn:
                cur = await conn.execute(
                    """
                    SELECT ecc.empresa_id, ecc.google_email, ecc.ativo
                      FROM empresa_calendar_config ecc
                     WHERE NOT EXISTS (
                         SELECT 1 FROM api_connection ac
                          WHERE ac.empresa_id = ecc.empresa_id
                            AND ac.provider_slug = 'google_calendar'
                     )
                    """
                )
                rows = await cur.fetchall()
            print(f"\n[DRY-RUN] {len(rows)} rows seriam migradas:")
            for r in rows:
                print(f"  empresa_id={r[0]} email={r[1]} ativo={r[2]}")
            return

        result = await migrate_legacy_to_api_connection(pool)
        print("\n=== Resumo ===")
        print(f"  Total legacy candidatas: {result['total_legacy']}")
        print(f"  Migradas: {result['migrated']}")
        print(f"  Skipped (JSON inválido): {result['skipped']}")
    finally:
        await close_pool()


if __name__ == "__main__":
    asyncio.run(main())
