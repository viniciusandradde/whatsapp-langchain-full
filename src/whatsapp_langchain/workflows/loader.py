"""Loader: lê `workflow_chatbot` ativo da empresa + monta runner.

Cache LRU pequeno por (empresa_id, version_id) — workflow é determinístico,
mesma version gera mesmo graph.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any

from whatsapp_langchain.workflows.runner import WorkflowRunner

logger = logging.getLogger(__name__)


async def load_active_workflow(
    pool: Any, empresa_id: int
) -> tuple[int, dict[str, Any]] | None:
    """Lê o workflow_chatbot principal ativo da empresa.

    Retorna `(version_id, definicao_json)` ou None se nenhum ativo.

    Convenção: workflow "principal" tem `slug='menu_principal'` (mig 076).
    Se houver versao_ativa_id, carrega da workflow_chatbot_version
    (imutável). Senão lê direto da `workflow_chatbot.definicao` (draft).
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT id, slug, definicao, versao_ativa_id, versao
              FROM workflow_chatbot
             WHERE empresa_id = %s AND ativo = TRUE AND slug = 'menu_principal'
             LIMIT 1
            """,
            (empresa_id,),
        )
        row = await cur.fetchone()
        if row is None:
            return None
        wf_id, _slug, definicao, versao_ativa_id, versao = row

        # Se versao_ativa_id existe, prefere a versão imutável (#5)
        version_id_to_use = versao_ativa_id or 0
        if versao_ativa_id:
            cur = await conn.execute(
                "SELECT id, definicao FROM workflow_chatbot_version WHERE id = %s",
                (versao_ativa_id,),
            )
            v_row = await cur.fetchone()
            if v_row is not None:
                version_id_to_use = v_row[0]
                definicao = v_row[1]

        # JSONB pode vir como dict ou str dependendo do psycopg
        if isinstance(definicao, str):
            definicao = json.loads(definicao)
        return version_id_to_use, definicao


async def get_workflow_state_snapshot(
    pool: Any,
    checkpointer: Any,
    atendimento_id: int,
    empresa_id: int,
) -> dict[str, Any] | None:
    """Retorna snapshot do state do workflow pra um atendimento.

    Útil pra debug L2 — admin abre o drawer e vê em que node o cliente
    travou, quais vars já foram coletadas, qual interrupt está pendente.

    Returns:
        None se atendimento não tem workflow ativo nem state salvo.
        Dict com:
            - current_nodes: list[str] (state.next)
            - vars: dict (sem _pool helper)
            - history: list[str]
            - interrupt_pending: dict | None (payload do interrupt)
            - workflow_version_id: int
            - events: list[dict] (últimos 20 de workflow_evento)
            - is_terminal: bool
    """
    runner = await build_runner_for_empresa(pool, checkpointer, empresa_id)
    if runner is None:
        return None

    config = {"configurable": {"thread_id": f"wf:{atendimento_id}"}}
    snapshot = await runner._graph.aget_state(config)
    if not snapshot.values:
        return None

    vars_clean = {
        k: v
        for k, v in (snapshot.values.get("vars") or {}).items()
        if not k.startswith("_")
    }

    # Detecta interrupt pendente via state.tasks
    interrupt_pending = None
    if snapshot.tasks:
        for task in snapshot.tasks:
            interrupts = getattr(task, "interrupts", None)
            if interrupts:
                iv = interrupts[0]
                interrupt_pending = getattr(iv, "value", iv)
                break

    # Últimos eventos do workflow_evento
    events: list[dict] = []
    try:
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT node_id, evento, payload, created_at
                  FROM workflow_evento
                 WHERE atendimento_id = %s
                 ORDER BY created_at DESC
                 LIMIT 20
                """,
                (atendimento_id,),
            )
            rows = await cur.fetchall()
            events = [
                {
                    "node_id": r[0],
                    "evento": r[1],
                    "payload": r[2],
                    "created_at": r[3].isoformat() if r[3] else None,
                }
                for r in rows
            ]
    except Exception as exc:  # noqa: BLE001
        logger.warning("workflow_state_events_load_failed err=%s", exc)

    is_terminal = (
        bool(snapshot.values)
        and not snapshot.next
        and not snapshot.tasks
    )

    return {
        "atendimento_id": atendimento_id,
        "current_nodes": list(snapshot.next) if snapshot.next else [],
        "vars": vars_clean,
        "history": snapshot.values.get("history") or [],
        "interrupt_pending": interrupt_pending,
        "workflow_version_id": snapshot.values.get("workflow_version_id", 0),
        "is_terminal": is_terminal,
        "events": events,
    }


async def build_runner_for_empresa(
    pool: Any,
    checkpointer: Any,
    empresa_id: int,
) -> WorkflowRunner | None:
    """High-level: carrega workflow ativo + retorna runner pronto pra
    `process(...)`. Returns None se empresa não tem workflow ativo.
    """
    loaded = await load_active_workflow(pool, empresa_id)
    if loaded is None:
        return None
    version_id, definicao = loaded
    return WorkflowRunner(
        definicao,
        checkpointer=checkpointer,
        workflow_version_id=version_id,
        pool=pool,
    )


# Cache LRU não-async pra evitar recompile a cada turno — a key inclui o
# `version_id` que é imutável.
@lru_cache(maxsize=64)
def _cached_compile_key(empresa_id: int, version_id: int) -> tuple[int, int]:
    """Apenas hash key. O compile real fica no `build_runner_for_empresa`."""
    return (empresa_id, version_id)
