"""Ferramentas de agendamento via Google Calendar (M5.a).

Injetadas no agente apenas quando a empresa tem `empresa_calendar_config`
ativo (factory consulta antes de incluir no array de tools). Cada tool
recebe `empresa_id` via `runtime.config.configurable.empresa_id` —
preenchido pelo worker no `invoke_config` ou pelo `webhook_sync`.

As tools retornam strings curtas pro agente formatar a resposta — o
LangGraph injeta como `ToolMessage` no estado e o agente decide o que
falar pro cliente.
"""

from __future__ import annotations

from typing import Annotated, Any

import structlog
from langchain_core.runnables.config import var_child_runnable_config
from langchain_core.tools import InjectedToolArg, tool

from whatsapp_langchain.shared import calendar_integration
from whatsapp_langchain.shared.calendar_integration import (
    CalendarIntegrationError,
    CalendarNotConfiguredError,
)
from whatsapp_langchain.shared.db import get_pool

logger = structlog.get_logger()


def _extract_empresa_id(runtime: Any) -> int | None:
    """Lê `empresa_id` do contexto LangGraph (igual ao memory tool)."""
    if runtime is not None:
        config = getattr(runtime, "config", None)
        if isinstance(config, dict):
            cfg = config.get("configurable", {})
            if isinstance(cfg, dict) and "empresa_id" in cfg:
                return int(cfg["empresa_id"])
    cfg = var_child_runnable_config.get(None)
    if isinstance(cfg, dict):
        configurable = cfg.get("configurable", {})
        if isinstance(configurable, dict) and "empresa_id" in configurable:
            return int(configurable["empresa_id"])
    return None


@tool
async def calendar_get_current_time(
    *,
    runtime: Annotated[Any, InjectedToolArg()] = None,
) -> str:
    """Retorna a data/hora atual e o fuso horário do calendário da empresa.

    Use SEMPRE antes de propor horários ao cliente — o cliente fala em
    horário local e o agente precisa saber qual fuso usar.
    """
    empresa_id = _extract_empresa_id(runtime)
    if empresa_id is None:
        return "empresa_id ausente no contexto — não consigo resolver o calendário."
    pool = await get_pool()
    info = await calendar_integration.get_current_time(pool, empresa_id)
    return (
        f"Agora: {info['now_utc']} (UTC). "
        f"Fuso horário do calendário: {info['timezone']}."
    )


@tool
async def calendar_find_free_slots(
    days_ahead: int = 7,
    slot_minutes: int = 60,
    *,
    runtime: Annotated[Any, InjectedToolArg()] = None,
) -> str:
    """Lista até 6 horários LIVRES na agenda da empresa.

    Use quando o cliente pedir pra agendar/marcar horário. Argumentos:
    - days_ahead: quantos dias à frente buscar (padrão 7).
    - slot_minutes: duração do slot (padrão 60min).

    Retorna ISO 8601 dos horários disponíveis na janela 09h–18h. Se não
    houver slots, informa explicitamente.
    """
    empresa_id = _extract_empresa_id(runtime)
    if empresa_id is None:
        return "empresa_id ausente no contexto."
    pool = await get_pool()
    try:
        slots = await calendar_integration.find_free_slots(
            pool,
            empresa_id,
            days_ahead=days_ahead,
            slot_minutes=slot_minutes,
        )
    except CalendarNotConfiguredError:
        return (
            "A empresa ainda não conectou o Google Calendar. "
            "Peça ao operador pra configurar em /settings/integracoes."
        )
    except CalendarIntegrationError as e:
        logger.warning("calendar_free_slots_failed", error=str(e))
        return f"Não consegui acessar o calendário agora: {e}"

    if not slots:
        return f"Nenhum horário livre nos próximos {days_ahead} dias."
    lines = "\n".join(f"- {s['start']} → {s['end']}" for s in slots)
    return f"Horários livres encontrados:\n{lines}"


@tool
async def calendar_create_event(
    summary: str,
    start_iso: str,
    end_iso: str,
    description: str = "",
    attendee_email: str = "",
    *,
    runtime: Annotated[Any, InjectedToolArg()] = None,
) -> str:
    """Cria evento no calendário da empresa.

    Use APENAS depois que o cliente confirmou o horário. Argumentos:
    - summary: título curto do evento (ex: "Atendimento Joao Teste").
    - start_iso, end_iso: timestamps ISO 8601 com timezone (ex:
      "2026-05-08T10:00:00-03:00").
    - description: texto livre (telefone do cliente, contexto).
    - attendee_email: opcional, email do convidado.
    """
    empresa_id = _extract_empresa_id(runtime)
    if empresa_id is None:
        return "empresa_id ausente no contexto."
    pool = await get_pool()
    try:
        ev = await calendar_integration.create_event(
            pool,
            empresa_id,
            summary=summary,
            start_iso=start_iso,
            end_iso=end_iso,
            description=description or None,
            attendee_email=attendee_email or None,
        )
    except CalendarNotConfiguredError:
        return "Empresa não tem Google Calendar conectado."
    except CalendarIntegrationError as e:
        logger.warning("calendar_create_event_failed", error=str(e))
        return f"Não consegui criar o evento: {e}"
    return f"Evento criado (id={ev['id']}). Link: {ev.get('htmlLink') or 'sem link'}"


@tool
async def calendar_cancel_event(
    event_id: str,
    *,
    runtime: Annotated[Any, InjectedToolArg()] = None,
) -> str:
    """Cancela um evento previamente criado. Argumento: event_id."""
    empresa_id = _extract_empresa_id(runtime)
    if empresa_id is None:
        return "empresa_id ausente no contexto."
    pool = await get_pool()
    try:
        ok = await calendar_integration.cancel_event(
            pool, empresa_id, event_id=event_id
        )
    except CalendarNotConfiguredError:
        return "Empresa não tem Google Calendar conectado."
    except CalendarIntegrationError as e:
        return f"Não consegui cancelar: {e}"
    return "Evento cancelado." if ok else "Evento não encontrado (já cancelado?)."
