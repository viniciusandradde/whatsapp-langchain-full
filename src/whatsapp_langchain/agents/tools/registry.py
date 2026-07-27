"""Registry slug → ferramenta: liga os checkboxes do painel ao agente real.

O editor de agente (`/agents/db/[slug]`) mostra uma lista de ferramentas com
checkbox e grava a seleção em `agente_ia.tools_enabled`. Até este módulo
existir, **nada lia esse campo em runtime**: a lista de tools era hardcoded no
`build_graph`, então todo agente recebia o mesmo conjunto, marcado ou não. O
painel prometia um controle que não existia.

Aqui fica o único lugar que traduz o vocabulário da UI para as funções `@tool`
de verdade.

Contrato:

- Marcar um slug é condição NECESSÁRIA, não suficiente. `calendar.*` e
  `search_knowledge_base` continuam dependendo de `calendar_enabled` /
  `knowledge_enabled`, que o loader resolve pelo banco. Marcar não liga
  integração que a empresa não tem.
- Lista vazia (ou só com slug irreconhecível) devolve o conjunto COMPLETO e
  loga aviso. Preferimos agente com ferramenta demais a agente mudo — e
  nenhum agente existente quebra ao subir esta mudança.
- Slug de backlog é reconhecido e ignorado em silêncio. Ele está na UI de
  propósito (roadmap visível), então não é erro de configuração.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Any

import structlog

from whatsapp_langchain.agents.tools.calendar import (
    calendar_cancel_event,
    calendar_create_event,
    calendar_find_free_slots,
    calendar_get_current_time,
    calendar_list_calendars,
    calendar_list_events,
    calendar_reschedule_event,
    calendar_set_active_calendar,
)
from whatsapp_langchain.agents.tools.cliente_atendimento import (
    add_cliente_tag,
    classificar_atendimento,
    close_atendimento,
    create_cliente_anotacao,
    get_cliente_anotacoes,
    get_cliente_history,
    get_cliente_profile,
    transfer_to_human,
    update_cliente,
)
from whatsapp_langchain.agents.tools.cliente_memoria import (
    read_cliente_memoria,
    save_cliente_fato,
)
from whatsapp_langchain.agents.tools.knowledge import search_knowledge_base

logger = structlog.get_logger()


# Slug da UI → tools reais. Um slug pode render mais de uma ferramenta:
# "consultar contexto" é uma ideia pro admin, mas duas funções pro agente.
TOOL_SLUGS: dict[str, tuple[Any, ...]] = {
    # `transferir_dep` e `solicitar_humano` são a MESMA tool: o destino é
    # determinístico (`agente_ia.departamento_default_id`), o agente não
    # escolhe departamento. Os dois slugs existem na UI porque descrevem
    # intenções diferentes pro admin, mas o efeito é idêntico.
    "solicitar_humano": (transfer_to_human,),
    "transferir_dep": (transfer_to_human,),
    "encerrar_atendimento": (close_atendimento,),
    "tag_cliente": (add_cliente_tag,),
    # Classificar grava prioridade/sentimento/categoria no atendimento —
    # é o que a UI chama de "tag do atendimento".
    "tag_atendimento": (classificar_atendimento,),
    "consultar_contexto": (get_cliente_history, get_cliente_anotacoes),
    "salvar_contexto": (save_cliente_fato, read_cliente_memoria),
    "cliente.read": (get_cliente_profile,),
    "cliente.write": (update_cliente,),
    "cliente_anotacao.create": (create_cliente_anotacao,),
    "search_knowledge_base": (search_knowledge_base,),
    # Calendário: `create` leva junto as tools de escrita/reagendamento, e
    # `list` as de leitura. `get_current_time` entra nos dois porque agendar
    # sem saber a data de hoje gera evento no passado.
    "calendar.create": (
        calendar_get_current_time,
        calendar_create_event,
        calendar_reschedule_event,
        calendar_cancel_event,
        calendar_find_free_slots,
    ),
    "calendar.list": (
        calendar_get_current_time,
        calendar_list_calendars,
        calendar_set_active_calendar,
        calendar_list_events,
    ),
}

# Vocabulário antigo. O agente 1 (`atendimento`) foi gravado com estes nomes,
# que sumiram da UI depois. Sem o alias ele cairia no fallback e ninguém ligaria
# uma coisa à outra.
SLUG_ALIASES: dict[str, str] = {
    "transferir_para_humano": "solicitar_humano",
    "transferir_para_departamento": "transferir_dep",
    "transferir_humano": "solicitar_humano",
    "buscar_conhecimento": "search_knowledge_base",
    "fechar_atendimento": "encerrar_atendimento",
}

# Aparecem na UI com selo "backlog" e não têm implementação. São ignorados sem
# aviso — estão lá de propósito, mostrando roadmap. `enviar_link` entra aqui
# porque nunca teve tool: o agente manda link no corpo da mensagem.
BACKLOG_SLUGS: frozenset[str] = frozenset(
    {
        "transferir_atendente",
        "transferir_agente",
        "abrir_menu",
        "chamar_webhook",
        "buscar_arquivos",
        "enviar_link",
    }
)

# Slugs que só valem com a integração ligada no banco. Marcar não basta.
_GATED_BY_CALENDAR = frozenset({"calendar.create", "calendar.list"})
_GATED_BY_KNOWLEDGE = frozenset({"search_knowledge_base"})


def normalizar_slug(slug: str) -> str:
    """Aplica alias e normaliza caixa/espaços."""
    limpo = (slug or "").strip().lower()
    return SLUG_ALIASES.get(limpo, limpo)


def _todas_as_tools(*, calendar_enabled: bool, knowledge_enabled: bool) -> list[Any]:
    """Conjunto completo, respeitando os gates de integração."""
    return _montar(TOOL_SLUGS.keys(), calendar_enabled, knowledge_enabled)


def _montar(
    slugs: Iterable[str], calendar_enabled: bool, knowledge_enabled: bool
) -> list[Any]:
    """Resolve slugs em tools, sem duplicar e mantendo ordem estável."""
    saida: list[Any] = []
    vistos: set[int] = set()
    for slug in slugs:
        if slug in _GATED_BY_CALENDAR and not calendar_enabled:
            continue
        if slug in _GATED_BY_KNOWLEDGE and not knowledge_enabled:
            continue
        for tool in TOOL_SLUGS.get(slug, ()):
            if id(tool) not in vistos:
                vistos.add(id(tool))
                saida.append(tool)
    return saida


def resolve_tools(
    tools_enabled: Sequence[str] | None,
    *,
    calendar_enabled: bool = False,
    knowledge_enabled: bool = False,
) -> list[Any]:
    """Traduz `agente_ia.tools_enabled` na lista de tools do agente.

    Args:
        tools_enabled: slugs marcados no painel. None/vazio = tudo.
        calendar_enabled: empresa tem Google Calendar ativo.
        knowledge_enabled: empresa tem ≥1 documento na base.

    Returns:
        Tools na ordem do registry, sem duplicata.
    """
    if not tools_enabled:
        # Caminho normal pro modo legacy (sem linha em `agente_ia`) e pra
        # agente recém-criado: recebe tudo até alguém restringir.
        return _todas_as_tools(
            calendar_enabled=calendar_enabled, knowledge_enabled=knowledge_enabled
        )

    normalizados = [normalizar_slug(s) for s in tools_enabled]
    conhecidos = [s for s in normalizados if s in TOOL_SLUGS]
    desconhecidos = [
        s for s in normalizados if s not in TOOL_SLUGS and s not in BACKLOG_SLUGS
    ]

    if desconhecidos:
        logger.warning(
            "agente_tools_slug_desconhecido",
            slugs=sorted(set(desconhecidos)),
            acao="ignorados",
        )

    if not conhecidos:
        # Só backlog e/ou lixo. Devolver lista vazia deixaria o agente sem
        # NENHUMA ferramenta — nem transferir pra humano ele conseguiria, e o
        # sintoma (agente que não sai do lugar) não apontaria pra config.
        logger.warning(
            "agente_tools_fallback_total",
            recebidos=list(tools_enabled),
            motivo="nenhum slug reconhecido; usando conjunto completo",
        )
        return _todas_as_tools(
            calendar_enabled=calendar_enabled, knowledge_enabled=knowledge_enabled
        )

    # Itera TOOL_SLUGS (não `conhecidos`) pra ordem não depender de como o
    # admin marcou os checkboxes — diff de log fica estável.
    selecionados = [s for s in TOOL_SLUGS if s in set(conhecidos)]
    return _montar(selecionados, calendar_enabled, knowledge_enabled)
