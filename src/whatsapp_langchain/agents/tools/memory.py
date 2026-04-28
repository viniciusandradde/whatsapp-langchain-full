"""Ferramentas de memória semântica para agentes.

Disponibiliza:
- save_memory: persiste informações importantes sobre o usuário.
- read_memory: recupera memórias relevantes por busca semântica.
"""

from typing import Annotated, Any
from uuid import uuid4

import structlog
from langchain_core.runnables.config import var_child_runnable_config
from langchain_core.tools import InjectedToolArg, tool
from langgraph.prebuilt import InjectedStore
from langgraph.store.base import BaseStore

from whatsapp_langchain.shared.config import settings

logger = structlog.get_logger()


def _extract_configurable(runtime: Any) -> dict:
    """Extrai `configurable` do contexto de execução da tool."""
    if runtime is not None:
        config = getattr(runtime, "config", None)
        if isinstance(config, dict):
            configurable = config.get("configurable", {})
            if isinstance(configurable, dict):
                return configurable

    cfg = var_child_runnable_config.get(None)
    if isinstance(cfg, dict):
        configurable = cfg.get("configurable", {})
        if isinstance(configurable, dict):
            return configurable

    return {}


def _extract_namespace(runtime: Any) -> tuple[tuple[str, str] | None, str | None]:
    """Resolve namespace de memória a partir do user_id."""
    configurable = _extract_configurable(runtime)
    user_id = configurable.get("user_id")
    if not user_id:
        return None, "user_id não encontrado na configuração."
    return (str(user_id), "memories"), None


@tool
async def save_memory(
    memory: str,
    *,
    runtime: Annotated[Any, InjectedToolArg()] = None,
    store: Annotated[BaseStore | None, InjectedStore()] = None,
) -> str:
    """Salva informação importante sobre o usuário para lembrar depois."""
    if store is None:
        return "Memória semântica não está disponível nesta sessão."

    namespace, error = _extract_namespace(runtime)
    if error:
        return error
    assert namespace is not None

    key = str(uuid4())
    await store.aput(namespace, key, {"memory": memory})
    logger.info("memory_saved", user_id=namespace[0], key=key, memory=memory)
    return "Memória salva com sucesso."


@tool
async def read_memory(
    query: str,
    limit: int | None = None,
    *,
    runtime: Annotated[Any, InjectedToolArg()] = None,
    store: Annotated[BaseStore | None, InjectedStore()] = None,
) -> str:
    """Busca memórias relevantes para a consulta atual."""
    if store is None:
        return "Memória semântica não está disponível nesta sessão."

    query = (query or "").strip()
    if not query:
        return "Forneça uma consulta de memória não vazia."

    namespace, error = _extract_namespace(runtime)
    if error:
        return error
    assert namespace is not None

    resolved_limit = settings.memory_search_limit if limit is None else limit
    safe_limit = max(1, min(resolved_limit, 10))

    try:
        results = await store.asearch(namespace, query=query, limit=safe_limit)
    except Exception as exc:
        logger.warning("memory_read_failed", namespace=namespace, error=str(exc))
        return "Falha ao buscar memórias no momento."

    if not results:
        return "Nenhuma memória relevante encontrada."

    memories: list[str] = []
    for item in results:
        value = item.value if hasattr(item, "value") else item
        if isinstance(value, dict):
            text = str(value.get("memory", value))
        else:
            text = str(value)
        text = text.strip()
        if text:
            memories.append(text)

    if not memories:
        return "Nenhuma memória relevante encontrada."

    logger.info("memory_read", user_id=namespace[0], count=len(memories))
    lines = ["Memórias relevantes encontradas:"]
    lines.extend(f"- {text}" for text in memories)
    return "\n".join(lines)
