"""Cleanup automático de atendimentos zumbis.

Atendimentos `aguardando` ou `em_andamento` que ficam parados por mais
tempo que o threshold são auto-fechados como `abandonado`. Sem isso a
fila acumula histórico zumbi (ex: empresa 1 com 133 aguardando, alguns
de 19k min = 13 dias).

Thresholds defaults (config global do código):
- aguardando > 48h sem nenhum atendimento → abandonado
- em_andamento > 24h sem mensagem nova do cliente → abandonado

Override por empresa via `empresa.config['cleanup_atendimento']`:
```json
{
  "dias_max_aguardando": 2,        // em dias (decimal aceito: 0.5 = 12h)
  "dias_max_sem_resposta": 1,
  "enabled": true                  // false desativa cleanup pra essa empresa
}
```

Rotina dispara via worker periódico (a cada 6h) + endpoint admin manual.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog
from psycopg_pool import AsyncConnectionPool

logger = structlog.get_logger()


# Defaults conservadores aplicados quando empresa.config não tem override
DEFAULT_DIAS_MAX_AGUARDANDO = 2.0  # 48h
DEFAULT_DIAS_MAX_SEM_RESPOSTA = 1.0  # 24h


async def get_cleanup_config(
    pool: AsyncConnectionPool, empresa_id: int
) -> dict[str, Any]:
    """Lê config de cleanup da empresa. Retorna defaults se não setado.

    Returns dict com `enabled`, `dias_max_aguardando`, `dias_max_sem_resposta`.
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT COALESCE(config, '{}'::jsonb) FROM empresa WHERE id = %s",
            (empresa_id,),
        )
        row = await cur.fetchone()

    config = (row[0] if row else None) or {}
    cleanup = config.get("cleanup_atendimento") or {}

    return {
        "enabled": cleanup.get("enabled", True),
        "dias_max_aguardando": float(
            cleanup.get("dias_max_aguardando", DEFAULT_DIAS_MAX_AGUARDANDO)
        ),
        "dias_max_sem_resposta": float(
            cleanup.get("dias_max_sem_resposta", DEFAULT_DIAS_MAX_SEM_RESPOSTA)
        ),
    }


