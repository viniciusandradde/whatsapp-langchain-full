"""Um `LISTEN` por canal por processo, com fan-out em memória.

Antes, cada stream SSE (fila da empresa, conversa aberta no drawer, HITL)
abria uma conexão Postgres própria só pra `LISTEN` — uma conexão por aba por
operador. Com `max_connections=100`, ~30 operadores com duas abas e uma
conversa aberta esgotavam o banco antes de qualquer limite de CPU (achado
M3 do red team; decisão 6 do ADR-003). Aqui o processo mantém UMA conexão
por canal e entrega cada NOTIFY a N filas asyncio, uma por assinante.

Contrato:
- `subscribe(canal)` é um context manager assíncrono que devolve uma
  `Assinatura`; `await assinatura.get(timeout)` entrega o payload cru (str)
  ou levanta `TimeoutError` — o chamador usa isso pra mandar heartbeat.
- A conexão nasce com o primeiro assinante e vive até o shutdown do
  processo (`fechar_hubs()` no lifespan).
- Se a conexão cair, o hub reconecta com backoff e entrega `RESYNC` a todo
  assinante: evento pode ter se perdido no intervalo, e quem consome tem
  que recarregar o estado (o drawer já faz isso ao receber `connected`).
- Fila cheia (assinante lento) descarta o evento e loga — o cliente tem
  fallback por timer; segurar o produtor travaria todos os outros.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

import structlog

logger = structlog.get_logger()

RESYNC = "__resync__"
_TAMANHO_FILA = 256
_BACKOFF_S = (1, 2, 5, 10, 30)

ConnectFactory = Callable[[], Awaitable[Any]]


class Assinatura:
    def __init__(self, fila: asyncio.Queue[str]) -> None:
        self._fila = fila
        self.descartados = 0

    async def get(self, timeout: float) -> str:
        return await asyncio.wait_for(self._fila.get(), timeout)


class NotifyHub:
    def __init__(self, canal: str, connect: ConnectFactory) -> None:
        self.canal = canal
        self._connect = connect
        self._assinantes: set[Assinatura] = set()
        self._task: asyncio.Task[None] | None = None
        self._conectado = asyncio.Event()

    @property
    def assinantes(self) -> int:
        return len(self._assinantes)

    @contextlib.asynccontextmanager
    async def subscribe(self) -> AsyncIterator[Assinatura]:
        assinatura = Assinatura(asyncio.Queue(maxsize=_TAMANHO_FILA))
        self._assinantes.add(assinatura)
        if self._task is None or self._task.done():
            self._conectado.clear()
            self._task = asyncio.create_task(
                self._loop(), name=f"notify-hub:{self.canal}"
            )
        try:
            yield assinatura
        finally:
            self._assinantes.discard(assinatura)
            # A conexão fica viva mesmo sem assinante: é UMA por canal por
            # processo, e derrubá-la a cada "último saiu" só cria churn (e uma
            # corrida com o próximo "primeiro entrou"). Fecha no shutdown.

    async def fechar(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
            self._task = None
        self._conectado.clear()

    async def esperar_conexao(self, timeout: float = 10.0) -> bool:
        try:
            await asyncio.wait_for(self._conectado.wait(), timeout)
            return True
        except TimeoutError:
            return False

    def _entregar(self, payload: str) -> None:
        for a in list(self._assinantes):
            try:
                a._fila.put_nowait(payload)
            except asyncio.QueueFull:
                a.descartados += 1
                if a.descartados in (1, 100, 1000):
                    logger.warning(
                        "notify_hub_assinante_lento",
                        canal=self.canal,
                        descartados=a.descartados,
                    )

    async def _loop(self) -> None:
        tentativa = 0
        primeira = True
        while True:
            try:
                async with await self._connect() as conn:
                    await conn.execute(f"LISTEN {self.canal}")
                    tentativa = 0
                    self._conectado.set()
                    logger.info(
                        "notify_hub_conectado",
                        canal=self.canal,
                        assinantes=len(self._assinantes),
                        reconexao=not primeira,
                    )
                    if not primeira:
                        self._entregar(RESYNC)
                    primeira = False
                    async for notify in conn.notifies():
                        self._entregar(notify.payload)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001 — reconecta sempre
                self._conectado.clear()
                espera = _BACKOFF_S[min(tentativa, len(_BACKOFF_S) - 1)]
                tentativa += 1
                logger.warning(
                    "notify_hub_caiu",
                    canal=self.canal,
                    erro=str(exc)[:200],
                    reconecta_em_s=espera,
                    assinantes=len(self._assinantes),
                )
                await asyncio.sleep(espera)


_hubs: dict[str, NotifyHub] = {}


def _connect_padrao() -> Awaitable[Any]:
    import psycopg

    from whatsapp_langchain.shared.config import settings

    return psycopg.AsyncConnection.connect(settings.database_url, autocommit=True)


def get_hub(canal: str) -> NotifyHub:
    hub = _hubs.get(canal)
    if hub is None:
        hub = NotifyHub(canal, _connect_padrao)
        _hubs[canal] = hub
    return hub


def hubs_ativos() -> dict[str, int]:
    """Canal → assinantes. Pra health/relatório."""
    return {c: h.assinantes for c, h in _hubs.items()}


async def fechar_hubs() -> None:
    for hub in list(_hubs.values()):
        await hub.fechar()
    _hubs.clear()
