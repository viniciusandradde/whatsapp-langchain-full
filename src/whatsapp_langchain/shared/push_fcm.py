"""Envio de push por FCM HTTP v1 (service account).

Mensagens SÓ de dados (`data`), nunca `notification`: quem monta a
notificação visível é o app, que usa `tag=atendimento_id` para colapsar
várias mensagens da mesma conversa num aviso só. Com `notification` o
sistema Android exibiria sozinho, uma por mensagem, sem colapso.

A credencial vem de `FIREBASE_SERVICE_ACCOUNT_JSON` (o JSON inteiro da
service account, numa linha, no env). Vazio = push desligado — o loop do
worker nem inicia, e nada além de um log de boot acontece.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import structlog

logger = structlog.get_logger()

_FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"

# Credencial e token OAuth ficam em módulo: o token vale ~1h e o google-auth
# sabe renovar sozinho (`credentials.valid` + `refresh`). Recriar a credencial
# a cada envio refaria o parse do JSON e uma ida ao OAuth por mensagem.
_credentials: Any = None
_project_id: str | None = None


class PushDesligadoError(Exception):
    """FIREBASE_SERVICE_ACCOUNT_JSON ausente ou inválido."""


def _carregar_credencial() -> tuple[Any, str]:
    global _credentials, _project_id
    if _credentials is not None and _project_id:
        return _credentials, _project_id

    from whatsapp_langchain.shared.config import settings

    raw = (settings.firebase_service_account_json or "").strip()
    if not raw:
        raise PushDesligadoError("FIREBASE_SERVICE_ACCOUNT_JSON não configurado")
    try:
        info = json.loads(raw)
        from google.oauth2 import service_account

        _credentials = service_account.Credentials.from_service_account_info(
            info, scopes=[_FCM_SCOPE]
        )
        _project_id = str(info["project_id"])
    except PushDesligadoError:
        raise
    except Exception as exc:
        # O conteúdo do env NUNCA vai pro log — é a chave privada.
        raise PushDesligadoError(
            f"FIREBASE_SERVICE_ACCOUNT_JSON inválido ({type(exc).__name__})"
        ) from exc
    return _credentials, _project_id


def push_configurado() -> bool:
    """True quando há credencial utilizável. Não faz rede."""
    try:
        _carregar_credencial()
        return True
    except PushDesligadoError:
        return False


def _access_token() -> str:
    creds, _ = _carregar_credencial()
    if not creds.valid:
        from google.auth.transport.requests import Request

        creds.refresh(Request())
    return str(creds.token)


async def enviar_push(token_fcm: str, data: dict[str, str]) -> str:
    """Envia um data-push para UM dispositivo.

    Retorna:
    - "ok" — aceito pelo FCM;
    - "token_invalido" — aparelho desinstalou/limpou; o chamador APAGA a linha;
    - "erro" — falha transitória (rede, 5xx); o chamador só loga.

    O refresh do OAuth é síncrono (google-auth), mas roda a cada ~1h e leva
    ~100ms — não vale um executor para isso no worker.
    """
    try:
        _, project = _carregar_credencial()
        bearer = _access_token()
    except PushDesligadoError as exc:
        logger.warning("push_desligado", motivo=str(exc))
        return "erro"

    corpo = {
        "message": {
            "token": token_fcm,
            "data": data,
            "android": {"priority": "HIGH"},
        }
    }
    try:
        async with httpx.AsyncClient(timeout=15) as cli:
            r = await cli.post(
                f"https://fcm.googleapis.com/v1/projects/{project}/messages:send",
                headers={"Authorization": f"Bearer {bearer}"},
                json=corpo,
            )
    except Exception as exc:
        logger.warning("push_falhou_rede", error=type(exc).__name__)
        return "erro"

    if r.status_code == 200:
        return "ok"
    # Permanentes → o chamador apaga a linha:
    # - 404 / UNREGISTERED: o aparelho desinstalou ou o token expirou;
    # - 400 INVALID_ARGUMENT sobre o token: registro malformado (visto no
    #   teste com a credencial real) — retentar daria o mesmo erro pra sempre.
    if r.status_code == 404 or "UNREGISTERED" in r.text:
        return "token_invalido"
    if r.status_code == 400 and "registration token" in r.text:
        return "token_invalido"
    logger.warning(
        "push_recusado",
        status=r.status_code,
        # Só o começo do corpo: erro do FCM não carrega segredo, mas também
        # não merece megabytes no log.
        body=r.text[:200],
    )
    return "erro"
