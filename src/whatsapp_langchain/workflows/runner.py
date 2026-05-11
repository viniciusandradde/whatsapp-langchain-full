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
    ) -> None:
        self._graph = compile_workflow(definicao, checkpointer=checkpointer)
        self._workflow_version_id = workflow_version_id

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
        config: RunnableConfig = {
            "configurable": {"thread_id": f"wf:{atendimento_id}"},
        }

        # Verifica se já tem state (atendimento em curso)
        state_snapshot = await self._graph.aget_state(config)
        has_state = bool(state_snapshot.values)
        # Detecção de "workflow terminou": NÃO tem state.next nem state.tasks
        # pendentes. Re-interrupt no mesmo node não popula state.next mas mantém
        # state.tasks — precisa checar ambos.
        has_pending_task = bool(state_snapshot.tasks) if has_state else False
        is_terminal = has_state and not state_snapshot.next and not has_pending_task

        if is_terminal:
            logger.info("workflow_already_ended atendimento_id=%s", atendimento_id)
            return []

        if not has_state:
            # Primeiro turn: passa estado inicial
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
            # Retomada: envia msg como resposta do interrupt pendente
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
