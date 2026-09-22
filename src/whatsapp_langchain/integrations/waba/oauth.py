"""OAuth Embedded Signup com Meta (WABA Cloud).

Fluxo (versão da Graph API vem de `WABA_GRAPH_API_VERSION`, hoje v25.0):
1. Front abre popup com URL gerada por `build_oauth_url` (dialog Meta)
2. User loga + escolhe Business + Phone Number
3. Meta redireciona pra nosso `redirect_uri` com `code`
4. Backend troca `code` por `access_token` via POST oauth/access_token
5. Backend lista WABA accounts disponíveis via GET /me/businesses
6. Se 1 só: cria Conexao auto. Se N: front mostra picker.
"""

from __future__ import annotations

import secrets
from typing import Any
from urllib.parse import urlencode

import httpx
import structlog

from whatsapp_langchain.integrations.waba.models import (
    WabaAccount,
    WabaEmbeddedSignupResult,
    WabaPhoneNumber,
)
from whatsapp_langchain.shared.config import settings

logger = structlog.get_logger()


META_DIALOG_URL = "https://www.facebook.com/{version}/dialog/oauth"
META_TOKEN_URL = "https://graph.facebook.com/{version}/oauth/access_token"
META_GRAPH_URL = "https://graph.facebook.com/{version}"

# Scopes mínimos pro Embedded Signup. `whatsapp_business_management` permite
# gerenciar WABA accounts; `whatsapp_business_messaging` permite enviar
# mensagens. `business_management` permite listar Business Manager accounts.
WABA_OAUTH_SCOPES = [
    "whatsapp_business_management",
    "whatsapp_business_messaging",
    "business_management",
]


class WabaOAuthError(Exception):
    """Erro no fluxo OAuth Meta (token exchange, listing, etc)."""


def generate_state_token() -> str:
    """Token CSRF aleatório pra parametro state do OAuth."""
    return secrets.token_urlsafe(32)


def build_oauth_url(state: str) -> str:
    """Monta URL do dialog Meta com extras pro Embedded Signup.

    `extras.feature='whatsapp_embedded_signup'` ativa o flow oficial:
    Meta mostra UI pra usuário escolher Business + Phone direto, em vez
    do OAuth padrão (que daria só token sem provisioning).
    """
    if not settings.waba_enabled:
        raise WabaOAuthError("Meta App não configurado (META_APP_ID/SECRET/CONFIG_ID)")

    base = META_DIALOG_URL.format(version=settings.waba_graph_api_version)
    params = {
        "client_id": settings.meta_app_id,
        "redirect_uri": settings.resolved_meta_oauth_redirect_uri,
        "state": state,
        "response_type": "code",
        "scope": ",".join(WABA_OAUTH_SCOPES),
        "extras": (
            '{"feature":"whatsapp_embedded_signup","sessionInfoVersion":3,'
            '"setup":{"solutionID":"' + settings.meta_config_id + '"}}'
        ),
    }
    return f"{base}?{urlencode(params)}"


async def exchange_code_for_token(code: str) -> dict[str, Any]:
    """Troca authorization code pelo access_token (long-lived).

    Retorno: {"access_token": str, "token_type": str, "expires_in": int?}
    """
    if not settings.waba_enabled or settings.meta_app_secret is None:
        raise WabaOAuthError("Meta App não configurado")

    url = META_TOKEN_URL.format(version=settings.waba_graph_api_version)
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            url,
            params={
                "client_id": settings.meta_app_id,
                "client_secret": settings.meta_app_secret.get_secret_value(),
                "redirect_uri": settings.resolved_meta_oauth_redirect_uri,
                "code": code,
            },
        )
        if resp.status_code != 200:
            logger.warning(
                "waba_oauth_exchange_failed",
                status=resp.status_code,
                body=resp.text[:500],
            )
            raise WabaOAuthError(f"Meta retornou {resp.status_code}: {resp.text[:200]}")
        return resp.json()


