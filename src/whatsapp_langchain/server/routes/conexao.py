"""CRUD + provisionamento de conexões WhatsApp do painel admin.

Sprint Conexões — 11 endpoints (5 CRUD + 3 WABA OAuth + 3 Evolution provision).

Padrão de erro: 503 quando integração não configurada (WABA App ou Evolution
admin credentials), 404 quando conexão inexistente, 403 cross-empresa.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from whatsapp_langchain.integrations.evolution import admin as evo_admin
from whatsapp_langchain.integrations.waba import oauth as waba_oauth
from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.shared.conexao import (
    get_conexao_by_id,
    get_credentials_decrypted,
    list_conexoes,
    mask_sensitive,
    patch_conexao,
    record_health_check,
    save_credentials,
    set_conexao_status,
    set_connection_state,
    set_qr_code,
    update_waba_fields,
    upsert_conexao,
)
from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.models import Conexao, ConexaoInput, ConexaoPatchInput

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/conexoes",
    tags=["conexoes"],
    dependencies=[Depends(verify_service_token)],
)


# ---------- legacy / CRUD básico ----------


@router.get("")
async def list_my_conexoes(
    empresa_id: int = Depends(get_empresa_context),
) -> dict[str, list[Conexao]]:
    """Lista conexões da empresa ativa, default primeiro."""
    pool = await get_pool()
    items = await list_conexoes(pool, empresa_id)
    return {"conexoes": [mask_sensitive(c) for c in items]}


@router.get("/{conexao_id}")
async def read_conexao(
    conexao_id: int,
    empresa_id: int = Depends(get_empresa_context),
) -> Conexao:
    pool = await get_pool()
    conexao = await get_conexao_by_id(pool, conexao_id)
    if conexao is None:
        raise HTTPException(status_code=404, detail="Conexão não encontrada.")
    if conexao.empresa_id != empresa_id:
        raise HTTPException(status_code=404, detail="Conexão não encontrada.")
    return mask_sensitive(conexao)


@router.post("")
async def create_conexao(
    body: ConexaoInput,
    empresa_id: int = Depends(get_empresa_context),
) -> Conexao:
    """Cria conexão Twilio (provider twilio_sandbox/twilio_prod).

    WABA usa /waba/finalize (após OAuth) e Evolution usa /evolution/provision.
    Twilio é o único path que mantém form simples.
    """
    pool = await get_pool()
    out = await upsert_conexao(pool, empresa_id, body)
    logger.info(
        "conexao_created",
        empresa_id=empresa_id,
        conexao_id=out.id,
        provider=out.provider,
    )
    return mask_sensitive(out)


@router.patch("/{conexao_id}")
async def patch_conexao_endpoint(
    conexao_id: int,
    body: ConexaoPatchInput,
    empresa_id: int = Depends(get_empresa_context),
) -> Conexao:
    pool = await get_pool()
    existing = await get_conexao_by_id(pool, conexao_id)
    if existing is None or existing.empresa_id != empresa_id:
        raise HTTPException(status_code=404, detail="Conexão não encontrada.")
    updated = await patch_conexao(
        pool,
        conexao_id,
        display_name=body.display_name,
        default_agent_id=body.default_agent_id,
        is_default=body.is_default,
        tipo_atendimento=body.tipo_atendimento,
        status=body.status,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Conexão não encontrada.")
    return mask_sensitive(updated)


@router.delete("/{conexao_id}", status_code=204)
async def disable_conexao(
    conexao_id: int,
    empresa_id: int = Depends(get_empresa_context),
) -> None:
    """Soft-delete (status='disabled'). Evolution: também desconecta instance."""
    pool = await get_pool()
    existing = await get_conexao_by_id(pool, conexao_id)
    if existing is None or existing.empresa_id != empresa_id:
        raise HTTPException(status_code=404, detail="Conexão não encontrada.")

    # Cleanup do provider antes do soft-delete (best-effort)
    if existing.provider == "evolution" and settings.evolution_admin_enabled:
        try:
            credentials = await get_credentials_decrypted(pool, conexao_id)
            inst = (credentials or {}).get(
                "instance_name"
            ) or existing.payload_json.get("instance_name")
            if inst:
                await evo_admin.disconnect_instance(inst)
        except Exception as exc:
            logger.warning("conexao_evolution_disconnect_failed", error=str(exc))

    await set_conexao_status(pool, conexao_id, "disabled")
    logger.info("conexao_disabled", empresa_id=empresa_id, conexao_id=conexao_id)


# ---------- WABA OAuth Embedded Signup ----------


class WabaOAuthStartInput(BaseModel):
    display_name: str | None = Field(default=None, max_length=80)


class WabaOAuthStartResponse(BaseModel):
    redirect_url: str
    state: str


@router.post("/waba/oauth/start")
async def waba_oauth_start(
    body: WabaOAuthStartInput,
    request: Request,
    empresa_id: int = Depends(get_empresa_context),
) -> WabaOAuthStartResponse:
    """Gera state CSRF + URL do Meta dialog. Front abre popup com redirect_url."""
    if not settings.waba_enabled:
        raise HTTPException(
            status_code=503,
            detail=(
                "Meta App não configurado. Setar "
                "META_APP_ID/META_APP_SECRET/META_CONFIG_ID."
            ),
        )
    user_id = get_user_id_from_request(request)
    state = waba_oauth.generate_state_token()

    pool = await get_pool()
    async with pool.connection() as conn:
        await conn.execute(
            """
            INSERT INTO waba_oauth_state (state, empresa_id, user_id, display_name)
            VALUES (%s, %s, %s, %s)
            """,
            (state, empresa_id, user_id, body.display_name),
        )

    return WabaOAuthStartResponse(
        redirect_url=waba_oauth.build_oauth_url(state), state=state
    )


@router.get("/waba/oauth/callback", include_in_schema=False)
async def waba_oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> Any:
    """Meta redireciona aqui após dialog. Persiste accounts + redirect front."""
    front_origin = (
        settings.frontend_origins_list[0]
        if settings.frontend_origins_list
        else "http://localhost:3000"
    )

    if error or not code or not state:
        reason = error or "missing_code"
        return RedirectResponse(
            url=f"{front_origin}/connections/oauth-callback?status=error&reason={reason}",
            status_code=302,
        )

    # Valida state + expira
    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            DELETE FROM waba_oauth_state WHERE state = %s
              AND expires_at > NOW()
            RETURNING empresa_id, user_id, display_name
            """,
            (state,),
        )
        row = await cur.fetchone()
    if row is None:
        return RedirectResponse(
            url=f"{front_origin}/connections/oauth-callback?status=error&reason=state_invalid",
            status_code=302,
        )
    empresa_id, user_id, display_name = row[0], row[1], row[2]

    # Troca code → token + lista accounts
    try:
        result = await waba_oauth.fetch_embedded_signup(code)
    except Exception:
        logger.exception("waba_oauth_exchange_error")
        return RedirectResponse(
            url=f"{front_origin}/connections/oauth-callback?status=error&reason=exchange_failed",
            status_code=302,
        )

    # Cache temporário do access_token + accounts (10min) pra finalize escolher account
    async with pool.connection() as conn:
        # Reuso waba_oauth_state como cache: re-insere state com dados
        import json as _json

        await conn.execute(
            """
            INSERT INTO waba_oauth_state (
                state, empresa_id, user_id, display_name, expires_at
            )
            VALUES (%s, %s, %s, %s, NOW() + INTERVAL '10 minutes')
            ON CONFLICT (state) DO UPDATE SET expires_at = EXCLUDED.expires_at
            """,
            (
                f"finalize_{state}",
                empresa_id,
                user_id,
                _json.dumps(
                    {
                        "access_token": result.access_token,
                        "accounts": [a.model_dump() for a in result.accounts],
                        "display_name": display_name,
                    }
                ),
            ),
        )

    return RedirectResponse(
        url=f"{front_origin}/connections/oauth-callback?status=ok&state={state}",
        status_code=302,
    )


