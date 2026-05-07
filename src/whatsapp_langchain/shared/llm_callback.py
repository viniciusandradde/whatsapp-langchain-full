"""LangChain callback handler que registra ia_execucao + acrescenta budget.

Plugado via `config={"callbacks": [IaExecucaoCallback(...)]}` no graph.ainvoke.
Best-effort: falhas só logam, não interrompem o fluxo do agente.
"""

from __future__ import annotations

import time
from typing import Any
from uuid import UUID

import structlog
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.outputs import LLMResult
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.governanca_ia import (
    acrescentar_consumo,
    calc_custo,
    get_custo_modelo,
    registrar_execucao,
)

logger = structlog.get_logger()


class IaExecucaoCallback(AsyncCallbackHandler):
    """Callback handler que captura tokens + duração + custo de cada call LLM
    e registra em ia_execucao + atualiza ia_budget.

    Cria uma row de ia_execucao por on_llm_end. Tools chamadas dentro do
    grafo são capturadas via on_tool_end (se ocorrerem entre llm_start/end).
    """

    def __init__(
        self,
        pool: AsyncConnectionPool,
        *,
        empresa_id: int,
        atendimento_id: int | None = None,
        agente_ia_id: int | None = None,
    ) -> None:
        super().__init__()
        self.pool = pool
        self.empresa_id = empresa_id
        self.atendimento_id = atendimento_id
        self.agente_ia_id = agente_ia_id
        # Estado por run (LangChain re-usa instance entre calls; usamos
        # run_id como chave)
        self._starts: dict[UUID, float] = {}
        self._modelos: dict[UUID, tuple[str, str]] = {}
        self._tools_call: list[str] = []

    async def on_llm_start(
        self,
        serialized: dict,
        prompts: list[str],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        self._starts[run_id] = time.time()
        # Extrai modelo do serialized — formato típico:
        # serialized = {"id": ["langchain", "chat_models", ...], "kwargs": {"model_name": "..."}}
        kw = serialized.get("kwargs") or {}
        modelo = (
            kw.get("model_name")
            or kw.get("model")
            or kwargs.get("invocation_params", {}).get("model")
            or "?"
        )
        # Split provedor/nome — convenção OpenRouter "provedor/nome"
        if "/" in modelo:
            provedor, nome = modelo.split("/", 1)
        else:
            provedor, nome = "?", modelo
        self._modelos[run_id] = (provedor, nome)

    async def on_chat_model_start(
        self,
        serialized: dict,
        messages: list[list],
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        # Chat models seguem mesmo path; reusa on_llm_start
        await self.on_llm_start(serialized, [], run_id=run_id, **kwargs)

    async def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        start = self._starts.pop(run_id, None)
        provedor, nome = self._modelos.pop(run_id, ("?", "?"))
        duracao_ms = int((time.time() - start) * 1000) if start else None

        # Tokens — LangChain disponibiliza via response.llm_output['token_usage']
        # ou response.usage_metadata em modelos novos
        tokens_input = 0
        tokens_output = 0
        tokens_cached = 0
        if response.llm_output:
            usage = response.llm_output.get("token_usage") or {}
            tokens_input = usage.get("prompt_tokens", 0) or 0
            tokens_output = usage.get("completion_tokens", 0) or 0
            # OpenAI prompt cache
            cached = usage.get("prompt_tokens_details", {}) or {}
            tokens_cached = cached.get("cached_tokens", 0) or 0

        # Cálculo de custo (lookup cached por call — OK em escala
        # média; pode-se memoizar depois)
        custo_in, custo_out = await get_custo_modelo(
            self.pool, self.empresa_id, provedor, nome
        )
        custo_total = calc_custo(tokens_input, tokens_output, custo_in, custo_out)

        # Registra ia_execucao + atualiza budget
        tools_snap = list(self._tools_call)
        await registrar_execucao(
            self.pool,
            empresa_id=self.empresa_id,
            modelo_provedor=provedor,
            modelo_nome=nome,
            tokens_input=tokens_input,
            tokens_output=tokens_output,
            tokens_cached=tokens_cached,
            custo_total=custo_total,
            duracao_ms=duracao_ms,
            tools_chamadas=tools_snap,
            status="success",
            atendimento_id=self.atendimento_id,
            agente_ia_id=self.agente_ia_id,
        )
        if custo_total is not None and custo_total > 0:
            await acrescentar_consumo(self.pool, self.empresa_id, custo_total)
        # Reset tools snapshot pra próxima chamada
        self._tools_call = []

    async def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: UUID,
        **kwargs: Any,
    ) -> None:
        start = self._starts.pop(run_id, None)
        provedor, nome = self._modelos.pop(run_id, ("?", "?"))
        duracao_ms = int((time.time() - start) * 1000) if start else None
        await registrar_execucao(
            self.pool,
            empresa_id=self.empresa_id,
            modelo_provedor=provedor,
            modelo_nome=nome,
            duracao_ms=duracao_ms,
            status="error",
            erro_msg=str(error)[:500],
            atendimento_id=self.atendimento_id,
            agente_ia_id=self.agente_ia_id,
        )

    async def on_tool_start(
        self,
        serialized: dict,
        input_str: str,
        **kwargs: Any,
    ) -> None:
        nome = serialized.get("name") if serialized else "?"
        if nome:
            self._tools_call.append(str(nome))