async def list_waba_accounts(access_token: str) -> list[WabaAccount]:
    """Lista WABA accounts visíveis com esse token + phones de cada.

    GET /me/businesses → ids
    GET /{biz_id}/owned_whatsapp_business_accounts → WABA ids
    GET /{waba_id}/phone_numbers → phones
    """
    version = settings.waba_graph_api_version
    headers = {"Authorization": f"Bearer {access_token}"}
    accounts: list[WabaAccount] = []

    async with httpx.AsyncClient(timeout=20) as client:
        biz_resp = await client.get(
            f"{META_GRAPH_URL.format(version=version)}/me/businesses",
            headers=headers,
        )
        biz_resp.raise_for_status()
        biz_ids = [b["id"] for b in biz_resp.json().get("data", [])]

        for biz_id in biz_ids:
            waba_resp = await client.get(
                f"{META_GRAPH_URL.format(version=version)}/{biz_id}/owned_whatsapp_business_accounts",
                headers=headers,
            )
            if waba_resp.status_code != 200:
                continue
            for waba in waba_resp.json().get("data", []):
                waba_id = waba["id"]
                phones_resp = await client.get(
                    f"{META_GRAPH_URL.format(version=version)}/{waba_id}/phone_numbers",
                    headers=headers,
                )
                phones_data = (
                    phones_resp.json().get("data", [])
                    if phones_resp.status_code == 200
                    else []
                )
                phones = [WabaPhoneNumber.model_validate(p) for p in phones_data]
                accounts.append(
                    WabaAccount(
                        id=waba_id,
                        name=waba.get("name", waba_id),
                        timezone_id=waba.get("timezone_id"),
                        message_template_namespace=waba.get(
                            "message_template_namespace"
                        ),
                        phone_numbers=phones,
                    )
                )

    return accounts


async def fetch_embedded_signup(code: str) -> WabaEmbeddedSignupResult:
    """Atalho: code → token → list accounts (1 round-trip da view do caller)."""
    token_data = await exchange_code_for_token(code)
    access_token = token_data["access_token"]
    accounts = await list_waba_accounts(access_token)
    return WabaEmbeddedSignupResult(
        access_token=access_token,
        token_type=token_data.get("token_type", "bearer"),
        expires_in=token_data.get("expires_in"),
        accounts=accounts,
    )


async def fetch_phone_details(
    access_token: str, phone_number_id: str
) -> dict[str, Any]:
    """GET /{phone_number_id} → display_phone_number + verified_name.

    Usado no Embedded Signup (FB SDK): o sessionInfo traz só o phone_number_id,
    então buscamos o número formatado + nome verificado pra montar from_number
    e display_name da conexão.
    """
    version = settings.waba_graph_api_version
    url = f"{META_GRAPH_URL.format(version=version)}/{phone_number_id}"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            params={"fields": "display_phone_number,verified_name,quality_rating"},
        )
        if resp.status_code != 200:
            logger.warning(
                "waba_fetch_phone_details_failed",
                phone_number_id=phone_number_id,
                status=resp.status_code,
                body=resp.text[:300],
            )
            raise WabaOAuthError(
                f"Falha ao buscar detalhes do phone: {resp.status_code}"
            )
        return resp.json()


async def register_phone(
    access_token: str, phone_id: str, pin: str | None = None
) -> bool:
    """Registra o número no WABA Cloud (necessário pra enviar mensagens).

    PIN é usado se 2FA tava habilitado no número antes. Pra novos números,
    omitir (Meta gera PIN automaticamente).

    POST /{phone_id}/register
    """
    version = settings.waba_graph_api_version
    url = f"{META_GRAPH_URL.format(version=version)}/{phone_id}/register"
    payload: dict[str, Any] = {"messaging_product": "whatsapp"}
    if pin:
        payload["pin"] = pin

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            json=payload,
        )
        if resp.status_code != 200:
            logger.warning(
                "waba_register_phone_failed",
                phone_id=phone_id,
                status=resp.status_code,
                body=resp.text[:300],
            )
            return False
        return True


