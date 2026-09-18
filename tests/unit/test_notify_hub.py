"""NotifyHub — um LISTEN por canal por processo, fan-out em memória.

Conexão falsa: o teste controla quando um NOTIFY "chega" e quando a conexão
"cai". Nada aqui toca Postgres.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from whatsapp_langchain.shared import notify_hub as nh


class _ConexaoFalsa:
    """`async with` + `execute` + `notifies()` que lê de uma fila do teste."""

    def __init__(self, eventos: asyncio.Queue, *, morrer_em: int | None = None):
        self._eventos = eventos
        self._morrer_em = morrer_em
        self.comandos: list[str] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def execute(self, sql: str):
        self.comandos.append(sql)

    async def notifies(self):
        n = 0
        while True:
            payload = await self._eventos.get()
            n += 1
            if self._morrer_em is not None and n >= self._morrer_em:
                raise OSError("conexão caiu")
            yield SimpleNamespace(payload=payload)


def _hub(eventos: asyncio.Queue, **kw) -> tuple[nh.NotifyHub, list[_ConexaoFalsa]]:
    conexoes: list[_ConexaoFalsa] = []

    async def connect():
        c = _ConexaoFalsa(eventos, **kw)
        conexoes.append(c)
        return c

    return nh.NotifyHub("canal_teste", connect), conexoes


async def test_um_listen_entrega_a_todos_os_assinantes():
    eventos: asyncio.Queue = asyncio.Queue()
    hub, conexoes = _hub(eventos)
    async with hub.subscribe() as a, hub.subscribe() as b:
        assert await hub.esperar_conexao(1)
        await eventos.put('{"x":1}')
        assert await a.get(1) == '{"x":1}'
        assert await b.get(1) == '{"x":1}'
    assert len(conexoes) == 1
    assert conexoes[0].comandos == ["LISTEN canal_teste"]
    assert hub.assinantes == 0
    await hub.fechar()


async def test_sem_evento_o_get_estoura_timeout_para_o_heartbeat():
    eventos: asyncio.Queue = asyncio.Queue()
    hub, _ = _hub(eventos)
    async with hub.subscribe() as a:
        await hub.esperar_conexao(1)
        with pytest.raises(TimeoutError):
            await a.get(0.05)
    await hub.fechar()


async def test_reconecta_e_avisa_resync(monkeypatch):
    monkeypatch.setattr(nh, "_BACKOFF_S", (0, 0))
    eventos: asyncio.Queue = asyncio.Queue()
    hub, conexoes = _hub(eventos, morrer_em=2)  # 2º evento derruba a conexão
    async with hub.subscribe() as a:
        await hub.esperar_conexao(1)
        await eventos.put("um")
        assert await a.get(1) == "um"
        await eventos.put("dois")  # mata a 1ª conexão; o hub reconecta
        assert await a.get(1) == nh.RESYNC
        await eventos.put("tres")
        assert await a.get(1) == "tres"
    assert len(conexoes) == 2
    await hub.fechar()


async def test_assinante_lento_descarta_sem_travar_os_outros(monkeypatch):
    monkeypatch.setattr(nh, "_TAMANHO_FILA", 2)
    eventos: asyncio.Queue = asyncio.Queue()
    hub, _ = _hub(eventos)
    async with hub.subscribe() as lento, hub.subscribe() as rapido:
        await hub.esperar_conexao(1)
        for i in range(5):
            await eventos.put(str(i))
            assert await rapido.get(1) == str(i)
        # o lento nunca leu: ficou com os 2 primeiros e descartou 3
        assert lento.descartados == 3
        assert await lento.get(1) == "0"
    await hub.fechar()


async def test_get_hub_reusa_por_canal():
    nh._hubs.clear()
    assert nh.get_hub("a") is nh.get_hub("a")
    assert nh.get_hub("a") is not nh.get_hub("b")
    assert nh.hubs_ativos() == {"a": 0, "b": 0}
    await nh.fechar_hubs()
    assert nh.hubs_ativos() == {}
