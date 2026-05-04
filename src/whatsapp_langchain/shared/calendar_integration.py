"""Google Calendar — OAuth flow + helpers de leitura/escrita (M5.a).

Cada empresa tem 1 row em `empresa_calendar_config`. O fluxo é:

1. Admin clica "Conectar Google Calendar" no painel.
2. Frontend redireciona pro endpoint `/api/google-calendar/oauth/init`,
   que devolve a URL de autorização do Google.
3. User autoriza no Google e é redirecionado pra
   `/api/google-calendar/oauth/callback?code=...`.
4. Trocamos o `code` por `Credentials` (token + refresh_token), persistimos
   o JSON em `empresa_calendar_config.oauth_credentials_json`.
5. Tools do agente carregam o JSON, montam `Credentials`, fazem refresh
   on-demand quando o `access_token` expira, e chamam Calendar API.

Multi-tenant: cada empresa pode ter sua própria conta Google. Quando a
empresa não tem config (ou `ativo=false`), as tools não são injetadas
no agente — o agente nem sabe que existe agendamento disponível.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from psycopg_pool import AsyncConnectionPool

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
    """Cria/atualiza a config (1 row por empresa). Reativa se estava `ativo=false`."""
    payload = json.dumps(credentials_to_json(creds))
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            INSERT INTO empresa_calendar_config
                (empresa_id, oauth_credentials_json, google_email,
                 created_by_user_id, ativo)
            VALUES (%s, %s::jsonb, %s, %s, TRUE)
            ON CONFLICT (empresa_id) DO UPDATE SET
                oauth_credentials_json = EXCLUDED.oauth_credentials_json,
                google_email = EXCLUDED.google_email,
                ativo = TRUE,
                updated_at = NOW()
            RETURNING empresa_id, oauth_credentials_json, google_email,
                      calendar_id, timezone, ativo, created_by_user_id,
                      created_at, updated_at
            """,
            (empresa_id, payload, google_email, user_id),
        )
        row = await cur.fetchone()
    assert row is not None
    return EmpresaCalendarConfig(
        empresa_id=row[0],
        oauth_credentials_json=row[1],
        google_email=row[2],
        calendar_id=row[3],
        timezone=row[4],
        ativo=row[5],
        created_by_user_id=row[6],
        created_at=row[7],
        updated_at=row[8],
    )


async def get_calendar_config(
    pool: AsyncConnectionPool, empresa_id: int
) -> EmpresaCalendarConfig | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT empresa_id, oauth_credentials_json, google_email,
                   calendar_id, timezone, ativo, created_by_user_id,
                   created_at, updated_at
              FROM empresa_calendar_config
             WHERE empresa_id = %s
            """,
            (empresa_id,),
        )
        row = await cur.fetchone()
    if not row:
        return None
    return EmpresaCalendarConfig(
        empresa_id=row[0],
        oauth_credentials_json=row[1],
        google_email=row[2],
        calendar_id=row[3],
        timezone=row[4],
        ativo=row[5],
        created_by_user_id=row[6],
        created_at=row[7],
        updated_at=row[8],
    )


def to_public(config: EmpresaCalendarConfig) -> CalendarConfigPublic:
    """Versão sem token bruto pra UI."""
    return CalendarConfigPublic(
        empresa_id=config.empresa_id,
        google_email=config.google_email,
        calendar_id=config.calendar_id,
        timezone=config.timezone,
        ativo=config.ativo,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


async def disconnect_calendar(pool: AsyncConnectionPool, empresa_id: int) -> bool:
    """Remove a config (não só inativa) — força nova autorização."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            "DELETE FROM empresa_calendar_config WHERE empresa_id = %s",
            (empresa_id,),
        )
    return (cur.rowcount or 0) > 0


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
        # persiste o token novo (refresh atualiza `token` + `expiry`)
        new_payload = json.dumps(credentials_to_json(creds))
        async with pool.connection() as conn:
            await conn.execute(
                """
                UPDATE empresa_calendar_config
                   SET oauth_credentials_json = %s::jsonb, updated_at = NOW()
                 WHERE empresa_id = %s
                """,
                (new_payload, empresa_id),
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
    work_start_hour: int = 9,
    work_end_hour: int = 18,
    max_slots: int = 6,
) -> list[dict]:
    """Calcula horários livres na agenda da empresa.

    Algoritmo: pega busy_intervals do Calendar API (`freebusy.query`)
    pros próximos `days_ahead` dias dentro da janela de trabalho, depois
    fatia em slots de `slot_minutes` minutos pulando os ocupados.

    Retorna lista de dicts `{start, end}` em ISO 8601 timezone-aware.
    """
    config, creds = await _resolve_credentials(pool, empresa_id)
    service = _calendar_service(creds)

    now = datetime.now(UTC)
    horizon = now + timedelta(days=days_ahead)
    body = {
        "timeMin": now.isoformat(),
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

    # Itera dia por dia dentro da janela de trabalho.
    slots: list[dict] = []
    cursor_day = now.date()
    end_day = horizon.date()
    while cursor_day <= end_day and len(slots) < max_slots:
        day_start = datetime.combine(
            cursor_day, datetime.min.time(), tzinfo=UTC
        ).replace(hour=work_start_hour)
        day_end = day_start.replace(hour=work_end_hour)
        # Pula horários no passado.
        slot_cursor = max(day_start, now)
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
                        "start": slot_cursor.isoformat(),
                        "end": slot_end.isoformat(),
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
) -> dict:
    """Cria evento no calendar default da empresa. Retorna {id, htmlLink}."""
    config, creds = await _resolve_credentials(pool, empresa_id)
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
        ev = service.events().insert(calendarId=config.calendar_id, body=body).execute()
    except HttpError as e:
        raise CalendarIntegrationError(f"events.insert falhou: {e}") from e
    return {"id": ev.get("id"), "htmlLink": ev.get("htmlLink")}


async def cancel_event(
    pool: AsyncConnectionPool, empresa_id: int, *, event_id: str
) -> bool:
    config, creds = await _resolve_credentials(pool, empresa_id)
    service = _calendar_service(creds)
    try:
        service.events().delete(
            calendarId=config.calendar_id, eventId=event_id
        ).execute()
    except HttpError as e:
        if e.resp.status == 404:
            return False
        raise CalendarIntegrationError(f"events.delete falhou: {e}") from e
    return True


async def get_current_time(pool: AsyncConnectionPool, empresa_id: int) -> dict:
    """Hora atual + timezone da empresa — útil pro agente raciocinar datas."""
    config = await get_calendar_config(pool, empresa_id)
    tz = config.timezone if config else "America/Sao_Paulo"
    now = datetime.now(UTC)
    return {"now_utc": now.isoformat(), "timezone": tz}
