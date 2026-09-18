"""Loop de consumo do worker com N mensagens em voo (`WORKER_CONCURRENCY`).

`claim_next_message`, `process_message` e `_lease_heartbeat` são fakes
coordenados por `asyncio.Event` — nada de `sleep` global. Cada teste roda
`_loop_consumo` como task, dispara o cenário e encerra pelo `parar`.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest

from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.rls_context import get_request_context
from whatsapp_langchain.worker import main as worker_main
from whatsapp_langchain.worker.processor import WORKER_HEALTH

# O loop usa `asyncio.sleep` direto; o fixture o substitui por um gravador. Os
# helpers do teste precisam do original pra não contaminar a gravação.
_SLEEP_REAL = asyncio.sleep


@dataclass
class _Msg:
    id: int
    empresa_id: int = 1
    attempts: int = 1


@dataclass
class _Cenario:
    """Fila fake + registro do que o loop fez."""

    fila: list[_Msg]
    liberar: asyncio.Event = field(default_factory=asyncio.Event)
    claims: int = 0
    em_voo: int = 0
    pico: int = 0
    processadas: list[int] = field(default_factory=list)
    escopos: dict[int, tuple] = field(default_factory=dict)
    heartbeats_criados: int = 0
    heartbeats_cancelados: int = 0
    dormiu: list[float] = field(default_factory=list)
    inicio_processamento: list[int] = field(default_factory=list)
    claim_lanca_uma_vez: bool = False
    falhar_ids: set[int] = field(default_factory=set)

    async def claim(self, pool, lease_seconds):
        self.claims += 1
        if self.claim_lanca_uma_vez:
            self.claim_lanca_uma_vez = False
            raise RuntimeError("db caiu")
        return self.fila.pop(0) if self.fila else None

    async def process(self, message, pool, checkpointer=None, store=None):
        self.em_voo += 1
        self.pico = max(self.pico, self.em_voo)
        self.inicio_processamento.append(message.id)
        self.escopos[message.id] = get_request_context()
        try:
            await self.liberar.wait()
            if message.id in self.falhar_ids:
                raise RuntimeError(f"falhou {message.id}")
            self.processadas.append(message.id)
        finally:
            self.em_voo -= 1

    async def heartbeat(self, pool, message):
        self.heartbeats_criados += 1
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.heartbeats_cancelados += 1
            raise


@pytest.fixture
def cenario(monkeypatch):
    def _montar(msgs: list[int], *, n: int) -> tuple[_Cenario, asyncio.Event, set]:
        c = _Cenario(fila=[_Msg(i) for i in msgs])
        monkeypatch.setattr(worker_main, "claim_next_message", c.claim)
        monkeypatch.setattr(worker_main, "process_message", c.process)
        monkeypatch.setattr(worker_main, "_lease_heartbeat", c.heartbeat)
        monkeypatch.setattr(settings, "worker_concurrency", n)
        monkeypatch.setattr(settings, "poll_interval_seconds", 0.0)

        async def sleep_gravado(s):
            c.dormiu.append(s)
            await _SLEEP_REAL(0)

        monkeypatch.setattr(worker_main.asyncio, "sleep", sleep_gravado)
        WORKER_HEALTH.record_success()
        return c, asyncio.Event(), set()

    yield _montar
    WORKER_HEALTH.record_success()


async def _rodar(parar, em_voo):
    return asyncio.create_task(
        worker_main._loop_consumo(None, None, None, parar=parar, em_voo=em_voo)
    )


async def _ate(cond, timeout=2.0):
    """Espera uma condição sem sleep arbitrário."""
    async with asyncio.timeout(timeout):
        while not cond():
            await _SLEEP_REAL(0)


async def _encerrar(loop_task, parar, em_voo, c):
    parar.set()
    c.liberar.set()
    async with asyncio.timeout(2.0):
        await asyncio.gather(loop_task, *em_voo, return_exceptions=True)


async def test_n3_enche_os_slots_sem_dormir(cenario):
    """3 slots → 3 claims seguidos sem dormir e 3 mensagens em voo AO MESMO TEMPO."""
    c, parar, em_voo = cenario([1, 2, 3], n=3)
    loop_task = await _rodar(parar, em_voo)

    await _ate(lambda: c.em_voo == 3)
    await _SLEEP_REAL(0)
    assert c.pico == 3
    assert c.claims == 3, "com os 3 slots ocupados o loop espera, não reivindica"
    assert c.dormiu == [], "entre claims bem-sucedidos não há sleep"

    # Slots livres → volta a reivindicar; a fila vazia é o que faz dormir.
    c.liberar.set()
    await _ate(lambda: c.dormiu != [])
    assert c.dormiu[0] == 0.0

    await _encerrar(loop_task, parar, em_voo, c)
    assert sorted(c.processadas) == [1, 2, 3]


async def test_slot_liberado_apos_termino(cenario):
    """N=2 com 3 mensagens: a 3ª só começa depois que uma das duas termina."""
    c, parar, em_voo = cenario([1, 2, 3], n=2)
    loop_task = await _rodar(parar, em_voo)

    await _ate(lambda: c.em_voo == 2)
    await _SLEEP_REAL(0)
    assert c.inicio_processamento == [1, 2], "a 3ª não pode começar sem slot"

    c.liberar.set()
    await _ate(lambda: 3 in c.inicio_processamento)
    assert c.pico == 2

    await _encerrar(loop_task, parar, em_voo, c)


async def test_n1_equivale_ao_serial(cenario):
    """Com N=1 o 2º claim só acontece depois do 1º `process_message` terminar."""
    c, parar, em_voo = cenario([1, 2], n=1)
    loop_task = await _rodar(parar, em_voo)

    await _ate(lambda: c.em_voo == 1)
    await _SLEEP_REAL(0)
    assert c.claims == 1

    c.liberar.set()
    await _ate(lambda: c.processadas == [1, 2])
    assert c.pico == 1

    await _encerrar(loop_task, parar, em_voo, c)


async def test_none_dorme_poll_interval(cenario, monkeypatch):
    """Fila vazia → dorme `poll_interval_seconds` entre claims, sem ocupar slot."""
    c, parar, em_voo = cenario([], n=2)
    monkeypatch.setattr(settings, "poll_interval_seconds", 0.25)
    loop_task = await _rodar(parar, em_voo)

    await _ate(lambda: len(c.dormiu) >= 3)
    assert set(c.dormiu) == {0.25}
    assert em_voo == set()

    await _encerrar(loop_task, parar, em_voo, c)


async def test_excecao_na_task_nao_derruba_loop(cenario):
    """Falha numa mensagem: slot liberado, a próxima é processada, o loop segue."""
    c, parar, em_voo = cenario([1, 2], n=1)
    c.falhar_ids = {1}
    loop_task = await _rodar(parar, em_voo)

    await _ate(lambda: c.em_voo == 1)
    c.liberar.set()
    await _ate(lambda: c.processadas == [2])
    assert not loop_task.done()

    await _encerrar(loop_task, parar, em_voo, c)


async def test_claim_lancando_libera_slot(cenario):
    """Claim que lança não vaza slot: a mensagem seguinte ainda é processada."""
    c, parar, em_voo = cenario([1], n=1)
    c.claim_lanca_uma_vez = True
    loop_task = await _rodar(parar, em_voo)

    await _ate(lambda: c.em_voo == 1)
    assert c.claims == 2

    await _encerrar(loop_task, parar, em_voo, c)
    assert c.processadas == [1]


async def test_circuit_breaker_dispara_antes_do_claim(cenario):
    """Teto de falhas consecutivas → SystemExit ANTES de reivindicar."""
    c, parar, em_voo = cenario([1], n=2)
    for _ in range(worker_main.MAX_CONSECUTIVE_FAILURES):
        WORKER_HEALTH.record_failure()

    # Direto, não como task: SystemExit dentro de uma task sobe pelo event
    # loop inteiro, não pelo `await` — é assim que o processo morre de verdade.
    with pytest.raises(SystemExit):
        async with asyncio.timeout(2.0):
            await worker_main._loop_consumo(
                None, None, None, parar=parar, em_voo=em_voo
            )
    assert c.claims == 0
    WORKER_HEALTH.record_success()


async def test_empresa_scope_por_task(cenario):
    """Cada task enxerga o `empresa_id` da própria mensagem; o loop fica no default."""
    c, parar, em_voo = cenario([], n=2)
    c.fila = [_Msg(1, empresa_id=10), _Msg(2, empresa_id=20)]
    loop_task = await _rodar(parar, em_voo)

    await _ate(lambda: c.em_voo == 2)
    assert c.escopos[1] == (10, False)
    assert c.escopos[2] == (20, False)
    assert get_request_context() == (None, False)

    await _encerrar(loop_task, parar, em_voo, c)


async def test_heartbeat_por_mensagem_e_cancelado(cenario):
    """Um heartbeat por mensagem, cancelado quando ela termina."""
    c, parar, em_voo = cenario([1, 2], n=2)
    loop_task = await _rodar(parar, em_voo)

    await _ate(lambda: c.heartbeats_criados == 2)
    assert c.heartbeats_cancelados == 0

    c.liberar.set()
    await _ate(lambda: c.heartbeats_cancelados == 2)

    await _encerrar(loop_task, parar, em_voo, c)


async def test_parar_nao_cancela_em_voo_nem_reivindica_mais(cenario):
    """`parar` com os slots ocupados: o que está em voo termina; nada novo é reivindicado."""
    c, parar, em_voo = cenario([1, 2, 3], n=2)
    loop_task = await _rodar(parar, em_voo)

    await _ate(lambda: c.em_voo == 2)
    parar.set()
    await _SLEEP_REAL(0)
    assert c.em_voo == 2, "parar não pode cancelar o que está rodando"

    c.liberar.set()
    async with asyncio.timeout(2.0):
        await asyncio.gather(loop_task, *em_voo, return_exceptions=True)
    assert sorted(c.processadas) == [1, 2]
    assert c.claims == 2, "slot liberado depois do parar não vira mensagem nova"
    assert [m.id for m in c.fila] == [3]


async def test_esperar_em_voo_cancela_apos_grace(monkeypatch):
    """Shutdown espera o grace e cancela o que sobrou."""
    monkeypatch.setattr(worker_main, "SHUTDOWN_GRACE_SECONDS", 0.05)
    cancelada = asyncio.Event()

    async def eterna():
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelada.set()
            raise

    async def rapida():
        return None

    em_voo = {asyncio.create_task(eterna()), asyncio.create_task(rapida())}
    async with asyncio.timeout(2.0):
        await worker_main._esperar_em_voo(em_voo)
    assert cancelada.is_set()