@router.get("/waba/oauth/result")
async def waba_oauth_result(
    state: str,
    empresa_id: int = Depends(get_empresa_context),
) -> dict[str, Any]:
    """Front lê os accounts coletados no callback (pra picker)."""
    import json as _json

    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT display_name FROM waba_oauth_state
             WHERE state = %s AND empresa_id = %s AND expires_at > NOW()
            """,
            (f"finalize_{state}", empresa_id),
        )
        row = await cur.fetchone()
    if row is None or not row[0]:
        raise HTTPException(
            status_code=404, detail="OAuth result não encontrado ou expirado."
        )
    try:
        data = _json.loads(row[0])
    except Exception:
        raise HTTPException(status_code=500, detail="Cache OAuth corrompido.")
    # Sem retornar access_token bruto pro front — guarda no cache pra finalize
    return {
        "accounts": data.get("accounts", []),
        "display_name": data.get("display_name"),
    }


class WabaFinalizeInput(BaseModel):
    state: str
    waba_account_id: str
    phone_id: str
    display_name: str | None = None
    register_phone: bool = False
    pin: str | None = None


@router.post("/waba/finalize")
async def waba_finalize(
    body: WabaFinalizeInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> Conexao:
    """User escolheu account+phone — cria Conexao + cifra token + subscribe webhook."""
    import json as _json
    import secrets

    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            DELETE FROM waba_oauth_state WHERE state = %s AND empresa_id = %s
              AND expires_at > NOW()
            RETURNING display_name
            """,
            (f"finalize_{body.state}", empresa_id),
        )
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(status_code=400, detail="State inválido ou expirado.")

    try:
        cache = _json.loads(row[0])
    except Exception:
        raise HTTPException(status_code=500, detail="Cache OAuth corrompido.")

    access_token = cache.get("access_token")
    if not access_token:
        raise HTTPException(status_code=500, detail="access_token ausente no cache.")

    # Encontra phone + account_description no cache
    account = next(
        (a for a in cache.get("accounts", []) if a.get("id") == body.waba_account_id),
        None,
    )
    if account is None:
        raise HTTPException(
            status_code=400, detail="WABA account não encontrada no cache."
        )
    phone = next(
        (p for p in account.get("phone_numbers", []) if p.get("id") == body.phone_id),
        None,
    )
    if phone is None:
        raise HTTPException(
            status_code=400, detail="Phone não encontrado nessa account."
        )

    display = body.display_name or cache.get("display_name") or account.get("name")
    from_number = "+" + "".join(
        c for c in (phone.get("display_phone_number") or "") if c.isdigit()
    )

    # Cria Conexao base (precisa ID antes de salvar credentials)
    conexao = await upsert_conexao(
        pool,
        empresa_id,
        ConexaoInput(
            provider="waba",
            from_number=from_number,
            display_name=display,
            default_agent_id="vsa_tech",
            status="active",
            is_default=False,
            payload_json={},
        ),
    )

    # Cifra access_token
    await save_credentials(
        pool,
        conexao.id,
        {
            "access_token": access_token,
            "waba_account_id": body.waba_account_id,
            "phone_id": body.phone_id,
        },
    )
    # Webhook verify token único por conexão (ou compartilha settings se vazio)
    verify_token = (
        settings.waba_webhook_verify_token.get_secret_value()
        if settings.waba_webhook_verify_token
        else secrets.token_urlsafe(24)
    )
    await update_waba_fields(
        pool,
        conexao.id,
        waba_account_id=body.waba_account_id,
        waba_phone_id=body.phone_id,
        waba_app_id=settings.meta_app_id or None,
        waba_account_description=account.get("name"),
        webhook_verify_token=verify_token,
        from_number=from_number,
    )
    await set_connection_state(pool, conexao.id, state="open", message=None)

    # Register phone (best-effort) + subscribe webhook
    if body.register_phone:
        await waba_oauth.register_phone(access_token, body.phone_id, pin=body.pin)
    await waba_oauth.subscribe_webhook(access_token, body.waba_account_id)

    logger.info(
        "waba_conexao_finalized",
        empresa_id=empresa_id,
        user_id=user_id,
        conexao_id=conexao.id,
        waba_phone_id=body.phone_id,
    )
    return mask_sensitive(await get_conexao_by_id(pool, conexao.id) or conexao)


