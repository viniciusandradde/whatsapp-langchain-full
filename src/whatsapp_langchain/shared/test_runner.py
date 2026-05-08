"""Orquestracao de runs de testes E2E pelo painel admin (Sprint L).

Dispara `pytest tests/e2e/` em subprocess assincrono, persiste output em
`tests/reports/runs/{run_id}/`, e atualiza progresso em `test_run` table.

1 run por vez (guard via SELECT WHERE status IN running). Pra prod requer
`enable_test_runner=True` em settings (gate por env).
"""

from __future__ import annotations

import asyncio
import json
import os
import signal
import sys
import xml.etree.ElementTree as ET
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog
from psycopg_pool import AsyncConnectionPool

logger = structlog.get_logger()

_REPO_ROOT = Path(os.environ.get("TEST_RUNNER_REPO_ROOT", os.getcwd()))
_RUNS_DIR = _REPO_ROOT / "tests" / "reports" / "runs"


@dataclass
class TestRun:
    id: int
    started_by_user_id: str | None
    started_at: Any
    finished_at: Any
    status: str
    filtro: str | None
    total: int | None
    passed: int | None
    failed: int | None
    duration_seconds: float | None
    pid: int | None
    storage_path: str
    log_size_bytes: int
    error_message: str | None
    started_by_name: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "started_by_user_id": self.started_by_user_id,
            "started_by_name": self.started_by_name,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": (self.finished_at.isoformat() if self.finished_at else None),
            "status": self.status,
            "filtro": self.filtro,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "duration_seconds": (
                float(self.duration_seconds) if self.duration_seconds else None
            ),
            "pid": self.pid,
            "storage_path": self.storage_path,
            "log_size_bytes": self.log_size_bytes,
            "error_message": self.error_message,
        }


_COLS = (
    "tr.id, tr.started_by_user_id, tr.started_at, tr.finished_at, "
    "tr.status, tr.filtro, tr.total, tr.passed, tr.failed, "
    "tr.duration_seconds, tr.pid, tr.storage_path, tr.log_size_bytes, "
    "tr.error_message, u.name"
)


def _row_to_run(row) -> TestRun:
    return TestRun(
        id=row[0], started_by_user_id=row[1], started_at=row[2],
        finished_at=row[3], status=row[4], filtro=row[5], total=row[6],
        passed=row[7], failed=row[8], duration_seconds=row[9], pid=row[10],
        storage_path=row[11], log_size_bytes=row[12], error_message=row[13],
        started_by_name=row[14] if len(row) > 14 else None,
    )


async def has_running_run(pool: AsyncConnectionPool) -> bool:
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT 1 FROM test_run WHERE status IN ('queued','running') LIMIT 1"
        )
        return await cur.fetchone() is not None


async def start_run(
    pool: AsyncConnectionPool, *, user_id: str, filtro: str | None
) -> TestRun:
    if await has_running_run(pool):
        raise RuntimeError("Ja ha um run em andamento. Aguarde finalizar.")

    async with pool.connection() as conn:
        cur = await conn.execute(
            "INSERT INTO test_run (started_by_user_id, status, filtro, storage_path) "
            "VALUES (%s, 'queued', %s, '') RETURNING id",
            (user_id, filtro),
        )
        row = await cur.fetchone()
        await conn.commit()
    assert row is not None
    run_id = int(row[0])

    storage_path = f"tests/reports/runs/{run_id}"
    abs_path = _REPO_ROOT / storage_path
    abs_path.mkdir(parents=True, exist_ok=True)
    (abs_path / "allure-results").mkdir(exist_ok=True)
    (abs_path / "stdout.log").touch()
    _write_manifest(abs_path, status="queued", filtro=filtro)

    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE test_run SET storage_path = %s WHERE id = %s",
            (storage_path, run_id),
        )
        await conn.commit()

    asyncio.create_task(_spawn_pytest_async(pool, run_id, filtro, abs_path))
    return await get_run(pool, run_id)  # type: ignore[return-value]


def _write_manifest(abs_path: Path, **kwargs: Any) -> None:
    manifest_path = abs_path / "manifest.json"
    existing: dict[str, Any] = {}
    if manifest_path.exists():
        with suppress(Exception):
            existing = json.loads(manifest_path.read_text())
    existing.update(kwargs)
    existing["updated_at"] = datetime.now().isoformat()
    manifest_path.write_text(json.dumps(existing, indent=2, ensure_ascii=False))


