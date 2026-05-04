"""Endpoints de OAuth + config do Google Calendar (M5.a).

Fluxo:

  GET  /api/google-calendar/oauth/init  → retorna {authorize_url}
  GET  /api/google-calendar/oauth/callback?code&state  → finaliza, redireciona
  GET  /api/google-calendar/config      → status pra UI (sem token bruto)
  DEL  /api/google-calendar/config      → desconecta empresa

O `state` carrega `empresa_id` + assinatura HMAC pra evitar CSRF (o
Google ecoa o state inalterado no callback).
"""

from __future__ import annotations

import hashlib
import hmac
import json

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.shared.calendar_integration import (
    CalendarIntegrationError,
    build_authorization_url,
    disconnect_calendar,
    exchange_code_for_credentials,
    fetch_userinfo_email,
    get_calendar_config,
    is_oauth_configured,
    to_public,
    upsert_calendar_config,
)
from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.models import (
    CalendarConfigInput,
    CalendarConfigPublic,
)

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/google-calendar",
    tags=["google-calendar"],
)


def _state_secret() -> bytes:
    """Reusa INTERNAL_SERVICE_TOKEN como chave HMAC do state (já obrigatório)."""
    return settings.internal_service_token.encode("utf-8")


def _make_state(empresa_id: int, user_id: str) -> str:
    payload = json.dumps({"empresa_id": empresa_id, "user_id": user_id})
    sig = hmac.new(_state_secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{sig}:{payload}"


def _verify_state(state: str) -> dict:
    """Valida HMAC e devolve {empresa_id, user_id}."""
    try:
        sig, payload = state.split(":", 1)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="State malformado.") from e
    expected = hmac.new(
        _state_secret(), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(status_code=400, detail="State inválido (HMAC).")
    return json.loads(payload)


@router.get("/oauth/init", dependencies=[Depends(verify_service_token)])
async def oauth_init(
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    """Frontend chama → recebe a URL pra abrir num popup/tab."""
    if not is_oauth_configured():
        raise HTTPException(
            status_code=503,
            detail=(
                "Google OAuth não configurado no servidor. "
                "Defina GOOGLE_OAUTH_CLIENT_ID e GOOGLE_OAUTH_CLIENT_SECRET."
            ),
        )
    state = _make_state(empresa_id, user_id)
    try:
        url = build_authorization_url(state)
    except CalendarIntegrationError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    return {"authorize_url": url}


def _frontend_redirect(path: str) -> str:
    """Monta URL absoluta no host do frontend pra redirect pós-OAuth.

    O callback Google roda em `api.vsanexus.com` (porque é onde a rota
    está registrada), mas o painel UI vive em `chat.vsanexus.com` —
    redirect relativo iria pra `api.vsanexus.com/settings/...` (404).
    Usa a primeira origem de `FRONTEND_ORIGINS` como base.
    """
    origins = settings.frontend_origins_list
    base = origins[0].rstrip("/") if origins else ""
    return f"{base}{path}"


@router.get("/oauth/callback")
async def oauth_callback(
    code: str = Query(default=""),
    state: str = Query(default=""),
    error: str | None = Query(default=None),
) -> RedirectResponse:
    """Google redireciona pra cá após o user autorizar (ou cancelar).

    Sem `verify_service_token` — quem chama é o navegador do user, não o
    frontend server-side. A confiança vem do `state` HMAC-assinado +
    obrigatoriedade de a empresa_id existir no payload.
    """
    if error:
        # Esperado quando user clica "Cancelar" no consent — não é bug.
        logger.info("google_oauth_user_denied", error=error)
        return RedirectResponse(
            url=_frontend_redirect(
                "/settings/integracoes?google_calendar_error=user_denied"
            )
        )
    if not code or not state:
        raise HTTPException(status_code=400, detail="code/state ausentes no callback.")
    payload = _verify_state(state)
    empresa_id = int(payload["empresa_id"])
    user_id = str(payload["user_id"])

    try:
        creds = exchange_code_for_credentials(code)
    except CalendarIntegrationError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        logger.error("google_oauth_exchange_failed", error=str(e))
        raise HTTPException(status_code=400, detail=f"Falha ao trocar code: {e}") from e

    pool = await get_pool()
    email = fetch_userinfo_email(creds)
    await upsert_calendar_config(
        pool, empresa_id, creds=creds, google_email=email, user_id=user_id
    )
    logger.info(
        "google_calendar_connected",
        empresa_id=empresa_id,
        user_id=user_id,
        google_email=email,
    )
    # Redireciona pro painel com sucesso (URL absoluta no host do frontend).
    return RedirectResponse(
        url=_frontend_redirect("/settings/integracoes?google_calendar=ok")
    )


@router.get(
    "/config",
    dependencies=[Depends(verify_service_token)],
    response_model=CalendarConfigPublic | None,
)
async def get_config(
    empresa_id: int = Depends(get_empresa_context),
) -> CalendarConfigPublic | None:
    """Status pra UI — None = empresa não conectou ainda."""
    pool = await get_pool()
    config = await get_calendar_config(pool, empresa_id)
    return to_public(config) if config else None


@router.delete(
    "/config",
    status_code=204,
    dependencies=[Depends(verify_service_token)],
)
async def delete_config(
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> None:
    pool = await get_pool()
    deleted = await disconnect_calendar(pool, empresa_id)
    logger.info(
        "google_calendar_disconnected",
        empresa_id=empresa_id,
        user_id=user_id,
        deleted=deleted,
    )


@router.put(
    "/config",
    dependencies=[Depends(verify_service_token)],
    response_model=CalendarConfigPublic,
)
async def update_config(
    body: "CalendarConfigInput",
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> CalendarConfigPublic:
    """Atualiza campos editáveis da config (S4 UI: aprovador_telefone)."""
    from whatsapp_langchain.shared.calendar_integration import (
        update_aprovador_telefone,
    )
    from whatsapp_langchain.shared.empresa import is_admin_of

    pool = await get_pool()
    if not await is_admin_of(pool, empresa_id, user_id):
        raise HTTPException(
            status_code=403, detail="Só admin pode alterar config Calendar."
        )

    config = await get_calendar_config(pool, empresa_id)
    if config is None:
        raise HTTPException(
            status_code=404,
            detail="Calendar não conectado. Conecte primeiro via OAuth.",
        )

    if body.aprovador_telefone is not None:
        # Validação simples: vazia ou E.164 com +55XXXXXXXXX
        v = body.aprovador_telefone.strip()
        if v and not (v.startswith("+") and len(v) >= 10):
            raise HTTPException(
                status_code=422,
                detail="aprovador_telefone deve estar em E.164 (ex: +5567984249725) ou vazio.",
            )
        await update_aprovador_telefone(pool, empresa_id, v)
        logger.info(
            "google_calendar_aprovador_changed",
            empresa_id=empresa_id,
            user_id=user_id,
            telefone_set=bool(v),
        )

    config = await get_calendar_config(pool, empresa_id)
    assert config is not None
    return to_public(config)