# ---------- Evolution auto-provision ----------


class EvolutionProvisionInput(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    instance_name: str | None = Field(default=None, max_length=80)


class EvolutionProvisionResponse(BaseModel):
    conexao_id: int
    qr_base64: str | None = None
    state: str
    expires_in: int = 45


@router.post("/evolution/provision")
async def evolution_provision(
    body: EvolutionProvisionInput,
    empresa_id: int = Depends(get_empresa_context),
) -> EvolutionProvisionResponse:
    """Cria instance no Evolution server + retorna QR base64 pra escanear."""
    if not settings.evolution_admin_enabled:
        raise HTTPException(
            status_code=503,
            detail=(
                "Evolution admin não configurado. Setar "
                "EVOLUTION_ADMIN_URL/EVOLUTION_GLOBAL_API_KEY."
            ),
        )

    import re

    # Gera instance_name slugificado se ausente
    instance_name = body.instance_name or (
        f"empresa{empresa_id}_"
        + re.sub(r"[^a-z0-9]+", "_", body.display_name.lower()).strip("_")[:40]
    )

    pool = await get_pool()

    webhook_url = (
        (settings.public_base_url.rstrip("/") + "/webhook/evolution")
        if settings.public_base_url
        else None
    )

    # Provision PRIMEIRO — se Evolution rejeita (401/4xx grave), aborta SEM
    # criar row no DB pra não deixar órfã. 409/403 = "já existe", segue.
    try:
        await evo_admin.provision_instance(instance_name, webhook_url=webhook_url)
    except evo_admin.EvolutionAdminError as exc:
        if exc.status_code not in (200, 201, 409, 403):
            raise HTTPException(
                status_code=502, detail=f"Evolution server: {exc.detail[:200]}"
            )

    # Pega QR (também antes da row — falha => sem órfã)
    try:
        qr_data = await evo_admin.connect_instance(instance_name)
    except evo_admin.EvolutionAdminError as exc:
        raise HTTPException(
            status_code=502, detail=f"Evolution connect: {exc.detail[:200]}"
        )

    # Provision + connect OK → AGORA cria a row Conexao
    placeholder_number = f"evolution:{instance_name}"
    conexao = await upsert_conexao(
        pool,
        empresa_id,
        ConexaoInput(
            provider="evolution",
            from_number=placeholder_number,
            display_name=body.display_name,
            default_agent_id="vsa_tech",
            status="active",
            is_default=False,
            payload_json={"instance_name": instance_name},
        ),
    )

    # Cifra credentials (instance_name + api_key — usa global se setada,
    # senão cai pra EVOLUTION_API_KEY)
    _key = settings.resolved_evolution_global_api_key
    await save_credentials(
        pool,
        conexao.id,
        {
            "instance_name": instance_name,
            "api_key": _key.get_secret_value() if _key else "",
            "api_url": settings.resolved_evolution_admin_url,
        },
    )

    qr_base64 = qr_data.get("base64") or qr_data.get("qrcode", {}).get("base64")
    expires_at = datetime.now(UTC) + timedelta(seconds=45)
    await set_qr_code(pool, conexao.id, qr_base64=qr_base64, expires_at=expires_at)

    logger.info(
        "evolution_provisioned",
        empresa_id=empresa_id,
        conexao_id=conexao.id,
        instance=instance_name,
    )
    return EvolutionProvisionResponse(
        conexao_id=conexao.id, qr_base64=qr_base64, state="qr_pending"
    )


@router.get("/{conexao_id}/qr")
async def get_qr(
    conexao_id: int,
    empresa_id: int = Depends(get_empresa_context),
) -> dict[str, Any]:
    """Retorna QR atual. Re-gera se expirou (Evolution only)."""
    pool = await get_pool()
    conexao = await get_conexao_by_id(pool, conexao_id)
    if conexao is None or conexao.empresa_id != empresa_id:
        raise HTTPException(status_code=404, detail="Conexão não encontrada.")
    if conexao.provider != "evolution":
        raise HTTPException(status_code=400, detail="QR só aplicável a Evolution.")
    if not settings.evolution_admin_enabled:
        raise HTTPException(status_code=503, detail="Evolution admin não configurado.")

    now = datetime.now(UTC)
    expired = conexao.qr_expires_at is None or conexao.qr_expires_at < now
    if expired:
        credentials = await get_credentials_decrypted(pool, conexao_id) or {}
        instance = credentials.get("instance_name") or conexao.payload_json.get(
            "instance_name"
        )
        if not instance:
            raise HTTPException(status_code=500, detail="instance_name ausente.")
        try:
            qr_data = await evo_admin.refresh_qr(instance)
        except evo_admin.EvolutionAdminError as exc:
            raise HTTPException(status_code=502, detail=str(exc.detail)[:200])
        qr_base64 = qr_data.get("base64") or qr_data.get("qrcode", {}).get("base64")
        expires_at = now + timedelta(seconds=45)
        await set_qr_code(pool, conexao_id, qr_base64=qr_base64, expires_at=expires_at)
        return {"qr_base64": qr_base64, "expires_in": 45, "state": "qr_pending"}

    expires_in = (
        int((conexao.qr_expires_at - now).total_seconds())
        if conexao.qr_expires_at is not None
        else 0
    )
    return {
        "qr_base64": conexao.qr_code,
        "expires_in": expires_in,
        "state": conexao.connection_state,
    }


@router.get("/{conexao_id}/status")
async def get_status(
    conexao_id: int,
    empresa_id: int = Depends(get_empresa_context),
) -> dict[str, Any]:
    """Polling-friendly: retorna state atual. Atualiza DB se Evolution mudou."""
    pool = await get_pool()
    conexao = await get_conexao_by_id(pool, conexao_id)
    if conexao is None or conexao.empresa_id != empresa_id:
        raise HTTPException(status_code=404, detail="Conexão não encontrada.")

    if conexao.provider == "evolution" and settings.evolution_admin_enabled:
        credentials = await get_credentials_decrypted(pool, conexao_id) or {}
        instance = credentials.get("instance_name") or conexao.payload_json.get(
            "instance_name"
        )
        if instance:
            try:
                raw_state = await evo_admin.get_connection_state(instance)
                new_state = evo_admin.normalize_state(raw_state)
                if new_state != conexao.connection_state:
                    await set_connection_state(pool, conexao_id, state=new_state)
                    conexao.connection_state = new_state
            except Exception as exc:
                logger.warning("evolution_state_check_failed", error=str(exc))

    return {
        "state": conexao.connection_state,
        "message": conexao.state_message,
        "is_active": conexao.connection_state in ("open", "ready"),
    }


@router.post("/{conexao_id}/test")
async def test_conexao(
    conexao_id: int,
    empresa_id: int = Depends(get_empresa_context),
) -> dict[str, Any]:
    """Health-check on-demand."""
    pool = await get_pool()
    conexao = await get_conexao_by_id(pool, conexao_id)
    if conexao is None or conexao.empresa_id != empresa_id:
        raise HTTPException(status_code=404, detail="Conexão não encontrada.")

    ok = False
    message = None

    try:
        if conexao.provider == "waba":
            credentials = await get_credentials_decrypted(pool, conexao_id)
            if not credentials:
                raise ValueError("Credenciais não configuradas.")
            # GET /me usando o token — confirma que ainda é válido
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"https://graph.facebook.com/{settings.waba_graph_api_version}/{credentials['phone_id']}",
                    headers={"Authorization": f"Bearer {credentials['access_token']}"},
                )
                ok = resp.status_code == 200
                if not ok:
                    message = f"Meta retornou {resp.status_code}: {resp.text[:200]}"

        elif conexao.provider == "evolution" and settings.evolution_admin_enabled:
            credentials = await get_credentials_decrypted(pool, conexao_id) or {}
            instance = credentials.get("instance_name") or conexao.payload_json.get(
                "instance_name"
            )
            if instance:
                raw_state = await evo_admin.get_connection_state(instance)
                state = evo_admin.normalize_state(raw_state)
                ok = state == "open"
                message = f"Evolution state: {state}"
                # Sincroniza connection_state com state real (test atua também
                # como manual refresh — útil pra rows criadas via "Importar
                # instance existente" que entram com state=pending)
                if state != conexao.connection_state:
                    await set_connection_state(pool, conexao_id, state=state)

        else:  # twilio_*
            ok = bool(settings.twilio_account_sid and settings.twilio_api_key_sid)
            message = "Twilio config OK" if ok else "Twilio env vars ausentes."

    except Exception as exc:
        message = str(exc)[:200]
        ok = False

    await record_health_check(pool, conexao_id, ok=ok, message=message)
    return {"ok": ok, "message": message}


