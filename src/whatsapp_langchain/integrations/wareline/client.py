"""Async HTTP client pra API Wareline ConecteHub.

Pattern:
    client = WarelineClient(pool, empresa_id=1)
    paciente = await client.buscar_paciente("12345678900")
    agenda = await client.listar_agenda_prestador("003297", "2025-08-01", "2025-08-31")
    resp = await client.criar_agendamento(CriarAgendamentoInput(...))

Retry exponencial em 5xx + rede (1s, 5s, 25s — pattern hook_dispatcher).
401 dispara invalidação do token cache + 1 retry com token novo.
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import structlog

from whatsapp_langchain.integrations.wareline.credentials import (
    get_credentials,
)
from whatsapp_langchain.integrations.wareline.errors import (
    WarelineAuthError,
    WarelineConfigError,
    WarelineError,
    WarelineNotFoundError,
    WarelineUnavailableError,
)
from whatsapp_langchain.integrations.wareline.models import (
    AgendaItem,
    AgendamentoResponse,
    CriarAgendamentoInput,
    Paciente,
)
from whatsapp_langchain.integrations.wareline.token import (
    get_or_refresh_token,
    invalidate_token,
)

logger = structlog.get_logger()

_REQUEST_TIMEOUT = 15.0
_RETRY_DELAYS = [1.0, 5.0, 25.0]  # 3 retries com backoff exponencial


class WarelineClient:
    """Cliente assíncrono pra Wareline. Stateless além do pool + empresa_id."""

    def __init__(self, pool: Any, empresa_id: int) -> None:
        self._pool = pool
        self._empresa_id = empresa_id

    async def _base_urls(self) -> tuple[str, str]:
        """Carrega URLs (modulos + services-pacientes) das credenciais."""
        creds = await get_credentials(self._pool, self._empresa_id)
        if creds is None:
            raise WarelineConfigError(
                f"Empresa {self._empresa_id} sem credenciais Wareline."
            )
        return creds.base_url, creds.pacientes_base_url

    async def _request(
        self,
        method: str,
        url: str,
        *,
        params: dict | None = None,
        json_body: dict | None = None,
        retry_on_401: bool = True,
    ) -> dict | list:
        """Wrapper httpx com auth + retry. Lança subclasses de WarelineError."""
        last_exc: Exception | None = None

        for attempt, delay in enumerate([0.0, *_RETRY_DELAYS]):
            if delay:
                await asyncio.sleep(delay)
            token = await get_or_refresh_token(self._pool, self._empresa_id)
            try:
                async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT) as client:
                    resp = await client.request(
                        method,
                        url,
                        params=params,
                        json=json_body,
                        headers={"Authorization": f"Bearer {token}"},
                    )
            except (httpx.TimeoutException, httpx.RequestError) as exc:
                last_exc = exc
                logger.warning(
                    "wareline_request_network_failed",
                    empresa_id=self._empresa_id,
                    url=url,
                    attempt=attempt,
                    error=str(exc),
                )
                continue  # retry

            # 401: token pode estar revogado server-side. Invalida cache + retry 1×
            if resp.status_code == 401 and retry_on_401:
                logger.info(
                    "wareline_401_invalidating_token",
                    empresa_id=self._empresa_id,
                    url=url,
                )
                await invalidate_token(self._pool, self._empresa_id)
                retry_on_401 = False  # só 1 retry desse tipo
                continue

            if resp.status_code == 401:
                raise WarelineAuthError("Token Wareline rejeitado mesmo após refresh")
            if resp.status_code == 404:
                raise WarelineNotFoundError(
                    f"Recurso não encontrado: {url} {params or json_body or ''}"
                )
            if resp.status_code >= 500:
                last_exc = WarelineUnavailableError(
                    f"Wareline retornou {resp.status_code}: {resp.text[:200]}"
                )
                logger.warning(
                    "wareline_5xx",
                    empresa_id=self._empresa_id,
                    url=url,
                    status=resp.status_code,
                    attempt=attempt,
                )
                continue  # retry
            if resp.status_code >= 400:
                raise WarelineError(
                    f"Wareline {resp.status_code} em {url}: {resp.text[:300]}"
                )

            return resp.json()

        # Esgotou retries
        if isinstance(last_exc, WarelineError):
            raise last_exc
        raise WarelineUnavailableError(
            f"Wareline esgotou {len(_RETRY_DELAYS)} retries em {url}: {last_exc!s}"
        )

    # ----- Endpoints -----

    async def buscar_paciente(self, cpf: str) -> list[Paciente]:
        """GET /services/utilitarios-api/pacientes?cpfpac=X

        Retorna lista (provider pode devolver duplicatas em raros casos).
        Lança WarelineNotFoundError se vazio.
        """
        _, pacientes_url = await self._base_urls()
        url = f"{pacientes_url}/services/utilitarios-api/pacientes"
        data = await self._request("GET", url, params={"cpfpac": cpf})
        if not isinstance(data, list) or not data:
            raise WarelineNotFoundError(f"Paciente CPF {cpf} não encontrado.")
        return [Paciente.model_validate(item) for item in data]

    async def listar_agenda_prestador(
        self,
        prestador: str,
        data_inicio: str,
        data_final: str,
        *,
        size: int = 20,
        page: int = 0,
    ) -> list[AgendaItem]:
        """GET /services/terapias-api/agendas/prestador

        Datas em YYYY-MM-DD. Retorna até `size` itens (default 20).
        """
        base_url, _ = await self._base_urls()
        url = f"{base_url}/services/terapias-api/agendas/prestador"
        data = await self._request(
            "GET",
            url,
            params={
                "prestador": prestador,
                "dataInicio": data_inicio,
                "dataFinal": data_final,
                "size": size,
                "page": page,
            },
        )
        if not isinstance(data, dict):
            raise WarelineError(
                f"Resposta inesperada de agenda prestador: {type(data)}"
            )
        content = data.get("content", [])
        return [AgendaItem.model_validate(item) for item in content]

    async def criar_agendamento(
        self, payload: CriarAgendamentoInput
    ) -> AgendamentoResponse:
        """POST /services/terapias-api/agendas — cria agendamento.

        Use SEMPRE depois de confirmar paciente + horário com cliente.
        """
        base_url, _ = await self._base_urls()
        url = f"{base_url}/services/terapias-api/agendas"
        body = payload.model_dump(mode="json")
        data = await self._request("POST", url, json_body=body)
        if not isinstance(data, dict):
            raise WarelineError(
                f"Resposta inesperada de criar_agendamento: {type(data)}"
            )
        return AgendamentoResponse.model_validate(data)
