"""Tests das tools de memória estruturada (M5.b.2)."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from whatsapp_langchain.agents.tools import cliente_memoria as cm_tools
from whatsapp_langchain.shared.models import (
    Atendimento,
    ClienteMemoria,
)


def _runtime(empresa_id: int = 1, atendimento_id: int = 5, user_id: str = "u1"):
    return SimpleNamespace(
        config={
            "configurable": {
                "empresa_id": empresa_id,
                "atendimento_id": atendimento_id,
                "user_id": user_id,
            }
        }
    )


def _atendimento(*, id_=5, empresa_id=1, cliente_id=10):
    now = datetime.now(UTC)
    return Atendimento(
        id=id_,
        empresa_id=empresa_id,
        cliente_id=cliente_id,
        conexao_id=1,
        agente_atual="vsa_tech",
        status="em_andamento",
        assigned_to_user_id=None,
        last_message_at=now,
        closed_at=None,
        created_at=now,
        updated_at=now,
    )


def _memoria(*, id_=1, categoria="fato", conteudo="cliente prefere email"):
    now = datetime.now(UTC)
    return ClienteMemoria(
        id=id_,
        empresa_id=1,
        cliente_id=10,
        categoria=categoria,
        conteudo=conteudo,
        source="agent_explicit",
        created_by_user_id="agente:u1",
        created_at=now,
        updated_at=now,
    )


@pytest.fixture(autouse=True)
def _patch_pool():
    with patch.object(cm_tools, "get_pool", new=AsyncMock(return_value=MagicMock())):
        yield


# --- read_cliente_memoria ---


@pytest.mark.asyncio
async def test_read_returns_relevant_memorias():
    with (
        patch.object(
            cm_tools, "get_atendimento_by_id", AsyncMock(return_value=_atendimento())
        ),
        patch.object(
            cm_tools.memoria,
            "search_relevant",
            AsyncMock(return_value=[(_memoria(conteudo="prefere whatsapp"), 0.85)]),
        ),
    ):
        out = await cm_tools.read_cliente_memoria.ainvoke(
            {"query": "como falar com cliente", "runtime": _runtime()}
        )
    assert "prefere whatsapp" in out
    assert "0.85" in out


@pytest.mark.asyncio
async def test_read_handles_missing_atendimento():
    with patch.object(
        cm_tools, "get_atendimento_by_id", AsyncMock(return_value=None)
    ):
        out = await cm_tools.read_cliente_memoria.ainvoke(
            {"query": "x", "runtime": _runtime()}
        )
    assert "contexto incompleto" in out


@pytest.mark.asyncio
async def test_read_anti_cross_tenant():
    """Atendimento de outra empresa → não retorna dados."""
    other = _atendimento(empresa_id=99)
    with patch.object(
        cm_tools, "get_atendimento_by_id", AsyncMock(return_value=other)
    ):
        out = await cm_tools.read_cliente_memoria.ainvoke(
            {"query": "x", "runtime": _runtime()}
        )
    assert "contexto incompleto" in out


@pytest.mark.asyncio
async def test_read_returns_empty_msg_when_no_results():
    with (
        patch.object(
            cm_tools, "get_atendimento_by_id", AsyncMock(return_value=_atendimento())
        ),
        patch.object(
            cm_tools.memoria, "search_relevant", AsyncMock(return_value=[])
        ),
    ):
        out = await cm_tools.read_cliente_memoria.ainvoke(
            {"query": "x", "runtime": _runtime()}
        )
    assert "Nenhuma memória" in out


# --- save_cliente_fato ---


@pytest.mark.asyncio
async def test_save_returns_id_when_created():
    with (
        patch.object(
            cm_tools, "get_atendimento_by_id", AsyncMock(return_value=_atendimento())
        ),
        patch.object(
            cm_tools.memoria,
            "save_memoria",
            AsyncMock(return_value=(_memoria(id_=42), True)),
        ),
    ):
        out = await cm_tools.save_cliente_fato.ainvoke(
            {
                "categoria": "fato",
                "conteudo": "Cliente comprou produto X",
                "runtime": _runtime(),
            }
        )
    assert "#42" in out
    assert "fato" in out


@pytest.mark.asyncio
async def test_save_dedup_returns_existing():
    with (
        patch.object(
            cm_tools, "get_atendimento_by_id", AsyncMock(return_value=_atendimento())
        ),
        patch.object(
            cm_tools.memoria,
            "save_memoria",
            AsyncMock(return_value=(_memoria(id_=99), False)),
        ),
    ):
        out = await cm_tools.save_cliente_fato.ainvoke(
            {
                "categoria": "fato",
                "conteudo": "Cliente comprou produto X",
                "runtime": _runtime(),
            }
        )
    assert "já existia" in out
    assert "#99" in out


@pytest.mark.asyncio
async def test_save_rejects_invalid_categoria():
    out = await cm_tools.save_cliente_fato.ainvoke(
        {
            "categoria": "invalida",
            "conteudo": "Cliente comprou X",
            "runtime": _runtime(),
        }
    )
    assert "Categoria inválida" in out


@pytest.mark.asyncio
async def test_save_rejects_short_conteudo():
    out = await cm_tools.save_cliente_fato.ainvoke(
        {"categoria": "fato", "conteudo": "ab", "runtime": _runtime()}
    )
    assert "muito curto" in out


@pytest.mark.asyncio
async def test_save_truncates_at_1000_chars():
    with (
        patch.object(
            cm_tools, "get_atendimento_by_id", AsyncMock(return_value=_atendimento())
        ),
        patch.object(
            cm_tools.memoria,
            "save_memoria",
            AsyncMock(return_value=(_memoria(id_=1), True)),
        ) as mock_save,
    ):
        await cm_tools.save_cliente_fato.ainvoke(
            {"categoria": "fato", "conteudo": "x" * 2000, "runtime": _runtime()}
        )
    # 3º arg posicional é ClienteMemoriaInput; pega o valor final do conteudo
    body = mock_save.await_args.args[3]
    assert len(body.conteudo) == 1000


@pytest.mark.asyncio
async def test_save_normalizes_categoria_uppercase():
    with (
        patch.object(
            cm_tools, "get_atendimento_by_id", AsyncMock(return_value=_atendimento())
        ),
        patch.object(
            cm_tools.memoria,
            "save_memoria",
            AsyncMock(return_value=(_memoria(id_=1), True)),
        ) as mock_save,
    ):
        await cm_tools.save_cliente_fato.ainvoke(
            {
                "categoria": "PERFIL",
                "conteudo": "Profissional de tech",
                "runtime": _runtime(),
            }
        )
    body = mock_save.await_args.args[3]
    assert body.categoria == "perfil"
