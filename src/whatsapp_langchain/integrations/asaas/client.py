"""Cliente HTTP Asaas v3.

Sprint B.1 — wrap mínimo de httpx.AsyncClient com:
- Auth automático via header `access_token`
- Base URL resolvida via `settings.asaas_base_url` (sandbox vs prod)
- Retry exponencial em 5xx (3 tentativas, 1s/2s/4s)
- Erros 4xx convertidos em `AsaasError` com detail user-friendly

Não-objetivos:
- Cobertura completa da API Asaas (só os 5-6 endpoints que usamos)
- Caching de respostas (cliente cria/lê em volume baixo)
"""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import structlog

from whatsapp_langchain.shared.config import settings

logger = structlog.get_logger()


class AsaasError(Exception):
    """Erro vindo da API Asaas (4xx ou 5xx após retries)."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        body: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.body = body or {}


class AsaasClient:
    """Wrap mínimo da API Asaas v3."""

    def __init__(self, *, timeout_seconds: float = 30.0):
        if not settings.asaas_enabled:
            raise AsaasError(
                "ASAAS_API_KEY não configurado. "
                "Setar em env vars + redeploy.",
                status_code=503,
            )
        self._key = settings.asaas_api_key.get_secret_value()  # type: ignore[union-attr]
        self._base = settings.asaas_base_url
        self._timeout = timeout_seconds

    def _headers(self) -> dict[str, str]:
        return {
            "access_token": self._key,
            "Content-Type": "application/json",
            "User-Agent": "chat-nexus-billing/1.0",
        }

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
    ) -> dict[str, Any]:
        url = f"{self._base}{path}"
        last_err: Exception | None = None
        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    resp = await client.request(
                        method, url,
                        headers=self._headers(),
                        json=json, params=params,
                    )
                # 4xx — erro do cliente, não retry
                if 400 <= resp.status_code < 500:
                    try:
                        body = resp.json()
                    except Exception:
                        body = {"raw": resp.text}
                    msg = self._extract_error_message(body, resp.status_code)
                    logger.warning(
                        "asaas_4xx",
                        method=method, path=path,
                        status=resp.status_code, body=body,
                    )
                    raise AsaasError(msg, status_code=resp.status_code, body=body)
                # 5xx — retry com backoff
                if resp.status_code >= 500:
                    last_err = AsaasError(
                        f"Asaas {resp.status_code}: {resp.text[:200]}",
                        status_code=resp.status_code,
                    )
                    if attempt < 2:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    raise last_err
                # 2xx ok
                resp.raise_for_status()
                return resp.json() if resp.content else {}
            except httpx.RequestError as exc:
                last_err = AsaasError(
                    f"Asaas connection error: {exc}", status_code=None
                )
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise last_err from exc
        raise last_err or AsaasError("Unknown Asaas error")

    @staticmethod
    def _extract_error_message(body: dict, status: int) -> str:
        """Asaas retorna {errors: [{code, description}]} em 4xx."""
        errs = body.get("errors") if isinstance(body, dict) else None
        if isinstance(errs, list) and errs:
            descs = [e.get("description", "") for e in errs if isinstance(e, dict)]
            return f"Asaas {status}: " + "; ".join(d for d in descs if d)
        return f"Asaas {status}: {body}"

    # ---- Customers ----

    async def create_customer(
        self,
        *,
        name: str,
        cpf_cnpj: str,
        email: str | None = None,
        phone: str | None = None,
        external_reference: str | None = None,
    ) -> dict:
        """POST /customers — retorna {id, name, email, cpfCnpj, ...}.

        external_reference: usado pra mapear customer Asaas → empresa interna
        (geralmente empresa_id como string).
        """
        body: dict[str, Any] = {"name": name, "cpfCnpj": cpf_cnpj}
        if email:
            body["email"] = email
        if phone:
            body["phone"] = phone
        if external_reference:
            body["externalReference"] = external_reference
        return await self._request("POST", "/customers", json=body)

    async def get_customer(self, customer_id: str) -> dict:
        return await self._request("GET", f"/customers/{customer_id}")

    async def list_customers_by_external_ref(self, ref: str) -> list[dict]:
        """Procura customer por external_reference (idempotência)."""
        resp = await self._request(
            "GET", "/customers", params={"externalReference": ref}
        )
        return resp.get("data", [])

    # ---- Subscriptions ----

    async def create_subscription(
        self,
        *,
        customer: str,
        value: float,
        next_due_date: str,  # YYYY-MM-DD
        cycle: str = "MONTHLY",
        billing_type: str = "UNDEFINED",  # CREDIT_CARD | BOLETO | PIX | UNDEFINED
        description: str | None = None,
        external_reference: str | None = None,
    ) -> dict:
        """POST /subscriptions — assinatura recorrente.

        billing_type=UNDEFINED deixa o cliente escolher na hora.
        next_due_date: data do primeiro vencimento (formato ISO).
        """
        body: dict[str, Any] = {
            "customer": customer,
            "value": value,
            "nextDueDate": next_due_date,
            "cycle": cycle,
            "billingType": billing_type,
        }
        if description:
            body["description"] = description
        if external_reference:
            body["externalReference"] = external_reference
        return await self._request("POST", "/subscriptions", json=body)

    async def cancel_subscription(self, subscription_id: str) -> dict:
        return await self._request("DELETE", f"/subscriptions/{subscription_id}")

    async def list_subscription_payments(self, subscription_id: str) -> list[dict]:
        resp = await self._request(
            "GET", f"/subscriptions/{subscription_id}/payments"
        )
        return resp.get("data", [])

    # ---- Payments (cobrança individual, fora de subscription) ----

    async def get_payment(self, payment_id: str) -> dict:
        return await self._request("GET", f"/payments/{payment_id}")

    async def get_payment_invoice_url(self, payment_id: str) -> str | None:
        """Retorna a URL pública da fatura (PDF + boleto/PIX/cartão)."""
        p = await self.get_payment(payment_id)
        return p.get("invoiceUrl")
