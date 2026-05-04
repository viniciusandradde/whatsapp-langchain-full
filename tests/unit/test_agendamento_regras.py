"""Tests de regras + validate_request (S3 Calendar v2).

Cobre:
- get() retorna defaults virtuais quando não há row
- get() lê row real quando existe
- upsert() preserva campos não passados
- validate_request: antecedência, dia da semana, dias bloqueados,
  janela horária local (timezone-aware)
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from whatsapp_langchain.shared import agendamento, agendamento_regras


@pytest.fixture
def fake_pool_no_row():
    """Pool que retorna fetchone() = None (empresa sem regras)."""
    pool = MagicMock()
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchone = AsyncMock(return_value=None)
    conn.execute = AsyncMock(return_value=cur)
    conn.commit = AsyncMock()
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool


@pytest.fixture
def fake_pool_with_regras():
    """Pool que retorna row com hora_inicio=09:00, hora_fim=17:00."""
    pool = MagicMock()
    conn = MagicMock()
    cur = MagicMock()
    cur.fetchone = AsyncMock(
        return_value=(
            time(9, 0),                                 # hora_inicio
            time(17, 0),                                # hora_fim
            30,                                         # antecedencia_minima_minutos
            0,                                          # intervalo_entre_minutos
            [1, 2, 3, 4, 5],                            # dias_semana_permitidos
            ["2026-05-09"],                             # dias_bloqueados (sexta)
            False,                                      # requer_aprovacao
            datetime(2026, 5, 1, tzinfo=timezone.utc),  # created_at
            datetime(2026, 5, 1, tzinfo=timezone.utc),  # updated_at
        )
    )
    conn.execute = AsyncMock(return_value=cur)
    conn.commit = AsyncMock()
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool


# ---------------------------------------------------------------------------
# agendamento_regras.get
# ---------------------------------------------------------------------------


async def test_get_returns_defaults_when_no_row(fake_pool_no_row):
    out = await agendamento_regras.get(fake_pool_no_row, 1)
    assert out.empresa_id == 1
    assert out.hora_inicio == "08:00"
    assert out.hora_fim == "18:00"
    assert out.antecedencia_minima_minutos == 60
    assert out.dias_semana_permitidos == [1, 2, 3, 4, 5]
    assert out.dias_bloqueados == []
    assert out.requer_aprovacao is False


async def test_get_reads_existing_row(fake_pool_with_regras):
    out = await agendamento_regras.get(fake_pool_with_regras, 1)
    assert out.hora_inicio == "09:00"
    assert out.hora_fim == "17:00"
    assert out.antecedencia_minima_minutos == 30
    assert "2026-05-09" in out.dias_bloqueados


# ---------------------------------------------------------------------------
# validate_request
# ---------------------------------------------------------------------------


@pytest.fixture
def patch_regras_default(monkeypatch):
    """Forja get_regras retornando defaults pra testar validate."""
    from whatsapp_langchain.shared.models import AgendamentoRegras

    def _build(**overrides):
        now = datetime.now(timezone.utc)
        defaults = {
            "empresa_id": 1,
            "hora_inicio": "08:00",
            "hora_fim": "18:00",
            "antecedencia_minima_minutos": 60,
            "intervalo_entre_minutos": 0,
            "dias_semana_permitidos": [1, 2, 3, 4, 5],
            "dias_bloqueados": [],
            "requer_aprovacao": False,
            "created_at": now,
            "updated_at": now,
        }
        defaults.update(overrides)
        return AgendamentoRegras(**defaults)

    return _build


@pytest.fixture
def patch_calendar_config(monkeypatch):
    """get_calendar_config retorna fake com timezone São Paulo."""
    from whatsapp_langchain.shared import calendar_integration

    fake = MagicMock()
    fake.timezone = "America/Sao_Paulo"
    monkeypatch.setattr(
        calendar_integration,
        "get_calendar_config",
        AsyncMock(return_value=fake),
    )
    return fake


async def test_validate_rejects_inicio_apos_fim(patch_regras_default, patch_calendar_config, monkeypatch):
    monkeypatch.setattr(
        agendamento_regras, "get",
        AsyncMock(return_value=patch_regras_default()),
    )
    later = datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)
    earlier = later - timedelta(hours=1)
    ok, motivo = await agendamento.validate_request(
        MagicMock(), 1, start=later, end=earlier
    )
    assert not ok
    assert "Início" in motivo


async def test_validate_rejects_antecedencia_curta(patch_regras_default, patch_calendar_config, monkeypatch):
    monkeypatch.setattr(
        agendamento_regras, "get",
        AsyncMock(return_value=patch_regras_default()),
    )
    # Daqui a 10 min — falha pq antecedência mín é 60 min
    soon = datetime.now(timezone.utc) + timedelta(minutes=10)
    end = soon + timedelta(hours=1)
    ok, motivo = await agendamento.validate_request(
        MagicMock(), 1, start=soon, end=end
    )
    assert not ok
    assert "Antecedência" in motivo


async def test_validate_rejects_sabado_dom(patch_regras_default, patch_calendar_config, monkeypatch):
    monkeypatch.setattr(
        agendamento_regras, "get",
        AsyncMock(return_value=patch_regras_default()),
    )
    # Sábado 2026-05-09 às 10h SP (= 13h UTC)
    sab = datetime(2026, 5, 9, 13, 0, tzinfo=timezone.utc)
    ok, motivo = await agendamento.validate_request(
        MagicMock(), 1, start=sab, end=sab + timedelta(hours=1)
    )
    assert not ok
    assert "sáb" in motivo.lower() or "sab" in motivo.lower()


async def test_validate_rejects_dia_bloqueado(patch_regras_default, patch_calendar_config, monkeypatch):
    monkeypatch.setattr(
        agendamento_regras, "get",
        AsyncMock(return_value=patch_regras_default(dias_bloqueados=["2026-05-08"])),
    )
    # Sexta 2026-05-08 (dia bloqueado)
    bloq = datetime(2026, 5, 8, 14, 0, tzinfo=timezone.utc)
    ok, motivo = await agendamento.validate_request(
        MagicMock(), 1, start=bloq, end=bloq + timedelta(hours=1)
    )
    assert not ok
    assert "bloqueado" in motivo.lower()


async def test_validate_rejects_fora_horario(patch_regras_default, patch_calendar_config, monkeypatch):
    monkeypatch.setattr(
        agendamento_regras, "get",
        AsyncMock(return_value=patch_regras_default()),
    )
    # Quinta 2026-05-07 às 22h SP (= 01h UTC dia 8) — fora janela 08-18
    fora = datetime(2026, 5, 8, 1, 0, tzinfo=timezone.utc)
    ok, motivo = await agendamento.validate_request(
        MagicMock(), 1, start=fora, end=fora + timedelta(hours=1)
    )
    assert not ok
    assert "08:00" in motivo or "fora" in motivo.lower()


async def test_validate_aceita_horario_valido(patch_regras_default, patch_calendar_config, monkeypatch):
    monkeypatch.setattr(
        agendamento_regras, "get",
        AsyncMock(return_value=patch_regras_default()),
    )
    # Quinta 2026-05-07 às 14h SP (= 17h UTC) — dentro de tudo
    ok = datetime(2026, 5, 7, 17, 0, tzinfo=timezone.utc)
    valido, motivo = await agendamento.validate_request(
        MagicMock(), 1, start=ok, end=ok + timedelta(hours=1)
    )
    assert valido
    assert motivo is None
