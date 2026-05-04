"""Tests dos helpers Calendar S1: list_calendars, set_active_calendar, list_events.

Mocka `_calendar_service` e `_resolve_credentials` pra evitar dependência
de Google API real e DB. Foca em validar:
- Shape do retorno (list de dicts com chaves esperadas)
- Validação de input (calendar_id vazio, 404 ao validar)
- Ordem das chamadas Google API (calendarList.list, calendarList.get,
  events.list com kwargs corretos)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from whatsapp_langchain.shared import calendar_integration
from whatsapp_langchain.shared.calendar_integration import CalendarIntegrationError


@pytest.fixture
def fake_creds() -> Any:
    """Credentials mock — só precisa existir, não é validado."""
    return MagicMock(name="Credentials")


@pytest.fixture
def fake_config() -> Any:
    cfg = MagicMock()
    cfg.empresa_id = 1
    cfg.calendar_id = "primary"
    cfg.timezone = "America/Sao_Paulo"
    cfg.ativo = True
    return cfg


@pytest.fixture
def patched_resolve(monkeypatch, fake_config, fake_creds):
    """Substitui `_resolve_credentials` por async mock que retorna config+creds fakes."""
    mock = AsyncMock(return_value=(fake_config, fake_creds))
    monkeypatch.setattr(calendar_integration, "_resolve_credentials", mock)
    return mock


@pytest.fixture
def fake_pool():
    """Pool mock — só precisa ter o ctx manager `connection()` pra UPDATE."""
    pool = MagicMock()
    conn = MagicMock()
    conn.execute = AsyncMock()
    conn.commit = AsyncMock()

    async def _aenter():
        return conn

    pool.connection.return_value.__aenter__ = AsyncMock(side_effect=_aenter)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool


# ---------------------------------------------------------------------------
# list_calendars
# ---------------------------------------------------------------------------


async def test_list_calendars_returns_normalized_dicts(monkeypatch, patched_resolve, fake_pool):
    """Itens do Google viram dicts com keys padronizadas."""
    google_items = [
        {
            "id": "primary",
            "summary": "Vinicius",
            "timeZone": "America/Sao_Paulo",
            "primary": True,
            "accessRole": "owner",
        },
        {
            "id": "comercial@empresa.com",
            "summary": "Comercial",
            "description": "Equipe vendas",
            "timeZone": "America/Sao_Paulo",
            "accessRole": "writer",
        },
    ]
    fake_service = MagicMock()
    fake_service.calendarList.return_value.list.return_value.execute.return_value = {
        "items": google_items
    }
    monkeypatch.setattr(
        calendar_integration, "_calendar_service", lambda creds: fake_service
    )

    out = await calendar_integration.list_calendars(fake_pool, 1)

    assert len(out) == 2
    assert out[0]["id"] == "primary"
    assert out[0]["primary"] is True
    assert out[1]["id"] == "comercial@empresa.com"
    assert out[1]["primary"] is False
    assert out[1]["description"] == "Equipe vendas"


async def test_list_calendars_empty_returns_empty_list(monkeypatch, patched_resolve, fake_pool):
    fake_service = MagicMock()
    fake_service.calendarList.return_value.list.return_value.execute.return_value = {}
    monkeypatch.setattr(
        calendar_integration, "_calendar_service", lambda creds: fake_service
    )

    out = await calendar_integration.list_calendars(fake_pool, 1)
    assert out == []


# ---------------------------------------------------------------------------
# set_active_calendar
# ---------------------------------------------------------------------------


async def test_set_active_calendar_validates_via_get_then_updates_db(
    monkeypatch, patched_resolve, fake_pool
):
    fake_service = MagicMock()
    fake_service.calendarList.return_value.get.return_value.execute.return_value = {
        "id": "comercial@empresa.com",
        "summary": "Comercial",
        "timeZone": "America/Sao_Paulo",
    }
    monkeypatch.setattr(
        calendar_integration, "_calendar_service", lambda creds: fake_service
    )

    out = await calendar_integration.set_active_calendar(
        fake_pool, 1, "comercial@empresa.com"
    )

    assert out["id"] == "comercial@empresa.com"
    assert out["summary"] == "Comercial"
    # Garantiu que validou via get antes de UPDATE
    fake_service.calendarList.return_value.get.assert_called_once_with(
        calendarId="comercial@empresa.com"
    )


async def test_set_active_calendar_rejects_empty_id(fake_pool):
    with pytest.raises(CalendarIntegrationError, match="vazio"):
        await calendar_integration.set_active_calendar(fake_pool, 1, "  ")


async def test_set_active_calendar_404_raises_friendly_error(
    monkeypatch, patched_resolve, fake_pool
):
    from googleapiclient.errors import HttpError

    fake_resp = MagicMock(status=404, reason="Not Found")
    fake_service = MagicMock()
    fake_service.calendarList.return_value.get.return_value.execute.side_effect = (
        HttpError(fake_resp, b'{"error":"not found"}')
    )
    monkeypatch.setattr(
        calendar_integration, "_calendar_service", lambda creds: fake_service
    )

    with pytest.raises(CalendarIntegrationError, match="não encontrado"):
        await calendar_integration.set_active_calendar(
            fake_pool, 1, "naoexiste@x.com"
        )


# ---------------------------------------------------------------------------
# list_events
# ---------------------------------------------------------------------------


async def test_list_events_passes_kwargs_to_google(monkeypatch, patched_resolve, fake_pool):
    fake_service = MagicMock()
    fake_service.events.return_value.list.return_value.execute.return_value = {
        "items": []
    }
    monkeypatch.setattr(
        calendar_integration, "_calendar_service", lambda creds: fake_service
    )

    await calendar_integration.list_events(
        fake_pool,
        1,
        time_min_iso="2026-05-08T00:00:00-03:00",
        time_max_iso="2026-05-08T23:59:59-03:00",
        max_results=10,
    )

    fake_service.events.return_value.list.assert_called_once_with(
        calendarId="primary",
        timeMin="2026-05-08T00:00:00-03:00",
        timeMax="2026-05-08T23:59:59-03:00",
        singleEvents=True,
        orderBy="startTime",
        maxResults=10,
    )


async def test_list_events_normalizes_event_shape(monkeypatch, patched_resolve, fake_pool):
    fake_service = MagicMock()
    fake_service.events.return_value.list.return_value.execute.return_value = {
        "items": [
            {
                "id": "ev123",
                "summary": "Reunião",
                "start": {"dateTime": "2026-05-08T14:00:00-03:00"},
                "end": {"dateTime": "2026-05-08T15:00:00-03:00"},
                "status": "confirmed",
                "htmlLink": "https://calendar.google.com/event?eid=...",
                "organizer": {"email": "vini@vsa.com"},
                "attendees": [
                    {"email": "joao@cliente.com"},
                    {"email": "maria@cliente.com"},
                    {"resource": True},  # sem email — deve ser filtrado
                ],
            },
            {
                "id": "ev456",
                # all-day event tem `start.date` em vez de `dateTime`
                "start": {"date": "2026-05-09"},
                "end": {"date": "2026-05-10"},
            },
        ]
    }
    monkeypatch.setattr(
        calendar_integration, "_calendar_service", lambda creds: fake_service
    )

    out = await calendar_integration.list_events(
        fake_pool, 1, time_min_iso="x", time_max_iso="y"
    )

    assert len(out) == 2
    assert out[0]["id"] == "ev123"
    assert out[0]["summary"] == "Reunião"
    assert out[0]["start"] == "2026-05-08T14:00:00-03:00"
    assert out[0]["organizer_email"] == "vini@vsa.com"
    assert out[0]["attendees"] == ["joao@cliente.com", "maria@cliente.com"]
    # All-day event normalizado: start vira a string `date`
    assert out[1]["start"] == "2026-05-09"
    assert out[1]["summary"] is None
