"""Carregador dinâmico de agentes.

Importa agentes do catálogo em tempo de execução, permitindo que a API
e o Worker carreguem qualquer agente registrado pelo nome.

Cada agente deve ter um arquivo agent.py com a função build_graph()
no diretório agents/catalog/{agent_id}/.

Uso:
    from whatsapp_langchain.agents.loader import load_graph, list_agents

    graph = load_graph("rhawk_assistant", checkpointer=saver)
    agents = list_agents()  # ["rhawk_assistant"]
"""

import importlib
from pathlib import Path

import structlog
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore

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


def load_graph(
    agent_id: str,
    checkpointer: BaseCheckpointSaver | None = None,
    store: BaseStore | None = None,
):
    """Carrega e compila o grafo de um agente pelo ID.

    Importa dinamicamente o módulo agent.py do catálogo e chama build_graph().

    Args:
        agent_id: Identificador do agente (nome do diretório em catalog/).
        checkpointer: Checkpointer para persistência de estado.
                      None em dev, PostgresSaver em prod.
        store: Store para memória semântica cross-thread.
               None desabilita memória, AsyncPostgresStore em prod.

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

    logger.info("agent_loaded", agent_id=agent_id)
    return module.build_graph(checkpointer=checkpointer, store=store)


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
