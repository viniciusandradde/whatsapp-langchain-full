"""Backfill manual de runs E2E históricos pra tabela test_run (Sprint L).

Pega artifacts em `tests/reports/{allure,allure-results,junit-e2e.xml}`
(se existirem) e cria um row em test_run + reorganiza pra `runs/{id}/`.

Idempotente: se já houver row com `error_message='backfill_sprint_k'`,
não duplica.

Uso:
    docker compose exec api python -m scripts.backfill_test_run_history
    # ou local:
    python scripts/backfill_test_run_history.py
"""

from __future__ import annotations

import asyncio
import os
import shutil
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

# Permite rodar standalone (fora do pacote)
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from whatsapp_langchain.shared.db import get_pool, close_pool


REPO_ROOT = Path(os.environ.get("TEST_RUNNER_REPO_ROOT", os.getcwd()))
REPORTS_DIR = REPO_ROOT / "tests" / "reports"
RUNS_DIR = REPORTS_DIR / "runs"


async def find_admin_user_id(pool) -> str | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            'SELECT id FROM auth."user" WHERE is_superadmin = TRUE '
            'ORDER BY "createdAt" ASC LIMIT 1'
        )
        row = await cur.fetchone()
    return row[0] if row else None


async def already_backfilled(pool) -> bool:
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT 1 FROM test_run WHERE error_message = 'backfill_sprint_k' LIMIT 1"
        )
        return await cur.fetchone() is not None


async def insert_run(
    pool,
    *,
    user_id: str | None,
    started_at: datetime,
    finished_at: datetime,
    status: str,
    total: int,
    passed: int,
    failed: int,
    duration: float,
    storage_path: str,
    log_size: int,
) -> int:
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            INSERT INTO test_run (
                started_by_user_id, started_at, finished_at, status,
                filtro, total, passed, failed, duration_seconds,
                storage_path, log_size_bytes, error_message
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (
                user_id, started_at, finished_at, status,
                None, total, passed, failed, duration,
                storage_path, log_size, "backfill_sprint_k",
            ),
        )
        row = await cur.fetchone()
        await conn.commit()
    assert row is not None
    return int(row[0])


async def main() -> int:
    junit = REPORTS_DIR / "junit-e2e.xml"
    allure_html = REPORTS_DIR / "allure"
    allure_results = REPORTS_DIR / "allure-results"

    if not junit.exists() or not allure_html.exists():
        print(f"[backfill] Sem artifacts em {REPORTS_DIR} — nada a fazer.")
        return 0

    pool = await get_pool()
    try:
        if await already_backfilled(pool):
            print("[backfill] Já existe row 'backfill_sprint_k' — skip.")
            return 0

        # Parse JUnit
        ts = ET.parse(junit).getroot().find("testsuite")
        if ts is None:
            print("[backfill] testsuite ausente em junit XML — abort.")
            return 1
        total = int(ts.get("tests") or 0)
        f1 = int(ts.get("failures") or 0)
        f2 = int(ts.get("errors") or 0)
        failed = f1 + f2
        passed = total - failed
        duration = float(ts.get("time") or 0)

        status = "passed" if failed == 0 else "failed"

        # Timestamps a partir do mtime do junit
        finished_ts = datetime.fromtimestamp(junit.stat().st_mtime).astimezone()
        started_ts = finished_ts - timedelta(seconds=duration)

        user_id = await find_admin_user_id(pool)

        # storage_path inicial — sem id, será atualizado depois
        run_id = await insert_run(
            pool,
            user_id=user_id,
            started_at=started_ts,
            finished_at=finished_ts,
            status=status,
            total=total,
            passed=passed,
            failed=failed,
            duration=duration,
            storage_path="",
            log_size=0,
        )

        # Mover artifacts pra runs/{run_id}/
        target = RUNS_DIR / str(run_id)
        target.mkdir(parents=True, exist_ok=True)

        # Copy allure/ (mantém original também — não destruir histórico)
        if (target / "allure").exists():
            shutil.rmtree(target / "allure")
        shutil.copytree(allure_html, target / "allure")

        if allure_results.exists():
            if (target / "allure-results").exists():
                shutil.rmtree(target / "allure-results")
            shutil.copytree(allure_results, target / "allure-results")

        # Copia junit
        shutil.copy(junit, target / "junit.xml")

        # Cria stdout.log placeholder
        stdout_log = target / "stdout.log"
        if not stdout_log.exists():
            stdout_log.write_text(
                f"[backfill] Run histórico do Sprint K — {total} cenários, "
                f"{passed}/{total} pass, duração {duration:.0f}s.\n"
                f"Logs originais não foram preservados (run rodado via "
                f"`make test-e2e` antes do test runner UI existir).\n"
            )

        log_size = stdout_log.stat().st_size
        storage_rel = f"tests/reports/runs/{run_id}"

        async with pool.connection() as conn:
            await conn.execute(
                "UPDATE test_run SET storage_path=%s, log_size_bytes=%s WHERE id=%s",
                (storage_rel, log_size, run_id),
            )
            await conn.commit()

        print(
            f"[backfill] OK — run #{run_id} criado. status={status} "
            f"{passed}/{total} duração={duration:.0f}s storage={storage_rel}"
        )
        return 0
    finally:
        await close_pool()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