@router.post("/{conexao_id}/disconnect")
async def disconnect_conexao(
    conexao_id: int,
    empresa_id: int = Depends(get_empresa_context),
) -> dict[str, Any]:
    """Desconecta sessão (Evolution: logout; WABA: revoke subscribed_apps)."""
    pool = await get_pool()
    conexao = await get_conexao_by_id(pool, conexao_id)
    if conexao is None or conexao.empresa_id != empresa_id:
        raise HTTPException(status_code=404, detail="Conexão não encontrada.")

    if conexao.provider == "evolution" and settings.evolution_admin_enabled:
        credentials = await get_credentials_decrypted(pool, conexao_id) or {}
        instance = credentials.get("instance_name") or conexao.payload_json.get(
            "instance_name"
        )
        if instance:
            try:
                await evo_admin.disconnect_instance(instance)
            except Exception as exc:
                logger.warning("evolution_disconnect_failed", error=str(exc))

    await set_connection_state(pool, conexao_id, state="disconnected")
    return {"ok": True, "state": "disconnected"}


# ---------- legacy test-evolution (mantém pra retrocompat) ----------


class TestEvolutionInput(BaseModel):
    api_url: str = Field(min_length=1, max_length=2048)
    api_key: str = Field(min_length=1, max_length=200)
    instance_name: str = Field(min_length=1, max_length=200)