async def _spawn_pytest_async(
    pool: AsyncConnectionPool, run_id: int, filtro: str | None, abs_path: Path,
) -> None:
    log_path = abs_path / "stdout.log"
    cmd = [
        sys.executable, "-m", "pytest", "tests/e2e/",
        f"--alluredir={abs_path}/allure-results",
        f"--junitxml={abs_path}/junit.xml",
        "-m", "docker_demo", "-v", "--tb=line",
        "-p", "no:cacheprovider",
    ]
    if filtro:
        cmd.extend(["-k", filtro])

    env = os.environ.copy()
    if not env.get("OPENROUTER_API_KEY"):
        env["SKIP_DEEPEVAL"] = "1"

    started_at = datetime.now()
    try:
        log_handle = open(log_path, "wb")
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(_REPO_ROOT),
            stdout=log_handle,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
        )
    except Exception as e:
        logger.error("test_runner_spawn_failed", run_id=run_id, error=str(e))
        await _mark_finished(
            pool, run_id, status="error",
            error_message=f"Falha ao iniciar pytest: {e}",
            duration_seconds=0,
        )
        return

    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE test_run SET status='running', pid=%s WHERE id=%s",
            (proc.pid, run_id),
        )
        await conn.commit()
    _write_manifest(abs_path, status="running", pid=proc.pid)
    logger.info("test_runner_started", run_id=run_id, pid=proc.pid, filtro=filtro)

    rc = await proc.wait()
    duration = (datetime.now() - started_at).total_seconds()

    total = passed = failed = None
    try:
        tree = ET.parse(abs_path / "junit.xml")
        ts = tree.getroot().find("testsuite")
        if ts is not None:
            total = int(ts.get("tests") or 0)
            failed = int(ts.get("failures") or 0) + int(ts.get("errors") or 0)
            passed = total - failed
    except Exception as e:
        logger.warning("test_runner_junit_parse_failed", run_id=run_id, error=str(e))

    if rc == 0 and (failed is None or failed == 0):
        final_status = "passed"
    elif failed is not None and failed > 0:
        final_status = "failed"
    else:
        final_status = "error"

    try:
        await _generate_allure_html(abs_path)
    except Exception as e:
        logger.warning("allure_generate_failed", run_id=run_id, error=str(e))

    log_size = log_path.stat().st_size if log_path.exists() else 0

    await _mark_finished(
        pool, run_id, status=final_status, total=total, passed=passed,
        failed=failed, duration_seconds=duration, log_size=log_size,
    )
    _write_manifest(
        abs_path, status=final_status, total=total, passed=passed,
        failed=failed, duration_seconds=duration, log_size=log_size,
    )
    logger.info(
        "test_runner_finished", run_id=run_id, status=final_status,
        total=total, passed=passed, failed=failed, duration_seconds=duration,
    )


async def _generate_allure_html(abs_path: Path) -> None:
    proc = await asyncio.create_subprocess_exec(
        "allure", "generate", str(abs_path / "allure-results"),
        "-o", str(abs_path / "allure"), "--clean",
        stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    if proc.returncode != 0:
        msg = stderr.decode(errors="ignore")[:200] if stderr else ""
        logger.warning("allure_cli_failed", returncode=proc.returncode, error=msg)


async def _mark_finished(
    pool: AsyncConnectionPool, run_id: int, *, status: str,
    total: int | None = None, passed: int | None = None,
    failed: int | None = None, duration_seconds: float | None = None,
    log_size: int = 0, error_message: str | None = None,
) -> None:
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE test_run SET status=%s, finished_at=NOW(), "
            "total=COALESCE(%s, total), passed=COALESCE(%s, passed), "
            "failed=COALESCE(%s, failed), "
            "duration_seconds=COALESCE(%s, duration_seconds), "
            "log_size_bytes=%s, error_message=COALESCE(%s, error_message) "
            "WHERE id=%s",
            (status, total, passed, failed, duration_seconds, log_size,
             error_message, run_id),
        )
        await conn.commit()


async def kill_run(pool: AsyncConnectionPool, run_id: int) -> bool:
    run = await get_run(pool, run_id)
    if not run or not run.pid or run.status not in ("queued", "running"):
        return False
    try:
        os.kill(run.pid, signal.SIGTERM)
        logger.info("test_runner_kill_sent", run_id=run_id, pid=run.pid)
        return True
    except ProcessLookupError:
        await _mark_finished(
            pool, run_id, status="error",
            error_message="Processo terminou inesperadamente",
        )
        return False


async def get_run(pool: AsyncConnectionPool, run_id: int) -> TestRun | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f'SELECT {_COLS} FROM test_run tr '
            'LEFT JOIN auth."user" u ON u.id = tr.started_by_user_id '
            'WHERE tr.id = %s',
            (run_id,),
        )
        row = await cur.fetchone()
    return _row_to_run(row) if row else None


async def list_runs(pool: AsyncConnectionPool, limit: int = 50) -> list[TestRun]:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f'SELECT {_COLS} FROM test_run tr '
            'LEFT JOIN auth."user" u ON u.id = tr.started_by_user_id '
            'ORDER BY tr.id DESC LIMIT %s',
            (limit,),
        )
        rows = await cur.fetchall()
    return [_row_to_run(r) for r in rows]


def tail_log(run_id: int, offset: int = 0, max_bytes: int = 65536) -> tuple[str, int]:
    log_path = _RUNS_DIR / str(run_id) / "stdout.log"
    if not log_path.exists():
        return ("", offset)
    size = log_path.stat().st_size
    if offset >= size:
        return ("", offset)
    with log_path.open("rb") as f:
        f.seek(offset)
        chunk = f.read(min(max_bytes, size - offset))
    return (chunk.decode("utf-8", errors="replace"), offset + len(chunk))


def get_report_path(run_id: int, sub: str = "index.html") -> Path | None:
    base = _RUNS_DIR / str(run_id) / "allure"
    if not base.exists():
        return None
    candidate = (base / sub).resolve()
    try:
        candidate.relative_to(base.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None
