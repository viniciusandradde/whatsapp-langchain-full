"""Celular BR com e sem o nono dígito é o mesmo cliente (24/09/2026).

Caso real (empresa 1025): o operador abriu a conversa com +55 67 98424-9725
e a resposta chegou da Meta como 556784249725 — virou outro cliente e outra
conversa.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from whatsapp_langchain.shared.cliente import criar_cliente, upsert_cliente
from whatsapp_langchain.shared.telefone import variantes_nono_digito
from whatsapp_langchain.shared.whitelist import candidatos_lookup


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("+5567984249725", ["+5567984249725", "+556784249725"]),
        ("+556784249725", ["+556784249725", "+5567984249725"]),
        ("556784249725", ["556784249725", "5567984249725"]),  # formato mantido
        ("+556733214567", ["+556733214567"]),  # fixo (começa em 3): sem variante
        ("+14155550100", ["+14155550100"]),  # estrangeiro
        ("+55679842", ["+55679842"]),  # tamanho fora do padrão
    ],
)
def test_variantes_nono_digito(entrada, esperado):
    assert variantes_nono_digito(entrada) == esperado


def test_whitelist_usa_a_mesma_regra():
    assert candidatos_lookup("+55 67 98424-9725") == ["+5567984249725", "+556784249725"]


def _pool(*fetchones):
    cur = AsyncMock()
    cur.fetchone = AsyncMock(side_effect=list(fetchones))
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cur)
    pool = MagicMock()
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


def _row(telefone):
    from datetime import UTC, datetime

    now = datetime.now(UTC)
    return (
        10876,
        1025,
        telefone,
        "Vinicius",
        None,
        None,
        "active",
        {},
        now,
        now,
        *([None] * 49),
    )


async def test_inbound_sem_o_9_cai_no_cliente_cadastrado_com_o_9():
    # 1º fetchone: a busca das grafias acha a cadastrada; 2º: o INSERT..UPSERT.
    pool, conn = _pool(("+5567984249725",), _row("+5567984249725"))
    out = await upsert_cliente(pool, 1025, "+556784249725", nome="Nexus")
    assert out.id == 10876
    busca, upsert = conn.execute.await_args_list
    assert busca.args[1][1] == ["+556784249725", "+5567984249725"]
    assert upsert.args[1][1] == "+5567984249725"  # grava na grafia existente


async def test_sem_cadastro_usa_o_numero_recebido():
    pool, conn = _pool(None, _row("+556784249725"))
    await upsert_cliente(pool, 1025, "+556784249725")
    assert conn.execute.await_args_list[1].args[1][1] == "+556784249725"


async def test_cadastro_manual_reconhece_a_outra_grafia():
    # grafia cadastrada → INSERT ... DO NOTHING não devolve linha → busca a existente
    pool, conn = _pool(("+556784249725",), None, _row("+556784249725"))
    cliente, criado = await criar_cliente(pool, 1025, "+5567984249725", nome="Ana")
    assert criado is False
    assert cliente.telefone == "+556784249725"
