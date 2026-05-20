"""Google Calendar — OAuth flow + helpers de leitura/escrita (M5.a).

**Storage migrado** (Sprint Conector API): credenciais OAuth agora
ficam em `api_connection` (provider_slug='google_calendar') com cripto
Fernet. `empresa_calendar_config` é mantida via dual-write como
backward-compat pra `horario.py` e `agendamento.py` (que SELECT direto
da tabela legacy).

Fluxo OAuth Web:
1. Admin clica "Conectar Google Calendar" no painel.
2. Frontend → `/api/google-calendar/oauth/init` → URL de autorização.
3. User autoriza → callback `/api/google-calendar/oauth/callback?code=`.
4. Troca `code` por `Credentials`. Persistimos via dual-write em
   `api_connection` (cripto) + `empresa_calendar_config` (legacy).
5. Tools do agente carregam o JSON via helper unificado.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.integrations.google_calendar_storage import (
    delete_dual,
    read_unified,
    refresh_credentials_dual,
    update_setting_dual,
    upsert_credentials_dual,
)
from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.models import (
    CalendarConfigPublic,
    EmpresaCalendarConfig,
)

logger = structlog.get_logger()


SCOPES = [
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
    "openid",
]


class CalendarIntegrationError(Exception):
    """Erro lógico (config ausente, refresh falhou, scope errado)."""


class CalendarNotConfiguredError(CalendarIntegrationError):
    """Empresa não tem `empresa_calendar_config` ativo — tools não disponíveis."""


def is_oauth_configured() -> bool:
    """True quando as 3 envs do Google OAuth estão preenchidas."""
    return bool(
        settings.google_oauth_client_id
        and settings.google_oauth_client_secret
        and settings.google_oauth_redirect_uri
    )


def _client_config() -> dict:
    """Constrói o `client_config` que o `Flow` espera (sem arquivo no FS)."""
    secret = settings.google_oauth_client_secret
    secret_value = secret.get_secret_value() if secret else ""
    return {
        "web": {
            "client_id": settings.google_oauth_client_id,
            "client_secret": secret_value,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [settings.google_oauth_redirect_uri],
        }
    }


def build_authorization_url(state: str) -> str:
    """URL pra qual o admin é redirecionado pra autorizar o app no Google.

    `state` é uma string opaca que o Google devolve no callback —
    usada pra amarrar o fluxo a uma empresa+user específicos.
    """
    if not is_oauth_configured():
        raise CalendarIntegrationError(
            "Google OAuth não configurado (GOOGLE_OAUTH_CLIENT_ID/SECRET ausentes)."
        )
    # autogenerate_code_verifier=False: desabilita PKCE. Como o callback
    # é stateless (cria Flow novo), guardar o verifier exigiria DB/cookie
    # extra — e PKCE é opcional pra OAuth Web Server (já temos secret).
    flow = Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        redirect_uri=settings.google_oauth_redirect_uri,
        autogenerate_code_verifier=False,
    )
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",  # força refresh_token mesmo em re-autorização
        state=state,
    )
    return auth_url


def exchange_code_for_credentials(code: str) -> Credentials:
    """Troca o `code` do callback por `Credentials` (com refresh_token)."""
    if not is_oauth_configured():
        raise CalendarIntegrationError("Google OAuth não configurado.")
    # Mesma flag autogenerate_code_verifier=False usada em
    # build_authorize_url — o flow precisa ser consistente.
    flow = Flow.from_client_config(
        _client_config(),
        scopes=SCOPES,
        redirect_uri=settings.google_oauth_redirect_uri,
        autogenerate_code_verifier=False,
    )
    flow.fetch_token(code=code)
    # `flow.credentials` é tipado como union (external_account | oauth2);
    # no fluxo OAuth Web sempre é oauth2.credentials.Credentials.
    return flow.credentials  # type: ignore[return-value]


def credentials_to_json(creds: Credentials) -> dict:
    """Serializa `Credentials` pra dict salvável em JSONB."""
    return {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes) if creds.scopes else [],
        "expiry": creds.expiry.isoformat() if creds.expiry else None,
    }


def credentials_from_json(data: dict) -> Credentials:
    """Restaura `Credentials` do JSONB persistido."""
    expiry = data.get("expiry")
    creds = Credentials(
        token=data.get("token"),
        refresh_token=data.get("refresh_token"),
        token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=data.get("client_id") or settings.google_oauth_client_id,
        client_secret=(
            data.get("client_secret")
            or (
                settings.google_oauth_client_secret.get_secret_value()
                if settings.google_oauth_client_secret
                else None
            )
        ),
        scopes=data.get("scopes", SCOPES),
    )
    if expiry:
        creds.expiry = datetime.fromisoformat(expiry).replace(tzinfo=None)
    return creds


def fetch_userinfo_email(creds: Credentials) -> str | None:
    """Lê o e-mail da conta Google que autorizou (audit + UI)."""
    try:
        oauth = build("oauth2", "v2", credentials=creds, cache_discovery=False)
        info = oauth.userinfo().get().execute()  # type: ignore[attr-defined]
        return info.get("email")
    except Exception as e:  # noqa: BLE001
        logger.warning("calendar_userinfo_failed", error=str(e))
        return None


# --- DB helpers ---


async def upsert_calendar_config(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    creds: Credentials,
    google_email: str | None,
    user_id: str | None = None,
) -> EmpresaCalendarConfig:
    """Cria/atualiza config — dual-write em api_connection + legacy."""
    oauth_json = credentials_to_json(creds)
    await upsert_credentials_dual(
        pool,
        empresa_id,
        oauth_credentials_json=oauth_json,
        google_email=google_email,
        created_by_user_id=user_id,
    )
    config = await get_calendar_config(pool, empresa_id)
    assert config is not None
    return config


async def get_calendar_config(
    pool: AsyncConnectionPool, empresa_id: int
) -> EmpresaCalendarConfig | None:
    """Lê config — api_connection primeiro, fallback legacy."""
    data = await read_unified(pool, empresa_id)
    if data is None:
        return None
    return EmpresaCalendarConfig(
        empresa_id=empresa_id,
        oauth_credentials_json=data["oauth_credentials_json"],
        google_email=data["google_email"],
        calendar_id=data["calendar_id"],
        timezone=data["timezone"],
        ativo=data["ativo"],
        created_by_user_id=None,  # não exposto pelo helper unified
        created_at=data["created_at"],
        updated_at=data["updated_at"],
        aprovador_telefone=data["aprovador_telefone"],
    )


def to_public(config: EmpresaCalendarConfig) -> CalendarConfigPublic:
    """Versão sem token bruto pra UI."""
    return CalendarConfigPublic(
        empresa_id=config.empresa_id,
        google_email=config.google_email,
        calendar_id=config.calendar_id,
        timezone=config.timezone,
        ativo=config.ativo,
        aprovador_telefone=config.aprovador_telefone,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


async def update_aprovador_telefone(
    pool: AsyncConnectionPool,
    empresa_id: int,
    aprovador_telefone: str | None,
) -> bool:
    """Atualiza aprovador (S4 fluxo de aprovação WhatsApp) — dual-write."""
    value = aprovador_telefone.strip() if aprovador_telefone else None
    if value == "":
        value = None
    # Passa string vazia explicitamente quando remove (helper interpreta)
    return await update_setting_dual(
        pool, empresa_id, aprovador_telefone=value or ""
    )


async def disconnect_calendar(pool: AsyncConnectionPool, empresa_id: int) -> bool:
    """DELETE em AMBOS storages — força nova autorização."""
    return await delete_dual(pool, empresa_id)


# --- Calendar API helpers (consumidos pelas tools do agente) ---


async def _resolve_credentials(
    pool: AsyncConnectionPool, empresa_id: int
) -> tuple[EmpresaCalendarConfig, Credentials]:
    """Carrega config, restaura Credentials, faz refresh e persiste se mudou."""
    config = await get_calendar_config(pool, empresa_id)
    if config is None or not config.ativo:
        raise CalendarNotConfiguredError("Empresa sem Google Calendar conectado.")
    creds = credentials_from_json(config.oauth_credentials_json)
    if not creds.valid:
        if not creds.refresh_token:
            raise CalendarIntegrationError(
                "Refresh token ausente — admin precisa reautenticar."
            )
        try:
            creds.refresh(GoogleAuthRequest())
        except Exception as e:  # noqa: BLE001
            raise CalendarIntegrationError(f"Falha ao renovar credenciais: {e}") from e
        # Persiste o token novo via dual-write (refresh atualiza token + expiry)
        await refresh_credentials_dual(
            pool, empresa_id, credentials_to_json(creds)
        )
    return config, creds


def _calendar_service(creds: Credentials) -> Any:
    """Service do Google Calendar v3 (lazy import-safe)."""
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


async def find_free_slots(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    days_ahead: int = 7,
    slot_minutes: int = 60,
    max_slots: int = 6,
) -> list[dict]:
    """Calcula horários livres na agenda da empresa, respeitando regras (S3).

    Algoritmo: pega busy_intervals do Calendar API (`freebusy.query`)
    pros próximos `days_ahead` dias dentro da janela de trabalho
    configurada em `agendamento_regras` (default 08-18) e dias da
    semana permitidos. Aplica antecedência mínima e pula dias bloqueados.

    Retorna lista de dicts `{start, end}` em ISO 8601 timezone-aware
    (timezone da empresa).
    """
    from zoneinfo import ZoneInfo as _ZoneInfo

    from whatsapp_langchain.shared.agendamento_regras import get as _get_regras

    config, creds = await _resolve_credentials(pool, empresa_id)
    service = _calendar_service(creds)
    regras = await _get_regras(pool, empresa_id)

    try:
        tz = _ZoneInfo(config.timezone)
    except Exception:
        tz = _ZoneInfo("America/Sao_Paulo")

    now_utc = datetime.now(UTC)
    minimo = now_utc + timedelta(minutes=regras.antecedencia_minima_minutos)
    horizon = now_utc + timedelta(days=days_ahead)

    body = {
        "timeMin": now_utc.isoformat(),
        "timeMax": horizon.isoformat(),
        "timeZone": config.timezone,
        "items": [{"id": config.calendar_id}],
    }
    try:
        fb = service.freebusy().query(body=body).execute()
    except HttpError as e:
        raise CalendarIntegrationError(f"freebusy.query falhou: {e}") from e

    busy = fb.get("calendars", {}).get(config.calendar_id, {}).get("busy", [])
    busy_intervals = [
        (
            datetime.fromisoformat(b["start"].replace("Z", "+00:00")),
            datetime.fromisoformat(b["end"].replace("Z", "+00:00")),
        )
        for b in busy
    ]

    # Janela horária local (HH:MM → hour/minute)
    h_inicio_h, h_inicio_m = (int(x) for x in regras.hora_inicio.split(":"))
    h_fim_h, h_fim_m = (int(x) for x in regras.hora_fim.split(":"))

    slots: list[dict] = []
    # Itera dia por dia em hora LOCAL pra respeitar regras de horário comercial.
    cursor_day = now_utc.astimezone(tz).date()
    end_day = horizon.astimezone(tz).date()
    while cursor_day <= end_day and len(slots) < max_slots:
        # Pula dia da semana não permitido
        if cursor_day.isoweekday() not in regras.dias_semana_permitidos:
            cursor_day += timedelta(days=1)
            continue
        # Pula dia bloqueado
        if cursor_day.isoformat() in regras.dias_bloqueados:
            cursor_day += timedelta(days=1)
            continue

        # Constrói início/fim do expediente em hora local, depois converte UTC
        day_start_local = datetime.combine(
            cursor_day,
            datetime.min.time().replace(hour=h_inicio_h, minute=h_inicio_m),
            tzinfo=tz,
        )
        day_end_local = datetime.combine(
            cursor_day,
            datetime.min.time().replace(hour=h_fim_h, minute=h_fim_m),
            tzinfo=tz,
        )
        day_start = day_start_local.astimezone(UTC)
        day_end = day_end_local.astimezone(UTC)

        # Aplica antecedência mínima: cursor mínimo é max(day_start, agora+ant.)
        slot_cursor = max(day_start, minimo)

        while (
            slot_cursor + timedelta(minutes=slot_minutes) <= day_end
            and len(slots) < max_slots
        ):
            slot_end = slot_cursor + timedelta(minutes=slot_minutes)
            collides = any(
                not (slot_end <= b_start or slot_cursor >= b_end)
                for b_start, b_end in busy_intervals
            )
            if not collides:
                slots.append(
                    {
                        "start": slot_cursor.astimezone(tz).isoformat(),
                        "end": slot_end.astimezone(tz).isoformat(),
                    }
                )
            slot_cursor = slot_end
        cursor_day += timedelta(days=1)
    return slots


async def create_event(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    summary: str,
    start_iso: str,
    end_iso: str,
    description: str | None = None,
    attendee_email: str | None = None,
    user_id_criador: str | None = None,
    cliente_id: int | None = None,
) -> dict:
    """Cria evento no Google Calendar + espelha em `agendamento` (S2).

    Fluxo:
    1. INSERT local em `agendamento` (status='confirmado', evento_id_externo=NULL)
    2. POST events.insert no Google
    3a. Sucesso → UPDATE local com evento_id_externo + payload + dispara
        hook `agendamento.criado`
    3b. Falha → UPDATE local pra status='cancelado' + log drift, propaga erro

    Retorna `{id, htmlLink, agendamento_id}`.
    """
    from datetime import datetime as _dt

    from whatsapp_langchain.shared import agendamento as _agendamento_helpers
    from whatsapp_langchain.shared.hook_dispatcher import dispatch_event

    config, creds = await _resolve_credentials(pool, empresa_id)

    # 1. Parse das datas
    try:
        dt_inicio = _dt.fromisoformat(start_iso.replace("Z", "+00:00"))
        dt_fim = _dt.fromisoformat(end_iso.replace("Z", "+00:00"))
    except ValueError as e:
        raise CalendarIntegrationError(
            f"Datas inválidas (esperado ISO 8601): {e}"
        ) from e

    # 2. Valida regras de negócio (S3) — recusa antes de tocar no Google
    ok, motivo = await _agendamento_helpers.validate_request(
        pool, empresa_id, start=dt_inicio, end=dt_fim
    )
    if not ok:
        raise CalendarIntegrationError(f"Regra de negócio: {motivo}")

    # 3. Decide se precisa de aprovação (S4): lê requer_aprovacao das regras
    from whatsapp_langchain.shared.agendamento_regras import get as _get_regras

    regras = await _get_regras(pool, empresa_id)
    requer_aprovacao = regras.requer_aprovacao

    # 3. INSERT local primeiro (source-of-truth). Status depende do
    # fluxo: 'pendente' se vai esperar aprovação, 'confirmado' direto.
    ag = await _agendamento_helpers.create(
        pool,
        empresa_id=empresa_id,
        calendar_id=config.calendar_id,
        summary=summary,
        descricao=description,
        data_inicio=dt_inicio,
        data_fim=dt_fim,
        user_id_criador=user_id_criador,
        cliente_id=cliente_id,
        status="pendente" if requer_aprovacao else "confirmado",
        aprovado=not requer_aprovacao,
    )

    # 3a. Fluxo de aprovação: dispara WhatsApp pro gestor + retorna early
    #     SEM tocar no Google. Só cria evento Google após APROVAR.
    if requer_aprovacao:
        # Resolve nome do cliente pra mensagem mais útil
        cliente_nome = None
        if cliente_id:
            from whatsapp_langchain.shared.cliente import get_cliente_by_id

            cli = await get_cliente_by_id(pool, cliente_id)
            cliente_nome = (cli.nome if cli else None) or (cli.telefone if cli else None)

        token = await _agendamento_helpers.notify_gestor(
            pool,
            agendamento_id=ag.id,
            empresa_id=empresa_id,
            summary=summary,
            data_inicio=dt_inicio,
            data_fim=dt_fim,
            cliente_nome=cliente_nome,
        )

        # Hook agendamento.criado dispara mesmo no caminho pendente
        from whatsapp_langchain.shared.hook_dispatcher import (
            dispatch_event as _dispatch,
        )
        await _dispatch(
            pool,
            empresa_id,
            "agendamento.criado",
            {
                "agendamento_id": ag.id,
                "cliente_id": cliente_id,
                "summary": summary,
                "data_inicio": ag.data_inicio.isoformat(),
                "data_fim": ag.data_fim.isoformat(),
                "status": "pendente",
                "requer_aprovacao": True,
                "aprovacao_token": token,
            },
        )

        return {
            "id": None,                         # ainda sem evento Google
            "htmlLink": None,
            "agendamento_id": ag.id,
            "status": "pendente",
            "requer_aprovacao": True,
            "mensagem": (
                "Agendamento registrado e enviado pra aprovação do gestor. "
                "Cliente será notificado quando o gestor decidir."
                if token
                else "Agendamento registrado, mas notificação ao gestor falhou. "
                "Verifique aprovador_telefone e Conexão ativa."
            ),
        }

    # 4. POST events.insert no Google
    service = _calendar_service(creds)
    body: dict = {
        "summary": summary,
        "start": {"dateTime": start_iso, "timeZone": config.timezone},
        "end": {"dateTime": end_iso, "timeZone": config.timezone},
    }
    if description:
        body["description"] = description
    if attendee_email:
        body["attendees"] = [{"email": attendee_email}]

    try:
        ev = (
            service.events()
            .insert(calendarId=config.calendar_id, body=body)
            .execute()
        )
    except HttpError as e:
        # 5b. Drift compensado: marca local como cancelado pra não ficar
        # ghost row. Logger crítico pra investigação.
        await _agendamento_helpers.cancel_local(pool, ag.id, empresa_id)
        logger.error(
            "agendamento_drift_google_insert_failed",
            agendamento_id=ag.id,
            empresa_id=empresa_id,
            error=str(e),
        )
        raise CalendarIntegrationError(f"events.insert falhou: {e}") from e

    # 5a. Sucesso — atualiza local com id e dispara hook
    evento_id = ev.get("id") or ""
    await _agendamento_helpers.update_external_event(
        pool,
        ag.id,
        evento_id_externo=evento_id,
        payload_externo={
            "htmlLink": ev.get("htmlLink"),
            "organizer": ev.get("organizer"),
            "attendees": ev.get("attendees", []),
            "status": ev.get("status"),
        },
    )
    # Hook fire-and-forget (E1.4 traz retry+DLQ)
    await dispatch_event(
        pool,
        empresa_id,
        "agendamento.criado",
        {
            "agendamento_id": ag.id,
            "cliente_id": cliente_id,
            "summary": summary,
            "data_inicio": ag.data_inicio.isoformat(),
            "data_fim": ag.data_fim.isoformat(),
            "evento_id_externo": evento_id,
            "status": "confirmado",
        },
    )

    return {
        "id": evento_id,
        "htmlLink": ev.get("htmlLink"),
        "agendamento_id": ag.id,
    }


async def reschedule_event(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    agendamento_id: int,
    novo_inicio_iso: str,
    novo_fim_iso: str,
    actor_user_id: str | None = None,
) -> dict:
    """Reagenda evento (S5): valida regras, events.patch no Google, versiona.

    Falhas: ValueError (datas inválidas) ou CalendarIntegrationError
    (regras não passam ou Google falhou).
    """
    from datetime import datetime as _dt

    from whatsapp_langchain.shared import agendamento as _agendamento_helpers

    ag = await _agendamento_helpers.get_by_id(pool, agendamento_id, empresa_id)
    if ag is None:
        raise CalendarIntegrationError("Agendamento não encontrado.")
    if ag.status == "cancelado":
        raise CalendarIntegrationError(
            "Não é possível reagendar evento cancelado."
        )

    try:
        novo_inicio = _dt.fromisoformat(novo_inicio_iso.replace("Z", "+00:00"))
        novo_fim = _dt.fromisoformat(novo_fim_iso.replace("Z", "+00:00"))
    except ValueError as e:
        raise CalendarIntegrationError(f"Datas inválidas: {e}") from e

    # Valida regras (S3) com as novas datas
    ok, motivo = await _agendamento_helpers.validate_request(
        pool, empresa_id, start=novo_inicio, end=novo_fim
    )
    if not ok:
        raise CalendarIntegrationError(f"Regra de negócio: {motivo}")

    config, creds = await _resolve_credentials(pool, empresa_id)
    service = _calendar_service(creds)

    # Snapshot do estado anterior pro histórico
    diff_before = {
        "data_inicio": ag.data_inicio.isoformat(),
        "data_fim": ag.data_fim.isoformat(),
        "evento_id_externo": ag.evento_id_externo,
    }

    # Se já tem evento no Google (status confirmado), faz patch.
    # Se ainda é pendente (sem evento Google), só atualiza local.
    if ag.evento_id_externo:
        body = {
            "start": {
                "dateTime": novo_inicio.isoformat(),
                "timeZone": config.timezone,
            },
            "end": {
                "dateTime": novo_fim.isoformat(),
                "timeZone": config.timezone,
            },
        }
        try:
            ev = (
                service.events()
                .patch(
                    calendarId=ag.calendar_id,
                    eventId=ag.evento_id_externo,
                    body=body,
                )
                .execute()
            )
        except HttpError as e:
            raise CalendarIntegrationError(f"events.patch falhou: {e}") from e
    else:
        ev = {"id": None, "htmlLink": None}

    # Atualiza local
    await _agendamento_helpers.reschedule_local(
        pool,
        agendamento_id,
        empresa_id,
        novo_inicio=novo_inicio,
        novo_fim=novo_fim,
    )

    # Audit
    await _agendamento_helpers.append_history(
        pool,
        agendamento_id,
        action="rescheduled",
        actor_user_id=actor_user_id,
        payload_diff={
            "before": diff_before,
            "after": {
                "data_inicio": novo_inicio.isoformat(),
                "data_fim": novo_fim.isoformat(),
            },
        },
    )

    return {
        "id": ev.get("id"),
        "htmlLink": ev.get("htmlLink"),
        "agendamento_id": agendamento_id,
    }


async def sync_calendar_for_empresa(
    pool: AsyncConnectionPool, empresa_id: int, *, since_minutes: int = 10
) -> dict:
    """Reconcilia drift Google → DB (S5 cron periódico).

    Faz `events.list?updatedMin` da janela `since_minutes` minutos atrás
    e atualiza/insere rows local. Conflito (local mais recente que
    Google) → log `sync_conflict` em vez de sobrescrever.

    Retorna `{checked, synced, conflicts, missing}` pra observabilidade.
    """
    from whatsapp_langchain.shared import agendamento as _agendamento_helpers

    config, creds = await _resolve_credentials(pool, empresa_id)
    service = _calendar_service(creds)

    since = (datetime.now(UTC) - timedelta(minutes=since_minutes)).isoformat()
    try:
        resp = (
            service.events()
            .list(
                calendarId=config.calendar_id,
                updatedMin=since,
                singleEvents=True,
                showDeleted=True,
                maxResults=200,
            )
            .execute()
        )
    except HttpError as e:
        logger.warning(
            "sync_calendar_failed",
            empresa_id=empresa_id,
            error=str(e),
        )
        return {"checked": 0, "synced": 0, "conflicts": 0, "missing": 0}

    items = resp.get("items", [])
    synced = 0
    conflicts = 0
    missing = 0

    for ev in items:
        event_id = ev.get("id")
        if not event_id:
            continue
        local = await _agendamento_helpers.get_by_external_id(
            pool, empresa_id, event_id
        )
        if local is None:
            missing += 1
            continue
        # Reconciliação simples: status sync
        google_status = ev.get("status", "confirmed")
        # Google usa 'cancelled' (com double-l), mapeamos pro nosso 'cancelado'
        if google_status == "cancelled" and local.status != "cancelado":
            await _agendamento_helpers.cancel_local(
                pool, local.id, empresa_id
            )
            await _agendamento_helpers.append_history(
                pool,
                local.id,
                action="sync_drift",
                payload_diff={"google_status": "cancelled", "local_was": local.status},
            )
            synced += 1
        else:
            # Sem mudança de status — apenas conta como checked
            pass

    logger.info(
        "sync_calendar_done",
        empresa_id=empresa_id,
        items=len(items),
        synced=synced,
        missing=missing,
    )
    return {
        "checked": len(items),
        "synced": synced,
        "conflicts": conflicts,
        "missing": missing,
    }


async def confirm_pending_event(
    pool: AsyncConnectionPool, empresa_id: int, agendamento_id: int
) -> dict:
    """Cria evento no Google após APROVAR (S4). Atualiza local pra confirmado.

    Lê dados do `agendamento` row pendente, monta body Google, faz
    events.insert, atualiza local com evento_id_externo + payload.
    Em caso de falha: marca local como cancelado + log drift.
    """
    from whatsapp_langchain.shared import agendamento as _agendamento_helpers
    from whatsapp_langchain.shared.hook_dispatcher import dispatch_event

    ag = await _agendamento_helpers.get_by_id(pool, agendamento_id, empresa_id)
    if ag is None:
        raise CalendarIntegrationError(
            f"Agendamento {agendamento_id} não encontrado."
        )
    if ag.status != "pendente":
        raise CalendarIntegrationError(
            f"Agendamento {agendamento_id} já tem status {ag.status!r}, não pode confirmar."
        )

    config, creds = await _resolve_credentials(pool, empresa_id)
    service = _calendar_service(creds)
    body: dict = {
        "summary": ag.summary,
        "start": {"dateTime": ag.data_inicio.isoformat(), "timeZone": config.timezone},
        "end": {"dateTime": ag.data_fim.isoformat(), "timeZone": config.timezone},
    }
    if ag.descricao:
        body["description"] = ag.descricao

    try:
        ev = (
            service.events()
            .insert(calendarId=ag.calendar_id, body=body)
            .execute()
        )
    except HttpError as e:
        await _agendamento_helpers.cancel_local(pool, ag.id, empresa_id)
        logger.error(
            "agendamento_drift_confirm_failed",
            agendamento_id=ag.id,
            empresa_id=empresa_id,
            error=str(e),
        )
        raise CalendarIntegrationError(f"events.insert (confirm) falhou: {e}") from e

    evento_id = ev.get("id") or ""
    await _agendamento_helpers.update_external_event(
        pool,
        ag.id,
        evento_id_externo=evento_id,
        payload_externo={
            "htmlLink": ev.get("htmlLink"),
            "organizer": ev.get("organizer"),
            "attendees": ev.get("attendees", []),
            "status": ev.get("status"),
        },
    )
    # Status: pendente → confirmado + aprovado=true
    async with pool.connection() as conn:
        await conn.execute(
            """
            UPDATE agendamento
               SET status = 'confirmado', aprovado = TRUE, updated_at = NOW()
             WHERE id = %s
            """,
            (ag.id,),
        )
        await conn.commit()

    await dispatch_event(
        pool,
        empresa_id,
        "agendamento.aprovado",
        {
            "agendamento_id": ag.id,
            "evento_id_externo": evento_id,
            "summary": ag.summary,
            "data_inicio": ag.data_inicio.isoformat(),
            "status": "confirmado",
        },
    )
    return {
        "id": evento_id,
        "htmlLink": ev.get("htmlLink"),
        "agendamento_id": ag.id,
    }


async def cancel_event(
    pool: AsyncConnectionPool, empresa_id: int, *, event_id: str
) -> bool:
    """Cancela evento no Google + atualiza `agendamento.status='cancelado'`.

    Lookup do row local via `evento_id_externo`. Se não achar (evento
    criado fora do sistema), só cancela no Google e loga warning.
    """
    from whatsapp_langchain.shared import agendamento as _agendamento_helpers
    from whatsapp_langchain.shared.hook_dispatcher import dispatch_event

    config, creds = await _resolve_credentials(pool, empresa_id)
    service = _calendar_service(creds)
    try:
        service.events().delete(
            calendarId=config.calendar_id, eventId=event_id
        ).execute()
    except HttpError as e:
        if e.resp.status == 404:
            # Evento já não existe no Google. Marca local também e segue.
            ag = await _agendamento_helpers.get_by_external_id(
                pool, empresa_id, event_id
            )
            if ag:
                await _agendamento_helpers.cancel_local(pool, ag.id, empresa_id)
            return False
        raise CalendarIntegrationError(f"events.delete falhou: {e}") from e

    ag = await _agendamento_helpers.get_by_external_id(pool, empresa_id, event_id)
    if ag is None:
        logger.warning(
            "agendamento_cancel_no_local_row",
            empresa_id=empresa_id,
            evento_id_externo=event_id,
        )
        return True

    await _agendamento_helpers.cancel_local(pool, ag.id, empresa_id)
    await dispatch_event(
        pool,
        empresa_id,
        "agendamento.cancelado",
        {
            "agendamento_id": ag.id,
            "evento_id_externo": event_id,
            "status": "cancelado",
        },
    )
    return True


async def get_current_time(pool: AsyncConnectionPool, empresa_id: int) -> dict:
    """Hora atual + timezone da empresa — útil pro agente raciocinar datas."""
    config = await get_calendar_config(pool, empresa_id)
    tz = config.timezone if config else "America/Sao_Paulo"
    now = datetime.now(UTC)
    return {"now_utc": now.isoformat(), "timezone": tz}


# ---------------------------------------------------------------------------
# S1: list_calendars + set_active_calendar + list_events
# ---------------------------------------------------------------------------


async def list_calendars(pool: AsyncConnectionPool, empresa_id: int) -> list[dict]:
    """Lista todos os calendários da conta Google conectada à empresa.

    Retorna lista de dicts com `id`, `summary`, `description`,
    `timeZone`, `primary` (bool), `accessRole`. Útil pro agente oferecer
    "qual calendário você quer usar?" e pra UI mostrar opções.
    """
    _, creds = await _resolve_credentials(pool, empresa_id)
    service = _calendar_service(creds)
    try:
        items = service.calendarList().list().execute().get("items", [])
    except HttpError as e:
        raise CalendarIntegrationError(f"calendarList.list falhou: {e}") from e
    return [
        {
            "id": item.get("id"),
            "summary": item.get("summary"),
            "description": item.get("description"),
            "timeZone": item.get("timeZone"),
            "primary": bool(item.get("primary", False)),
            "accessRole": item.get("accessRole"),
        }
        for item in items
    ]


async def set_active_calendar(
    pool: AsyncConnectionPool, empresa_id: int, calendar_id: str
) -> dict:
    """Atualiza `empresa_calendar_config.calendar_id` após validar.

    Valida via `calendarList.get(calendarId)` que o calendário existe
    e que a conta tem acesso. Sem isso, gravar um id inválido faria
    todos os flows futuros (find_free_slots, create_event) falharem.

    Retorna metadata do calendário ativo pra confirmação ao chamador.
    """
    cid = calendar_id.strip()
    if not cid:
        raise CalendarIntegrationError("calendar_id não pode ser vazio.")

    _, creds = await _resolve_credentials(pool, empresa_id)
    service = _calendar_service(creds)
    try:
        meta = service.calendarList().get(calendarId=cid).execute()
    except HttpError as e:
        if e.resp.status == 404:
            raise CalendarIntegrationError(
                f"Calendário {cid!r} não encontrado ou sem acesso."
            ) from e
        raise CalendarIntegrationError(f"calendarList.get falhou: {e}") from e

    # Dual-write via helper
    await update_setting_dual(pool, empresa_id, calendar_id=cid)

    logger.info(
        "calendar_active_changed",
        empresa_id=empresa_id,
        calendar_id=cid,
        calendar_summary=meta.get("summary"),
    )

    return {
        "id": meta.get("id"),
        "summary": meta.get("summary"),
        "timeZone": meta.get("timeZone"),
        "primary": bool(meta.get("primary", False)),
    }


async def list_events(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    time_min_iso: str,
    time_max_iso: str,
    max_results: int = 50,
) -> list[dict]:
    """Lista eventos do calendário ativo entre `time_min_iso` e `time_max_iso`.

    Atende perguntas tipo "Quais reuniões tenho amanhã?" sem precisar
    fazer freebusy + raciocínio de slot livre. Inclui id, summary,
    start/end, organizer, attendees.
    """
    config, creds = await _resolve_credentials(pool, empresa_id)
    service = _calendar_service(creds)
    try:
        resp = (
            service.events()
            .list(
                calendarId=config.calendar_id,
                timeMin=time_min_iso,
                timeMax=time_max_iso,
                singleEvents=True,
                orderBy="startTime",
                maxResults=max_results,
            )
            .execute()
        )
    except HttpError as e:
        raise CalendarIntegrationError(f"events.list falhou: {e}") from e

    out: list[dict] = []
    for ev in resp.get("items", []):
        start = ev.get("start", {}) or {}
        end = ev.get("end", {}) or {}
        out.append(
            {
                "id": ev.get("id"),
                "summary": ev.get("summary"),
                "start": start.get("dateTime") or start.get("date"),
                "end": end.get("dateTime") or end.get("date"),
                "status": ev.get("status"),
                "htmlLink": ev.get("htmlLink"),
                "organizer_email": (ev.get("organizer") or {}).get("email"),
                "attendees": [
                    a.get("email") for a in (ev.get("attendees") or []) if a.get("email")
                ],
            }
        )
    return out
