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

from whatsapp_langchain.shared.agente import AgenteRuntime
from whatsapp_langchain.shared.agente_ia import resolve_runtime_config
from whatsapp_langchain.shared.base_conhecimento import has_active_documents
from whatsapp_langchain.shared.calendar_integration import get_calendar_config
from whatsapp_langchain.shared.llm import get_agent_llm_config
from whatsapp_langchain.shared.variavel import build_render_context, render_template

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
    agente_runtime: AgenteRuntime | None = None,
):
    """Carrega e compila o grafo de um agente pelo ID.

    Modo legacy (`agente_runtime=None`):
        `agent_id` é nome do diretório em `catalog/`. Resolve overrides via
        tabelas legadas `agent_llm_config` + `agente_ia_config`.

    Modo híbrido (`agente_runtime` preenchido — A.6):
        `agent_id` vira `agente_runtime.template_catalog` (qual diretório
        Python carregar). Demais campos do runtime sobrescrevem qualquer
        config legada — multi-agente DB tem precedência total.

    Args:
        agent_id: Identificador. Em modo legacy é o dir do catálogo;
                  em modo híbrido é ignorado em favor do template do runtime.
        checkpointer: Persistência de estado (None em dev).
        store: Memória semântica cross-thread (None desabilita).
        pool: Pool psycopg. None = só usa env.
        empresa_id: Tenant scope. Default 1.
        agente_runtime: Config rica de agente DB (A.6). None = legacy.

    Raises:
        AgentNotFoundError: dir do catálogo não existe.
    """
    template_id = agente_runtime.template_catalog if agente_runtime else agent_id
    agent_dir = CATALOG_DIR / template_id
    if not agent_dir.is_dir():
        raise AgentNotFoundError(template_id)

    module_path = f"whatsapp_langchain.agents.catalog.{template_id}.agent"

    try:
        module = importlib.import_module(module_path)
    except ModuleNotFoundError as e:
        raise AgentNotFoundError(template_id) from e

    if not hasattr(module, "build_graph"):
        raise AgentNotFoundError(template_id)

    chat_model: str | None = None
    calendar_enabled = False
    knowledge_enabled = False
    system_prompt_override: str | None = None
    temperatura: float | None = None
    top_p: float | None = None
    max_tokens: int | None = None

    if pool is not None:
        cal_config = await get_calendar_config(pool, empresa_id)
        calendar_enabled = cal_config is not None and cal_config.ativo
        knowledge_enabled = await has_active_documents(pool, empresa_id)

        if agente_runtime is not None:
            # Multi-agente DB tem precedência (A.6).
            chat_model = agente_runtime.modelo
            system_prompt_override = agente_runtime.prompt_override
            temperatura = agente_runtime.temperatura
            top_p = agente_runtime.top_p
            max_tokens = agente_runtime.max_tokens
        else:
            # Legacy: resolve via tabelas antigas
            chat_model, _ = await get_agent_llm_config(pool, agent_id, empresa_id)
            system_prompt_override, temperatura = await resolve_runtime_config(
                pool, empresa_id, agent_id
            )

        # Render `{{empresa.*}}`, `{{data.*}}`, `{{var.*}}`, `{{menu.*}}`
        # no prompt antes de virar instrução do agente. `cliente.*` não é
        # resolvido aqui porque o prompt é compilado uma vez por load_graph
        # (sem atendimento ainda definido).
        #
        # Quando admin não setou `prompt_override`, renderiza no default
        # SYSTEM_PROMPT do template (lê via getattr no módulo do template).
        # Sem isso, `{{empresa.nome}}` ficava literal na resposta do agente.
        ctx = await build_render_context(pool, empresa_id)
        if system_prompt_override:
            system_prompt_override = render_template(system_prompt_override, ctx)
        else:
            # Tenta renderizar o SYSTEM_PROMPT default do template (módulo
            # do catálogo). Quando o template não exporta, fica None.
            try:
                from importlib import import_module

                prompts_mod = import_module(
                    f"whatsapp_langchain.agents.catalog.{template_id}.prompts"
                )
                default_prompt = getattr(prompts_mod, "SYSTEM_PROMPT", None)
                if default_prompt:
                    system_prompt_override = render_template(default_prompt, ctx)
            except Exception as exc:
                logger.warning(
                    "default_prompt_render_failed",
                    template=template_id,
                    error=str(exc),
                )

    logger.info(
        "agent_loaded",
        agent_id=agent_id,
        template=template_id,
        empresa_id=empresa_id,
        chat_model=chat_model,
        calendar_enabled=calendar_enabled,
        knowledge_enabled=knowledge_enabled,
        prompt_override=bool(system_prompt_override),
        temperatura=temperatura,
        top_p=top_p,
        max_tokens=max_tokens,
        runtime_source="agente_ia" if agente_runtime else "legacy",
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
        top_p=top_p,
        max_tokens=max_tokens,
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


# Metadata curada dos templates (label amigável + descrição).
# Quando um template novo é adicionado ao catálogo, registrar aqui pra UI
# mostrar nome legível em vez do slug. Templates não listados ganham
# label = slug capitalizado e descrição genérica.
_TEMPLATE_METADATA: dict[str, tuple[str, str]] = {
    "vsa_tech": (
        "VSA Tech (genérico)",
        "Assistente IA com 19 tools (Calendar 8 / CRM 8 / Memória 2 / RAG 1). "
        "Modelo padrão `openai/gpt-4o-mini`. Bom pra agentes simples ou nichados "
        "via prompt_override.",
    ),
    "atendimento_completo": (
        "Atendimento Completo (multimodal)",
        "Especializado em atendimento ao cliente brasileiro com 23 tools "
        "(19 base + 4 multimodais: analyze_image / transcribe_audio / "
        "extract_document / summarize_document). SYSTEM_PROMPT pt-BR com "
        "política não-invente, escalonamento humano e fora-expediente.",
    ),
    "atendimento_router": (
        "Atendimento Router (multi-agent paralelo)",
        "Topologia Router + Parallel Agents: classifier decide quais "
        "especialistas ativar (mídia / CRM / calendário / conhecimento) e "
        "executa até 3 em paralelo via Send. Synthesizer agrega outputs em "
        "resposta única pt-BR. Reduz alucinação isolando contexto por domínio. "
        "Bom pra atendimento com mídia + CRM + KB no mesmo turno.",
    ),
}


def list_agente_templates() -> list[dict]:
    """Lista templates do catálogo com metadata pra UI dropdown.

    Returns:
        [{slug, label, descricao}] ordenado por label.
    """
    items: list[dict] = []
    for slug in list_agents():
        label, descricao = _TEMPLATE_METADATA.get(
            slug,
            (slug.replace("_", " ").title(), "Template sem metadata cadastrada."),
        )
        items.append({"slug": slug, "label": label, "descricao": descricao})
    items.sort(key=lambda x: x["label"])
    return items