async def subscribe_webhook(access_token: str, waba_account_id: str) -> bool:
    """Inscreve nosso app pra receber webhooks dessa WABA.

    POST /{waba_account_id}/subscribed_apps — Meta começa a entregar
    eventos `messages` + `message_template_status_update` pra URL configurada
    no App Dashboard.
    """
    version = settings.waba_graph_api_version
    url = f"{META_GRAPH_URL.format(version=version)}/{waba_account_id}/subscribed_apps"

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        if resp.status_code != 200:
            logger.warning(
                "waba_subscribe_failed",
                waba_id=waba_account_id,
                status=resp.status_code,
                body=resp.text[:300],
            )
            return False
        return True


async def list_phone_numbers(
    access_token: str, waba_account_id: str
) -> list[WabaPhoneNumber]:
    """GET /{waba_id}/phone_numbers → números da WABA.

    O Embedded Signup do Coexistence termina com
    `FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING`, cujo `data` traz só o `waba_id`
    — o `phone_number_id` sai daqui.
    """
    version = settings.waba_graph_api_version
    url = f"{META_GRAPH_URL.format(version=version)}/{waba_account_id}/phone_numbers"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            params={"fields": "id,display_phone_number,verified_name,quality_rating"},
        )
        if resp.status_code != 200:
            logger.warning(
                "waba_list_phone_numbers_failed",
                waba_id=waba_account_id,
                status=resp.status_code,
                body=resp.text[:300],
            )
            raise WabaOAuthError(
                f"Falha ao listar os números da WABA: {resp.status_code}"
            )
        return [WabaPhoneNumber.model_validate(p) for p in resp.json().get("data", [])]


#: Ordem da Meta: contatos primeiro, depois o histórico. As duas chamadas têm
#: de acontecer em até 24 h do onboarding, senão o número precisa ser
#: desconectado e conectado de novo.
SMB_SYNC_TYPES = ("smb_app_state_sync", "history")


async def sincronizar_smb(access_token: str, phone_id: str) -> dict[str, str | None]:
    """POST /{phone_id}/smb_app_data para cada `sync_type` (Coexistence).

    Devolve `{sync_type: request_id | None}` — `None` = aquela chamada falhou.
    Não levanta: quem chama decide o que fazer com a falha parcial (a conexão
    continua criada e a sincronização pode ser repetida pela rota
    `/waba/sincronizar` dentro das 24 h). O token nunca vai para o log.
    """
    version = settings.waba_graph_api_version
    url = f"{META_GRAPH_URL.format(version=version)}/{phone_id}/smb_app_data"
    resultado: dict[str, str | None] = {}
    async with httpx.AsyncClient(timeout=20) as client:
        for sync_type in SMB_SYNC_TYPES:
            try:
                resp = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {access_token}"},
                    json={"messaging_product": "whatsapp", "sync_type": sync_type},
                )
            except httpx.HTTPError as exc:
                logger.warning(
                    "waba_coexistence_sync_failed",
                    phone_id=phone_id,
                    sync_type=sync_type,
                    error=type(exc).__name__,
                )
                resultado[sync_type] = None
                continue
            if resp.status_code != 200:
                logger.warning(
                    "waba_coexistence_sync_failed",
                    phone_id=phone_id,
                    sync_type=sync_type,
                    status=resp.status_code,
                    body=resp.text[:300],
                )
                resultado[sync_type] = None
                continue
            request_id = resp.json().get("request_id")
            logger.info(
                "waba_coexistence_sync_requested",
                phone_id=phone_id,
                sync_type=sync_type,
                request_id=request_id,
            )
            resultado[sync_type] = request_id or ""
    return resultado
