"""CRUD + provisionamento de conexões WhatsApp do painel admin.

Sprint Conexões — 11 endpoints (5 CRUD + 3 WABA OAuth + 3 Evolution provision).

Padrão de erro: 503 quando integração não configurada (WABA App ou Evolution
admin credentials), 404 quando conexão inexistente, 403 cross-empresa.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, model_validator

from whatsapp_langchain.integrations.evolution import admin as evo_admin
from whatsapp_langchain.integrations.waba import oauth as waba_oauth
from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.server.dependencies_plano import (
    assert_plano_feature,
    require_plano_feature,
    require_plano_limit,
)
from whatsapp_langchain.server.dependencies_rbac import require_permission
from whatsapp_langchain.shared.conexao import (
    get_conexao_by_id,
    get_conexao_by_waba_phone_id,
    get_credentials_decrypted,
    hard_delete_conexao,
    list_conexoes,
    mask_sensitive,
    patch_conexao,
    record_health_check,
    save_credentials,
    set_conexao_from_number,
    set_conexao_status,
    set_connection_state,
    set_qr_code,
    update_waba_fields,
    upsert_conexao,
    validar_agente_da_empresa_para_ia,
)
from whatsapp_langchain.shared.conexao_quota import quota_status
from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.models import (
    PROVIDERS_SUPORTADOS,
    Conexao,
    ConexaoInput,
    ConexaoPatchInput,
)

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

    # Backfill do número real (mig PR #38): conexões Evolution conectadas que
    # ainda têm o placeholder `evolution:<inst>`. UMA chamada fetchInstances só
    # quando há placeholder (caso comum: nenhum → zero overhead). Best-effort.
    placeholders = [
        c
        for c in items
        if c.provider == "evolution"
        and (c.from_number or "").startswith("evolution:")
        and c.connection_state in ("open", "ready")
    ]
    if placeholders and settings.evolution_admin_enabled:
        try:
            numeros = await evo_admin.get_owner_numbers()
            for c in placeholders:
                inst = c.payload_json.get("instance_name")
                numero = numeros.get(inst) if inst else None
                if numero and numero != c.from_number:
                    await set_conexao_from_number(pool, c.id, numero)
                    c.from_number = numero
        except Exception as exc:
            logger.warning("conexao_list_backfill_numero_falhou", error=str(exc))

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
    _quota: None = Depends(require_plano_limit("conexoes")),
) -> Conexao:
    """Cria/atualiza uma conexão a partir de payload cru.

    Caminho usado pelo modal "Importar instance existente" da Evolution.
    O fluxo normal é `/evolution/provision` (QR) ou `/waba/finalize` (após
    o Embedded Signup) — aqui é o cadastro manual.

    Sprint Q.3: bloqueado com HTTP 402 se atingiu limite de conexões do
    plano (Free=1, Pro=3, Enterprise=∞).
    """
    if body.provider not in PROVIDERS_SUPORTADOS:
        raise HTTPException(
            status_code=422,
            detail=("Provider inválido: use 'waba' (WhatsApp Oficial) ou 'evolution'."),
        )
    # ADR-005 leva C1: cadastro manual de conexão WABA também depende do plano.
    if body.provider == "waba":
        await assert_plano_feature(
            empresa_id,
            "waba",
            mensagem=(
                "A conexão pela API oficial da Meta (WABA) não está incluída no "
                "seu plano. Faça upgrade para conectar."
            ),
        )
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
    # Modo IA só salva com um agente da empresa cadastrado — sem isso o worker
    # cairia no template de exemplo do catálogo (incidente 2026-08-19). O modo
    # e o agente efetivos são os do corpo se vierem, senão os já gravados.
    tipo_efetivo = (
        body.tipo_atendimento
        if body.tipo_atendimento is not None
        else existing.tipo_atendimento
    )
    agente_efetivo = (
        body.default_agent_id
        if body.default_agent_id is not None
        else existing.default_agent_id
    )
    erro_agente = await validar_agente_da_empresa_para_ia(
        pool, empresa_id, tipo_efetivo, agente_efetivo
    )
    if erro_agente:
        raise HTTPException(status_code=422, detail=erro_agente)
    # ADR-005 leva B: LIGAR a transcrição para o operador (uma chamada de LLM
    # por áudio) exige a feature no plano. Desligar sempre pode; interruptor
    # que ficou ligado de um plano antigo é o worker que ignora (degrada).
    if body.transcrever_audio_sempre is True and not existing.transcrever_audio_sempre:
        await assert_plano_feature(
            empresa_id,
            "transcricao_operador",
            mensagem=(
                "A transcrição automática de áudio para o operador não está "
                "incluída no seu plano. Faça upgrade para ligar."
            ),
        )
    updated = await patch_conexao(
        pool,
        conexao_id,
        display_name=body.display_name,
        default_agent_id=body.default_agent_id,
        is_default=body.is_default,
        tipo_atendimento=body.tipo_atendimento,
        status=body.status,
        daily_send_cap=body.daily_send_cap,
        warmup_enabled=body.warmup_enabled,
        resposta_agrupamento_segundos=body.resposta_agrupamento_segundos,
        transcrever_audio_sempre=body.transcrever_audio_sempre,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="Conexão não encontrada.")
    return mask_sensitive(updated)


@router.get("/{conexao_id}/quota")
async def read_conexao_quota(
    conexao_id: int,
    empresa_id: int = Depends(get_empresa_context),
) -> dict[str, object]:
    """Teto diário / aquecimento (anti-ban): teto efetivo do dia, quanto já
    saiu e quanto resta para esta conexão."""
    pool = await get_pool()
    conexao = await get_conexao_by_id(pool, conexao_id)
    if conexao is None or conexao.empresa_id != empresa_id:
        raise HTTPException(status_code=404, detail="Conexão não encontrada.")
    q = await quota_status(pool, conexao)
    return {
        "conexao_id": conexao_id,
        "cap": q.cap,
        "usados": q.usados,
        "restante": q.restante,
        "motivo": q.motivo,
        "daily_send_cap": conexao.daily_send_cap,
        "warmup_ativo": conexao.warmup_started_at is not None,
        "warmup_started_at": conexao.warmup_started_at,
    }


@router.delete("/{conexao_id}", status_code=204)
async def disable_conexao(
    conexao_id: int,
    empresa_id: int = Depends(get_empresa_context),
) -> None:
    """Exclusão total — sem deixar órfã. Evolution: DELETA a instance no
    servidor (não só logout). DB: hard-delete quando não há atendimento
    referenciando (FK RESTRICT); senão soft-delete (status='disabled') pra
    preservar o histórico de atendimentos."""
    pool = await get_pool()
    existing = await get_conexao_by_id(pool, conexao_id)
    if existing is None or existing.empresa_id != empresa_id:
        raise HTTPException(status_code=404, detail="Conexão não encontrada.")

    # Remove a instance no Evolution server (best-effort) ANTES de mexer no DB —
    # delete_instance (não disconnect) pra não deixar a instância órfã no server.
    if existing.provider == "evolution" and settings.evolution_admin_enabled:
        try:
            credentials = await get_credentials_decrypted(pool, conexao_id)
            inst = (credentials or {}).get(
                "instance_name"
            ) or existing.payload_json.get("instance_name")
            if inst:
                await evo_admin.delete_instance(inst)
        except Exception as exc:
            logger.warning("conexao_evolution_delete_failed", error=str(exc))

    # Tenta exclusão total; se um atendimento referenciar (FK RESTRICT), cai
    # pro soft-delete (que esconde da listagem) pra não perder histórico.
    removida = await hard_delete_conexao(pool, conexao_id, empresa_id)
    if not removida:
        await set_conexao_status(pool, conexao_id, "disabled")
    logger.info(
        "conexao_deleted",
        empresa_id=empresa_id,
        conexao_id=conexao_id,
        modo="hard" if removida else "soft",
    )


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
    # ADR-005 leva C1: a API oficial da Meta (WABA) é Pro/Enterprise (`waba`);
    # Evolution continua em todo plano.
    _plano: None = Depends(require_plano_feature("waba")),
) -> WabaOAuthStartResponse:
    """Gera state CSRF + URL do Meta dialog. Front abre popup com redirect_url.

    DEPRECIADO — fluxo por redirect, anterior ao Embedded Signup. Desde
    abr/2026 a Meta trata o Embedded Signup (`POST /waba/embedded-signup`)
    como caminho padrão de onboarding. Mantido só para não quebrar quem já
    tinha o popup antigo aberto; não construa nada novo em cima dele.
    """
    if not settings.waba_enabled:
        raise HTTPException(
            status_code=503,
            detail=MSG_WABA_DESLIGADO,
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


async def _create_waba_conexao(
    pool,
    *,
    empresa_id: int,
    access_token: str,
    waba_account_id: str,
    phone_id: str,
    display_name: str | None,
    account_description: str | None,
    from_number: str,
    register_phone: bool = False,
    pin: str | None = None,
    waba_mode: str = "cloud_api",
) -> Conexao:
    """Cria/atualiza conexão WABA + cifra token + registra phone + webhook.

    Núcleo compartilhado entre /waba/finalize (fluxo redirect legado) e
    /waba/embedded-signup (FB SDK). Idempotente via upsert por
    (empresa_id, from_number).

    `waba_mode="coexistence"` (mig 200): o número segue no WhatsApp Business
    do celular, então NÃO se chama `/register` (a Meta manda pular) e, depois
    de assinar o webhook, pede-se a sincronização de contatos e histórico
    (`smb_app_data`) — obrigatória em até 24 h do onboarding.
    """
    import secrets as _secrets

    conexao = await upsert_conexao(
        pool,
        empresa_id,
        ConexaoInput(
            provider="waba",
            from_number=from_number,
            display_name=display_name,
            default_agent_id="vsa_tech",
            status="active",
            is_default=False,
            payload_json={},
        ),
    )
    await save_credentials(
        pool,
        conexao.id,
        {
            "access_token": access_token,
            "waba_account_id": waba_account_id,
            "phone_id": phone_id,
            # PIN da verificação em duas etapas definido no registro (Cloud
            # API). Cifrado com o resto; um novo registro do mesmo número exige
            # o MESMO PIN. Nunca vai para log nem para resposta da API.
            **({"pin": pin} if pin and waba_mode != "coexistence" else {}),
        },
    )
    # NOTA: esta coluna é gravada mas NÃO é lida por ninguém — o handshake do
    # webhook (`webhook_waba.py`) compara sempre com o token GLOBAL do env,
    # porque a plataforma tem um app Meta só. Guardar por conexão é resquício
    # de um desenho multi-app que não existe. Fica como registro do que foi
    # usado no cadastro; se um dia houver app por empresa, é aqui que começa.
    verify_token = (
        settings.waba_webhook_verify_token.get_secret_value()
        if settings.waba_webhook_verify_token
        else _secrets.token_urlsafe(24)
    )
    await update_waba_fields(
        pool,
        conexao.id,
        waba_account_id=waba_account_id,
        waba_phone_id=phone_id,
        waba_app_id=settings.meta_app_id or None,
        waba_account_description=account_description,
        webhook_verify_token=verify_token,
        from_number=from_number,
        waba_mode=waba_mode,
    )
    coexistence = waba_mode == "coexistence"
    # O estado só é decidido DEPOIS de registrar o número e assinar o webhook.
    #
    # Antes, `state="open"` era gravado aqui em cima e os retornos das duas
    # chamadas eram descartados: a conexão aparecia "Conectada" na tela mesmo
    # quando o número não registrou ou o app não ficou inscrito nos webhooks —
    # ou seja, sem receber uma única mensagem. Tela que promete o que o backend
    # não cumpre é pior do que erro visível.
    problemas: list[str] = []
    if (
        register_phone
        and not coexistence
        and not await waba_oauth.register_phone(access_token, phone_id, pin=pin)
    ):
        problemas.append(
            "o número não foi registrado na Meta (confira o PIN de 6 dígitos: "
            "se o número já tinha verificação em duas etapas, use o mesmo PIN)"
        )
    if not await waba_oauth.subscribe_webhook(access_token, waba_account_id):
        problemas.append("o app não ficou inscrito nos webhooks (não recebe mensagem)")

    sincronizacao_pendente = False
    if coexistence and not problemas:
        sincronizacao_pendente = not await _sincronizar_coexistence(
            access_token, phone_id, conexao_id=conexao.id, empresa_id=empresa_id
        )

    if problemas:
        logger.warning(
            "waba_conexao_incompleta",
            conexao_id=conexao.id,
            empresa_id=empresa_id,
            problemas=problemas,
        )
        # "error", não "close": o CHECK de `connection_state` (mig 128) não
        # aceita "close" — o caminho de falha dava 500 justamente quando o
        # registro ou a inscrição falhavam.
        await set_connection_state(
            pool,
            conexao.id,
            state="error",
            message="Conexão criada, mas " + " e ".join(problemas) + ".",
        )
    elif sincronizacao_pendente:
        # A conexão funciona (recebe e envia); só falta trazer contatos e
        # histórico do celular — dá para repetir por /waba/sincronizar.
        await set_connection_state(
            pool, conexao.id, state="open", message=MSG_SINCRONIZACAO_PENDENTE
        )
    else:
        await set_connection_state(pool, conexao.id, state="open", message=None)
    return conexao


MSG_SINCRONIZACAO_PENDENTE = (
    "Sincronização de contatos e histórico pendente. Tente de novo em até 24 horas."
)


#: Aparece na tela de nova conexão — sem nome de variável (quem lê é o cliente).
#: Quem instala o ChatNexus acha o que falta no log e em `docs/WABA_SETUP.md`.
MSG_WABA_DESLIGADO = (
    "A conexão oficial com a Meta ainda não está disponível nesta instalação."
)


async def _sincronizar_coexistence(
    access_token: str, phone_id: str, *, conexao_id: int, empresa_id: int
) -> bool:
    """Pede à Meta contatos + histórico do WhatsApp Business (Coexistence).

    True quando as duas chamadas foram aceitas. Nunca levanta — a conexão já
    existe e funciona; a falha vira aviso na tela e a rota /waba/sincronizar.
    """
    resultado = await waba_oauth.sincronizar_smb(access_token, phone_id)
    ok = all(v is not None for v in resultado.values())
    logger.info(
        "waba_coexistence_onboarding",
        conexao_id=conexao_id,
        empresa_id=empresa_id,
        phone_id=phone_id,
        sync_ok=ok,
        request_ids=resultado,
    )
    return ok


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
    _quota: None = Depends(require_plano_limit("conexoes")),
    _plano: None = Depends(require_plano_feature("waba")),
) -> Conexao:
    """User escolheu account+phone — cria Conexao + cifra token + subscribe webhook.

    Sprint Q.3: bloqueado com 402 se limite de conexões do plano atingido.
    """
    import json as _json

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

    conexao = await _create_waba_conexao(
        pool,
        empresa_id=empresa_id,
        access_token=access_token,
        waba_account_id=body.waba_account_id,
        phone_id=body.phone_id,
        display_name=display,
        account_description=account.get("name"),
        from_number=from_number,
        register_phone=body.register_phone,
        pin=body.pin,
    )

    logger.info(
        "waba_conexao_finalized",
        empresa_id=empresa_id,
        user_id=user_id,
        conexao_id=conexao.id,
        waba_phone_id=body.phone_id,
    )
    return mask_sensitive(await get_conexao_by_id(pool, conexao.id) or conexao)


# ---------- WABA Embedded Signup (FB JS SDK — método oficial Meta) ----------


class WabaConfigResponse(BaseModel):
    app_id: str
    config_id: str
    graph_version: str


@router.get("/waba/config")
async def waba_config() -> WabaConfigResponse:
    """Config pública pro frontend inicializar o FB JS SDK.

    Retorna SÓ app_id + config_id (públicos por design — vão no FB.init/login).
    NUNCA retorna meta_app_secret. 503 se WABA não configurado."""
    if not settings.waba_enabled:
        raise HTTPException(
            status_code=503,
            detail=MSG_WABA_DESLIGADO,
        )
    return WabaConfigResponse(
        app_id=settings.meta_app_id,
        config_id=settings.meta_config_id,
        graph_version=settings.waba_graph_api_version,
    )


class WabaEmbeddedSignupInput(BaseModel):
    code: str = Field(min_length=10)
    waba_account_id: str = Field(min_length=1)
    # Opcional só em Coexistence: o evento FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING
    # traz só o `waba_id`, e o número sai de GET /{waba}/phone_numbers.
    phone_number_id: str | None = Field(default=None, min_length=1)
    display_name: str | None = Field(default=None, max_length=80)
    register_phone: bool = True
    waba_mode: Literal["cloud_api", "coexistence"] = "cloud_api"
    # PIN de 6 dígitos da verificação em duas etapas. A Meta EXIGE no
    # `POST /{phone}/register` (Cloud API) e um novo registro do mesmo número
    # tem de usar o mesmo PIN — por isso quem conecta escolhe e guarda. Não se
    # aplica ao Coexistence (o número do WhatsApp Business não é registrado).
    pin: str | None = Field(default=None, pattern=r"^\d{6}$")

    @model_validator(mode="after")
    def _pin_obrigatorio_no_registro(self) -> WabaEmbeddedSignupInput:
        if self.waba_mode == "cloud_api" and self.register_phone and not self.pin:
            raise ValueError("Informe o PIN de 6 dígitos do número.")
        return self


class WabaManualInput(BaseModel):
    """Conexão manual da API oficial (como a "configuração manual" do Chatwoot).

    Para número que já está ativo na Cloud API — o número de teste da Meta,
    ou um número que o cliente já usa na API — sem passar pelo cadastro
    incorporado. O token tem de ser de um usuário do sistema com acesso ao App
    do ChatNexus: o webhook confere a assinatura com o segredo do NOSSO App, e
    mensagem assinada por outro App seria rejeitada.
    """

    phone_number_id: str = Field(min_length=5, max_length=40, pattern=r"^\d+$")
    waba_account_id: str = Field(min_length=5, max_length=40, pattern=r"^\d+$")
    access_token: str = Field(min_length=20, max_length=2048)
    display_name: str | None = Field(default=None, max_length=80)


@router.post("/waba/manual")
async def waba_manual(
    body: WabaManualInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _quota: None = Depends(require_plano_limit("conexoes")),
    _perm: None = Depends(require_permission("integracao.manage")),
    _plano: None = Depends(require_plano_feature("waba")),
) -> Conexao:
    """Cria a conexão WABA a partir de ID do número + ID da conta + token.

    Valida na Meta antes de gravar: o número tem de existir para o token e
    pertencer à conta informada. Não registra o número (ele já está ativo na
    API); assina o webhook da conta. O token nunca volta na resposta nem vai
    para log.
    """
    if not settings.meta_app_secret:
        raise HTTPException(status_code=503, detail=MSG_WABA_DESLIGADO)

    pool = await get_pool()
    token = body.access_token.strip()

    try:
        phone = await waba_oauth.fetch_phone_details(token, body.phone_number_id)
    except waba_oauth.WabaOAuthError as exc:
        raise HTTPException(
            status_code=400,
            detail=(
                "A Meta não reconheceu o número com esse token. Confira o ID do "
                "número de telefone e se o token tem acesso a ele."
            ),
        ) from exc
    try:
        numeros = await waba_oauth.list_phone_numbers(token, body.waba_account_id)
    except waba_oauth.WabaOAuthError as exc:
        raise HTTPException(
            status_code=400,
            detail=(
                "A Meta não reconheceu a conta do WhatsApp Business com esse "
                "token. Confira o ID da conta."
            ),
        ) from exc
    if body.phone_number_id not in {n.id for n in numeros}:
        raise HTTPException(
            status_code=400,
            detail="Esse número não pertence à conta do WhatsApp Business informada.",
        )

    # Um número só pode estar ativo em uma conexão — senão o webhook resolveria
    # a mensagem para a empresa errada (o lookup é por phone_number_id).
    existente = await get_conexao_by_waba_phone_id(pool, body.phone_number_id)
    if existente is not None and existente.empresa_id != empresa_id:
        raise HTTPException(
            status_code=409,
            detail="Esse número já está conectado em outra empresa.",
        )

    from_number = "+" + "".join(
        c for c in (phone.get("display_phone_number") or "") if c.isdigit()
    )
    if from_number == "+":
        raise HTTPException(
            status_code=502, detail="A Meta não devolveu o número formatado."
        )
    display = body.display_name or phone.get("verified_name") or from_number

    conexao = await _create_waba_conexao(
        pool,
        empresa_id=empresa_id,
        access_token=token,
        waba_account_id=body.waba_account_id,
        phone_id=body.phone_number_id,
        display_name=display,
        account_description=phone.get("verified_name"),
        from_number=from_number,
        register_phone=False,
    )
    logger.info(
        "waba_conexao_manual_criada",
        empresa_id=empresa_id,
        user_id=user_id,
        conexao_id=conexao.id,
        waba_account_id=body.waba_account_id,
        phone_number_id=body.phone_number_id,
    )
    return mask_sensitive(await get_conexao_by_id(pool, conexao.id) or conexao)


@router.post("/waba/embedded-signup")
async def waba_embedded_signup(
    body: WabaEmbeddedSignupInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _quota: None = Depends(require_plano_limit("conexoes")),
    _perm: None = Depends(require_permission("integracao.manage")),
    _plano: None = Depends(require_plano_feature("waba")),
) -> Conexao:
    """Finaliza o Embedded Signup do FB SDK.

    O frontend captura o `code` (FB.login) + `waba_account_id`/`phone_number_id`
    (sessionInfo do evento WA_EMBEDDED_SIGNUP) e manda aqui. Trocamos o code por
    token, buscamos o número formatado e criamos a conexão WABA — sem precisar
    listar accounts (o sessionInfo já trouxe os IDs selecionados pelo user no
    popup oficial da Meta).
    """
    if not settings.waba_enabled:
        raise HTTPException(status_code=503, detail="Meta App não configurado.")

    pool = await get_pool()

    # 1) code → access_token
    try:
        token_data = await waba_oauth.exchange_code_for_token(body.code)
    except waba_oauth.WabaOAuthError as exc:
        logger.warning("waba_embedded_exchange_failed", error=str(exc))
        raise HTTPException(
            status_code=502, detail=f"Falha ao trocar code por token: {exc}"
        ) from exc
    access_token = token_data.get("access_token")
    if not access_token:
        raise HTTPException(status_code=502, detail="Meta não retornou access_token.")

    phone_number_id = body.phone_number_id
    if not phone_number_id:
        if body.waba_mode != "coexistence":
            raise HTTPException(
                status_code=422, detail="phone_number_id é obrigatório."
            )
        try:
            numeros = await waba_oauth.list_phone_numbers(
                access_token, body.waba_account_id
            )
        except waba_oauth.WabaOAuthError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        if len(numeros) != 1:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Não foi possível identificar o número desta conta do "
                    "WhatsApp Business. Conecte de novo escolhendo um único número."
                ),
            )
        phone_number_id = numeros[0].id

    # 2) detalhes do phone (display_phone_number + verified_name)
    try:
        phone = await waba_oauth.fetch_phone_details(access_token, phone_number_id)
    except waba_oauth.WabaOAuthError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    from_number = "+" + "".join(
        c for c in (phone.get("display_phone_number") or "") if c.isdigit()
    )
    if from_number == "+":
        raise HTTPException(
            status_code=502,
            detail="Meta não retornou display_phone_number do número.",
        )
    display = body.display_name or phone.get("verified_name") or from_number

    # 3) cria conexão (reusa helper compartilhado com /finalize)
    conexao = await _create_waba_conexao(
        pool,
        empresa_id=empresa_id,
        access_token=access_token,
        waba_account_id=body.waba_account_id,
        phone_id=phone_number_id,
        display_name=display,
        account_description=phone.get("verified_name"),
        from_number=from_number,
        register_phone=body.register_phone,
        pin=body.pin,
        waba_mode=body.waba_mode,
    )

    logger.info(
        "waba_embedded_signup_done",
        empresa_id=empresa_id,
        user_id=user_id,
        conexao_id=conexao.id,
        waba_account_id=body.waba_account_id,
        phone_number_id=phone_number_id,
        waba_mode=body.waba_mode,
    )
    return mask_sensitive(await get_conexao_by_id(pool, conexao.id) or conexao)


@router.post("/{conexao_id}/waba/sincronizar")
async def waba_sincronizar(
    conexao_id: int,
    empresa_id: int = Depends(get_empresa_context),
    _perm: None = Depends(require_permission("integracao.manage")),
    _plano: None = Depends(require_plano_feature("waba")),
) -> Conexao:
    """Repete a sincronização de contatos e histórico (Coexistence).

    A Meta exige as duas chamadas `smb_app_data` em até 24 h do onboarding;
    quando a do cadastro falhou, o operador repete por aqui.
    """
    pool = await get_pool()
    conexao = await get_conexao_by_id(pool, conexao_id)
    if conexao is None or conexao.empresa_id != empresa_id:
        raise HTTPException(status_code=404, detail="Conexão não encontrada.")
    if conexao.provider != "waba" or conexao.waba_mode != "coexistence":
        raise HTTPException(
            status_code=409,
            detail="Só conexões do WhatsApp Business com o ChatNexus sincronizam.",
        )
    creds = await get_credentials_decrypted(pool, conexao.id) or {}
    access_token = creds.get("access_token")
    if not access_token or not conexao.waba_phone_id:
        raise HTTPException(
            status_code=409,
            detail="Conexão sem credenciais. Conecte o número de novo.",
        )
    ok = await _sincronizar_coexistence(
        access_token,
        conexao.waba_phone_id,
        conexao_id=conexao.id,
        empresa_id=empresa_id,
    )
    if not ok:
        await set_connection_state(
            pool,
            conexao.id,
            state=conexao.connection_state,
            message=MSG_SINCRONIZACAO_PENDENTE,
        )
        raise HTTPException(
            status_code=502,
            detail="A Meta não aceitou a sincronização agora. Tente de novo em instantes.",
        )
    if conexao.state_message == MSG_SINCRONIZACAO_PENDENTE:
        await set_connection_state(
            pool, conexao.id, state=conexao.connection_state, message=None
        )
    return mask_sensitive(await get_conexao_by_id(pool, conexao.id) or conexao)


# ---------- Evolution auto-provision ----------


class EvolutionProvisionInput(BaseModel):
    display_name: str = Field(min_length=1, max_length=80)
    instance_name: str | None = Field(default=None, max_length=80)
    # Conexão por código de pareamento (alternativa ao QR): número com DDI.
    phone_number: str | None = Field(default=None, max_length=20)


class EvolutionProvisionResponse(BaseModel):
    conexao_id: int
    qr_base64: str | None = None
    # Código de pareamento (8 chars) quando phone_number foi informado.
    pairing_code: str | None = None
    state: str
    expires_in: int = 45


class PairingCodeInput(BaseModel):
    phone_number: str = Field(min_length=8, max_length=20)


class PairingCodeResponse(BaseModel):
    pairing_code: str | None = None
    state: str
    expires_in: int = 45


@router.post("/evolution/provision")
async def evolution_provision(
    body: EvolutionProvisionInput,
    empresa_id: int = Depends(get_empresa_context),
    _quota: None = Depends(require_plano_limit("conexoes")),
) -> EvolutionProvisionResponse:
    """Cria instance no Evolution server + retorna QR base64 pra escanear.

    Sprint Q.3: bloqueado com 402 se atingiu limite de conexões.
    """
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
    # criar row no DB pra não deixar órfã. 409/403 = "já existe", segue —
    # MAS um 403 de auth (key vazia) deve falhar com diagnóstico, não seguir.
    try:
        await evo_admin.provision_instance(instance_name, webhook_url=webhook_url)
    except evo_admin.EvolutionAdminError as exc:
        diag = evo_admin.classify_admin_error(exc)
        if diag:
            logger.warning(
                "evolution_auth_rejected",
                status=exc.status_code,
                key_source=evo_admin.describe_key_source(),
                admin_url=settings.resolved_evolution_admin_url,
                empresa_id=empresa_id,
            )
            raise HTTPException(status_code=502, detail=diag)
        if exc.status_code not in (200, 201, 409, 403):
            raise HTTPException(
                status_code=502, detail=f"Evolution server: {exc.detail[:200]}"
            )

    # Pega QR (escanear) OU pairing code (digitar) — também antes da row.
    try:
        qr_data = await evo_admin.connect_instance(
            instance_name, phone_number=body.phone_number
        )
    except evo_admin.EvolutionAdminError as exc:
        diag = evo_admin.classify_admin_error(exc)
        if diag:
            logger.warning(
                "evolution_auth_rejected",
                status=exc.status_code,
                key_source=evo_admin.describe_key_source(),
                admin_url=settings.resolved_evolution_admin_url,
                empresa_id=empresa_id,
            )
            raise HTTPException(status_code=502, detail=diag)
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

    expires_at = datetime.now(UTC) + timedelta(seconds=45)

    if body.phone_number:
        # Modo código de pareamento: persiste o código na coluna qr_code
        # (reuso) com estado distinto. Sem código = socket não pronto.
        pairing_code = qr_data.get("pairingCode")
        if not pairing_code:
            raise HTTPException(
                status_code=502,
                detail=(
                    "Evolution não retornou código de pareamento — gere "
                    "novamente em alguns segundos."
                ),
            )
        await set_qr_code(
            pool,
            conexao.id,
            qr_base64=pairing_code,
            expires_at=expires_at,
            state="pairing_code_pending",
        )
        logger.info(
            "evolution_provisioned",
            empresa_id=empresa_id,
            conexao_id=conexao.id,
            instance=instance_name,
            modo="pairing_code",
        )
        return EvolutionProvisionResponse(
            conexao_id=conexao.id,
            pairing_code=pairing_code,
            state="pairing_code_pending",
        )

    qr_base64 = qr_data.get("base64") or qr_data.get("qrcode", {}).get("base64")
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
            raise HTTPException(
                status_code=502,
                detail=evo_admin.classify_admin_error(exc) or str(exc.detail)[:200],
            )
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


@router.post("/{conexao_id}/pairing-code")
async def regenerate_pairing_code(
    conexao_id: int,
    body: PairingCodeInput,
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("conexao.write")),
) -> PairingCodeResponse:
    """Gera um novo código de pareamento (Evolution) pro número informado.

    Alternativa ao QR: o user digita o código no WhatsApp (Aparelhos conectados
    → Conectar com número de telefone). Precisa do número a cada chamada porque
    o Evolution repassa pro Baileys `requestPairingCode`.
    """
    pool = await get_pool()
    conexao = await get_conexao_by_id(pool, conexao_id)
    if conexao is None or conexao.empresa_id != empresa_id:
        raise HTTPException(status_code=404, detail="Conexão não encontrada.")
    if conexao.provider != "evolution":
        raise HTTPException(
            status_code=400, detail="Pairing code só aplicável a Evolution."
        )
    if not settings.evolution_admin_enabled:
        raise HTTPException(status_code=503, detail="Evolution admin não configurado.")

    credentials = await get_credentials_decrypted(pool, conexao_id) or {}
    instance = credentials.get("instance_name") or conexao.payload_json.get(
        "instance_name"
    )
    if not instance:
        raise HTTPException(status_code=500, detail="instance_name ausente.")

    try:
        data = await evo_admin.refresh_pairing_code(instance, body.phone_number)
    except evo_admin.EvolutionAdminError as exc:
        raise HTTPException(
            status_code=502,
            detail=evo_admin.classify_admin_error(exc) or str(exc.detail)[:200],
        )
    pairing_code = data.get("pairingCode")
    if not pairing_code:
        raise HTTPException(
            status_code=502,
            detail=(
                "Evolution não retornou código de pareamento — tente novamente "
                "em alguns segundos."
            ),
        )
    expires_at = datetime.now(UTC) + timedelta(seconds=45)
    await set_qr_code(
        pool,
        conexao_id,
        qr_base64=pairing_code,
        expires_at=expires_at,
        state="pairing_code_pending",
    )
    return PairingCodeResponse(pairing_code=pairing_code, state="pairing_code_pending")


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

            # Conectou e o from_number ainda é o placeholder `evolution:<inst>`?
            # Busca o número real (ownerJid) e grava — pro painel mostrar o número
            # em vez de "aguardando conexão". Best-effort (UNIQUE pode colidir).
            if conexao.connection_state in ("open", "ready") and (
                conexao.from_number or ""
            ).startswith("evolution:"):
                try:
                    numero = await evo_admin.get_instance_owner_number(instance)
                    if numero and numero != conexao.from_number:
                        await set_conexao_from_number(pool, conexao_id, numero)
                        conexao.from_number = numero
                except Exception as exc:
                    logger.warning("evolution_sync_numero_falhou", error=str(exc))

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

        else:
            message = f"Sem checagem de saúde para o provider {conexao.provider!r}."

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
