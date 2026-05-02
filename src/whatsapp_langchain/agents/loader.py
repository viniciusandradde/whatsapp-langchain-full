"""Carregador dinâmico de agentes.

Importa agentes do catálogo em tempo de execução, permitindo que a API
e o Worker carreguem qualquer agente registrado pelo nome.

Cada agente deve ter um arquivo agent.py com a função build_graph()
no diretório agents/catalog/{agent_id}/.

Uso:
    from whatsapp_langchain.agents.loader import load_graph, list_agents

    graph = load_graph("vsa_tech", checkpointer=saver)
    agents = list_agents()  # ["vsa_tech"]
"""

import importlib
from pathlib import Path

import structlog
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.agente_ia import resolve_runtime_config
from whatsapp_langchain.shared.base_conhecimento import has_active_documents
from whatsapp_langchain.shared.calendar_integration import get_calendar_config
from whatsapp_langchain.shared.llm import get_agent_llm_config

logger = structlog.get_logger()

# Diretório do catálogo de agentes
CATALOG_DIR = Path(__file__).parent / "catalog"


class AgentNotFoundError(Exception):
    """Erro quando um agent_id não existe no catálogo.

    Exemplo:
        try:
            graph = load_graph("agente_inexistente")
        except AgentNotFoundError as e:
            print(e.agent_id)  # "agente_inexistente"
    """

    def __init__(self, agent_id: str):
        self.agent_id = agent_id
        super().__init__(f"Agente '{agent_id}' não encontrado no catálogo")


async def load_graph(
    agent_id: str,
    checkpointer: BaseCheckpointSaver | None = None,
    store: BaseStore | None = None,
    pool: AsyncConnectionPool | None = None,
    empresa_id: int = 1,
):
    """Carrega e compila o grafo de um agente pelo ID.

    Importa dinamicamente o módulo agent.py do catálogo e chama build_graph().
    Quando `pool` é fornecido, resolve o modelo principal via
    `agent_llm_config` (hot reload) escopado por (empresa_id, agent_id) e
    propaga como `chat_model`.

    Args:
        agent_id: Identificador do agente (nome do diretório em catalog/).
        checkpointer: Checkpointer para persistência de estado.
                      None em dev, PostgresSaver em prod.
        store: Store para memória semântica cross-thread.
               None desabilita memória, AsyncPostgresStore em prod.
        pool: Pool psycopg pra resolver chat_model por agente. None = usa env.
        empresa_id: Tenant scope. Default 1 ("VSA Tech").

    Returns:
        CompiledStateGraph pronto para invoke().

    Raises:
        AgentNotFoundError: Se o agent_id não existe no catálogo.
    """
    agent_dir = CATALOG_DIR / agent_id
    if not agent_dir.is_dir():
        raise AgentNotFoundError(agent_id)

    module_path = f"whatsapp_langchain.agents.catalog.{agent_id}.agent"

    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as e:
        raise AgentNotFoundError(agent_id) from e

    if not hasattr(module, "build_graph"):
        raise AgentNotFoundError(agent_id)

    chat_model: str | None = None
    calendar_enabled = False
    knowledge_enabled = False
    system_prompt_override: str | None = None
    temperatura: float | None = None
    if pool is not None:
        chat_model, _ = await get_agent_llm_config(pool, agent_id, empresa_id)
        cal_config = await get_calendar_config(pool, empresa_id)
        calendar_enabled = cal_config is not None and cal_config.ativo
        knowledge_enabled = await has_active_documents(pool, empresa_id)
        system_prompt_override, temperatura = await resolve_runtime_config(
            pool, empresa_id, agent_id
        )

    logger.info(
        "agent_loaded",
        agent_id=agent_id,
        empresa_id=empresa_id,
        chat_model=chat_model,
        calendar_enabled=calendar_enabled,
        knowledge_enabled=knowledge_enabled,
        prompt_override=bool(system_prompt_override),
        temperatura=temperatura,
    )
    return module.build_graph(
        checkpointer=checkpointer,
        store=store,
        chat_model=chat_model,
        pool=pool,
        empresa_id=empresa_id,
        calendar_enabled=calendar_enabled,
        knowledge_enabled=knowledge_enabled,
        system_prompt_override=system_prompt_override,
        temperatura=temperatura,
    )


def list_agents() -> list[str]:
    """Lista todos os agentes disponíveis no catálogo.

    Escaneia diretórios em catalog/ que possuam um arquivo agent.py
    com a função build_graph().

    Returns:
        Lista de agent_ids disponíveis.
    """
    agents = []

    for path in sorted(CATALOG_DIR.iterdir()):
        if not path.is_dir():
            continue
        if path.name.startswith("_"):
            continue

        agent_file = path / "agent.py"
        if agent_file.exists():
            agents.append(path.name)

    return agents
