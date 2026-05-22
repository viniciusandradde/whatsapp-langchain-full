"""Sprint B — Integração ASAAS (cobrança recorrente).

Doc oficial: https://docs.asaas.com/reference/

Sandbox: https://sandbox.asaas.com/api/v3
Production: https://api.asaas.com/v3
Auth: header `access_token: <api_key>`

Recursos usados:
- POST /customers — criar cliente Asaas (CPF/CNPJ + nome + email)
- POST /subscriptions — criar assinatura (cycle=MONTHLY)
- GET /subscriptions/{id}/payments — listar pagamentos
- DELETE /subscriptions/{id} — cancelar assinatura
- Webhook events: PAYMENT_CONFIRMED, PAYMENT_OVERDUE, etc.
"""

from whatsapp_langchain.integrations.asaas.client import (
    AsaasClient,
    AsaasError,
)

__all__ = ["AsaasClient", "AsaasError"]