class TestEvolutionResult(BaseModel):
    ok: bool
    state: str | None = None
    instance_name: str | None = None
    error: str | None = None


@router.post("/test-evolution")
async def test_evolution_connection(
    body: TestEvolutionInput,
    _empresa_id: int = Depends(get_empresa_context),
) -> TestEvolutionResult:
    """Mantém endpoint legado pro form Evolution manual (sem auto-provision)."""
    api_url = body.api_url.rstrip("/")
    target = f"{api_url}/instance/connectionState/{body.instance_name}"
    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            response = await http.get(target, headers={"apikey": body.api_key})
    except httpx.RequestError as exc:
        return TestEvolutionResult(ok=False, error=f"Erro de rede: {exc}")
    if response.status_code == 401:
        return TestEvolutionResult(ok=False, error="apikey inválida.")
    if response.status_code == 404:
        return TestEvolutionResult(
            ok=False, error=f"Instância '{body.instance_name}' não existe."
        )
    if not response.is_success:
        return TestEvolutionResult(
            ok=False, error=f"Evolution retornou {response.status_code}"
        )
    data = response.json()
    instance = data.get("instance") or {}
    state = instance.get("state") if isinstance(instance, dict) else None
    return TestEvolutionResult(
        ok=state in {"open", "connecting"},
        state=state,
        instance_name=body.instance_name,
    )