async def preview_zumbis(
    pool: AsyncConnectionPool, empresa_id: int
) -> dict[str, Any]:
    """Conta atendimentos que SERIAM fechados se cleanup rodasse agora.

    Não modifica nada. Usado pelo dashboard pra mostrar contador + endpoint
    admin pra preview antes do execute.
    """
    config = await get_cleanup_config(pool, empresa_id)
    if not config["enabled"]:
        return {
            "enabled": False,
            "aguardando_zumbi": 0,
            "em_andamento_zumbi": 0,
            "total": 0,
            "config": config,
        }

    dias_aguard = config["dias_max_aguardando"]
    dias_resp = config["dias_max_sem_resposta"]

    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT
                COUNT(*) FILTER (
                    WHERE status = 'aguardando'
                      AND last_message_at < NOW() - (%s || ' days')::INTERVAL
                ) AS aguardando_zumbi,
                COUNT(*) FILTER (
                    WHERE status = 'em_andamento'
                      AND last_message_at < NOW() - (%s || ' days')::INTERVAL
                ) AS em_andamento_zumbi
              FROM atendimento
             WHERE empresa_id = %s
               AND status IN ('aguardando', 'em_andamento')
            """,
            (str(dias_aguard), str(dias_resp), empresa_id),
        )
        row = await cur.fetchone()

    aguard = int(row[0] or 0) if row else 0
    resp = int(row[1] or 0) if row else 0

    return {
        "enabled": True,
        "aguardando_zumbi": aguard,
        "em_andamento_zumbi": resp,
        "total": aguard + resp,
        "config": config,
    }


async def cleanup_zumbis(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    dry_run: bool = False,
    motivo: str = "cleanup_auto",
) -> dict[str, Any]:
    """Fecha atendimentos zumbis como `abandonado`.

    Marca:
    - status = 'abandonado'
    - closed_at = NOW()
    - finalizado_por_user_id = 'system:cleanup' (mig 047)
    - audit via dispatch_event('atendimento.fechado') com motivo

    Args:
        dry_run: True = só conta, não modifica
        motivo: tag pra logs/audit ('cleanup_auto' = cron; 'cleanup_manual' = admin)

    Returns: dict com stats {aguardando_fechados, em_andamento_fechados, ids}
    """
    config = await get_cleanup_config(pool, empresa_id)
    if not config["enabled"]:
        logger.info("cleanup_skipped_disabled", empresa_id=empresa_id)
        return {
            "enabled": False,
            "aguardando_fechados": 0,
            "em_andamento_fechados": 0,
            "total": 0,
            "dry_run": dry_run,
        }

    dias_aguard = config["dias_max_aguardando"]
    dias_resp = config["dias_max_sem_resposta"]

    if dry_run:
        preview = await preview_zumbis(pool, empresa_id)
        return {
            "enabled": True,
            "aguardando_fechados": preview["aguardando_zumbi"],
            "em_andamento_fechados": preview["em_andamento_zumbi"],
            "total": preview["total"],
            "dry_run": True,
            "config": config,
        }

    closed_ids_aguard: list[int] = []
    closed_ids_resp: list[int] = []

    async with pool.connection() as conn:
        # Fecha aguardando zumbi
        cur = await conn.execute(
            """
            UPDATE atendimento
               SET status = 'abandonado',
                   closed_at = NOW(),
                   finalizado_por_user_id = 'system:cleanup',
                   updated_at = NOW()
             WHERE empresa_id = %s
               AND status = 'aguardando'
               AND last_message_at < NOW() - (%s || ' days')::INTERVAL
            RETURNING id
            """,
            (empresa_id, str(dias_aguard)),
        )
        rows = await cur.fetchall()
        closed_ids_aguard = [int(r[0]) for r in rows]

        # Fecha em_andamento zumbi
        cur = await conn.execute(
            """
            UPDATE atendimento
               SET status = 'abandonado',
                   closed_at = NOW(),
                   finalizado_por_user_id = 'system:cleanup',
                   updated_at = NOW()
             WHERE empresa_id = %s
               AND status = 'em_andamento'
               AND last_message_at < NOW() - (%s || ' days')::INTERVAL
            RETURNING id
            """,
            (empresa_id, str(dias_resp)),
        )
        rows = await cur.fetchall()
        closed_ids_resp = [int(r[0]) for r in rows]

        await conn.commit()

    total = len(closed_ids_aguard) + len(closed_ids_resp)
    logger.info(
        "cleanup_zumbis_executed",
        empresa_id=empresa_id,
        aguardando_fechados=len(closed_ids_aguard),
        em_andamento_fechados=len(closed_ids_resp),
        total=total,
        motivo=motivo,
    )

    # Dispatch evento atendimento.fechado pra cada (hooks externos opcionais)
    if total > 0:
        try:
            from whatsapp_langchain.shared.hook_dispatcher import dispatch_event

            for atend_id in closed_ids_aguard + closed_ids_resp:
                await dispatch_event(
                    pool,
                    empresa_id,
                    "atendimento.fechado",
                    {
                        "atendimento_id": atend_id,
                        "status": "abandonado",
                        "motivo": motivo,
                        "fechado_por": "system:cleanup",
                        "closed_at": datetime.now(UTC).isoformat(),
                    },
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "cleanup_dispatch_failed",
                empresa_id=empresa_id,
                error=str(exc),
            )

    return {
        "enabled": True,
        "aguardando_fechados": len(closed_ids_aguard),
        "em_andamento_fechados": len(closed_ids_resp),
        "total": total,
        "dry_run": False,
        "config": config,
        "ids": closed_ids_aguard + closed_ids_resp,
    }


async def cleanup_zumbis_all_empresas(
    pool: AsyncConnectionPool,
    *,
    motivo: str = "cleanup_auto",
) -> dict[str, Any]:
    """Roda cleanup pra TODAS as empresas ativas. Usado pelo cron.

    Pula empresas com `cleanup_atendimento.enabled = false` na config.
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT id FROM empresa WHERE status = 'active' ORDER BY id",
        )
        rows = await cur.fetchall()

    empresa_ids = [int(r[0]) for r in rows]
    results: list[dict[str, Any]] = []
    total_fechados = 0

    for eid in empresa_ids:
        try:
            r = await cleanup_zumbis(pool, eid, motivo=motivo)
            results.append({"empresa_id": eid, **r})
            total_fechados += r.get("total", 0)
        except Exception as exc:  # noqa: BLE001
            logger.warning("cleanup_empresa_failed", empresa_id=eid, error=str(exc))
            results.append({"empresa_id": eid, "error": str(exc)})

    logger.info(
        "cleanup_all_empresas_done",
        empresas=len(empresa_ids),
        total_fechados=total_fechados,
    )
    return {
        "empresas_processadas": len(empresa_ids),
        "total_fechados": total_fechados,
        "by_empresa": results,
    }
