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
