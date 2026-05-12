"""Runner — orquestra `process(atendimento_id, msg)` no worker.

PoC: SEM advisory lock (`pg_advisory_xact_lock` fica pra MVP #10).
SEM cache LRU de graphs compiled.

Fluxo:
1. Carrega `definicao_json` da workflow_chatbot_version ativa
2. Compila graph com checkpointer compartilhado
3. Se thread está em interrupt: `Command(resume=msg)`
   Senão: estado inicial
4. Coleta `result["__interrupt__"]` (próxima pergunta) + `outbox` (mensagens
   side-effect-after-interrupt)
5. Retorna lista de mensagens pro caller enviar via outbound
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.types import Command

from whatsapp_langchain.workflows.compiler import compile_workflow

logger = logging.getLogger(__name__)


class WorkflowRunner:
    """Wrap em torno de um graph compilado pra integração com worker.

    Não-thread-safe: cada chamada `process` carrega state via checkpointer
    que já é seguro pra concorrência interna.
    """

    def __init__(
        self,
        definicao: dict[str, Any],
        checkpointer: BaseCheckpointSaver,
        *,
        workflow_version_id: int = 0,
        pool: Any = None,
    ) -> None:
        """Args:
        definicao: dict com entry+nodes (single workflow, sem refs `wf:`)
        checkpointer: AsyncPostgresSaver / MemorySaver
        workflow_version_id: snapshot da version usada (Sprint v2 #5)
        pool: AsyncConnectionPool — necessário pros nodes que tocam DB
            (transfer_departamento, handover, delegate_to_agent, audit_event).
            None ⇒ esses nodes viram no-op (útil pra MemorySaver em tests).
        """
        self._graph = compile_workflow(definicao, checkpointer=checkpointer)
        self._workflow_version_id = workflow_version_id
        self._pool = pool

    async def process(
        self,
        *,
        atendimento_id: int,
        empresa_id: int,
        msg: str,
    ) -> list[dict[str, Any]]:
        """Processa 1 turn do workflow.

        Returns:
            Lista de mensagens a enviar ao cliente (cada item: dict com `kind`).
            Vazio quando workflow já terminou (END).
        """
        # Sprint v2 #10 — advisory lock por thread pra serializar workers
        # concorrentes processando mensagens do MESMO atendimento.
        if self._pool is not None:
            return await self._process_with_lock(atendimento_id, empresa_id, msg)
        return await self._process_inner(atendimento_id, empresa_id, msg)

    async def _process_with_lock(
        self, atendimento_id: int, empresa_id: int, msg: str
    ) -> list[dict[str, Any]]:
        """Wrap process() em pg_advisory_xact_lock pra evitar race
        multi-worker no mesmo thread (= mesmo atendimento)."""
        import hashlib

        thread_id = f"wf:{atendimento_id}"
        lock_key = int.from_bytes(
            hashlib.sha256(thread_id.encode()).digest()[:8],
            "big",
            signed=True,
        )
        async with self._pool.connection() as conn:
            async with conn.transaction():
                await conn.execute("SELECT pg_advisory_xact_lock(%s)", (lock_key,))
                return await self._process_inner(atendimento_id, empresa_id, msg)

    async def _process_inner(
        self, atendimento_id: int, empresa_id: int, msg: str
    ) -> list[dict[str, Any]]:
        """Lógica core sem lock (chamada via _process_with_lock ou direto)."""
        config: RunnableConfig = {
            "configurable": {"thread_id": f"wf:{atendimento_id}"},
        }

        # Pool não é msgpack-serializável → vai via configurable, não no state.
        # Nodes que precisam de DB leem via `config["configurable"]["pool"]`.
        if self._pool is not None:
            config["configurable"]["pool"] = self._pool

        # Verifica se já tem state (atendimento em curso)
        state_snapshot = await self._graph.aget_state(config)
        has_state = bool(state_snapshot.values)
        has_pending_task = bool(state_snapshot.tasks) if has_state else False
        is_terminal = has_state and not state_snapshot.next and not has_pending_task

        if is_terminal:
            logger.info("workflow_already_ended atendimento_id=%s", atendimento_id)
            return []

        if not has_state:
            input_payload: Any = {
                "atendimento_id": atendimento_id,
                "empresa_id": empresa_id,
                "workflow_version_id": self._workflow_version_id,
                "vars": {},
                "outbox": [],
                "history": [],
                "last_input": msg,
            }
        else:
            input_payload = Command(resume=msg)

        # Sprint v2 #2: usa `astream(stream_mode="updates")` pra pegar APENAS
        # os deltas do turn atual — evita ler `outbox` acumulado do checkpoint
        # (que duplicaria mensagens de turns anteriores).
        outgoing: list[dict[str, Any]] = []
        interrupt_value: Any = None
        async for chunk in self._graph.astream(
            input_payload, config=config, stream_mode="updates"
        ):
            for node_id, node_update in chunk.items():
                if node_id == "__interrupt__":
                    # node_update aqui é tuple/list de Interrupt objects
                    iv = (
                        node_update[0]
                        if isinstance(node_update, (list, tuple))
                        else node_update
                    )
                    interrupt_value = iv.value if hasattr(iv, "value") else iv
                    continue
                if isinstance(node_update, dict):
                    new_msgs = node_update.get("outbox") or []
                    outgoing.extend(new_msgs)

        # Converte interrupt em mensagem outbound
        if interrupt_value is not None:
            if isinstance(interrupt_value, dict):
                prompt = interrupt_value.get("prompt", "")
                kind = interrupt_value.get("kind", "ask")
                if kind == "ask_choice":
                    outgoing.append(
                        {
                            "kind": "text",
                            "text": prompt,
                            "choices": interrupt_value.get("choices"),
                        }
                    )
                else:
                    outgoing.append({"kind": "text", "text": prompt})
            else:
                outgoing.append({"kind": "text", "text": str(interrupt_value)})

        return outgoing
