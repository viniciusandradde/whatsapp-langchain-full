"""Cripto Fernet compartilhada entre providers (Sprint Conector API).

Nasceu como refator de `wareline/credentials.py` — extrai encrypt/decrypt e
adiciona helpers pra dicts (JSON) usados pelo storage genérico
`api_connection.credentials_encrypted`. O Wareline saiu do produto, mas este
módulo ficou: é o que cifra as credenciais do Google Calendar e das demais
integrações.

A env continua se chamando `WARELINE_ENCRYPTION_KEY` **de propósito**. Ela é a
chave que decifra o que já está gravado; renomear tornaria ilegível todo
`credentials_encrypted` existente em produção. O nome é histórico, o uso não.
"""

from __future__ import annotations

import base64
import hashlib
import json

from cryptography.fernet import Fernet, InvalidToken

from whatsapp_langchain.shared.config import settings


class IntegracaoConfigError(Exception):
    """Configuração de integração ausente ou inválida.

    Era `WarelineConfigError`, de quem herdava; virou classe própria quando o
    Wareline saiu.
    """


def _derive_fernet_key(secret: str) -> bytes:
    """Deriva uma Fernet key válida (32 bytes url-safe base64) de um segredo
    qualquer via SHA-256. Determinística → mesma key entre restarts."""
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())


def _get_fernet() -> Fernet:
    """Lazy. Usa WARELINE_ENCRYPTION_KEY se setada; senão DERIVA a key de um
    segredo já presente (INTERNAL_SERVICE_TOKEN) — evita exigir uma env nova só
    pra isso e mantém as credenciais cifradas. A derivação é determinística;
    se o INTERNAL_SERVICE_TOKEN mudar, ciphertext antigo não decifra (mesma
    propriedade de "não perca a chave" da env explícita)."""
    key = settings.wareline_encryption_key
    if key is not None:
        raw = key.get_secret_value() if hasattr(key, "get_secret_value") else str(key)
        return Fernet(raw.encode() if isinstance(raw, str) else raw)
    fallback = (settings.internal_service_token or "").strip()
    if fallback:
        return Fernet(_derive_fernet_key(fallback))
    raise IntegracaoConfigError(
        "WARELINE_ENCRYPTION_KEY não configurada e sem INTERNAL_SERVICE_TOKEN "
        "pra derivar. Setar INTERNAL_SERVICE_TOKEN (já obrigatório) resolve."
    )


def encrypt_str(plaintext: str) -> str:
    """Cifra string em Fernet ciphertext."""
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt_str(ciphertext: str) -> str:
    """Decifra. Lança IntegracaoConfigError se key trocou ou cipher corrompido."""
    try:
        return _get_fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise IntegracaoConfigError(
            "Credencial corrompida ou WARELINE_ENCRYPTION_KEY trocada — "
            "reconfigure a integração."
        ) from exc


def encrypt_dict(data: dict) -> str:
    """dict → JSON → Fernet. Pra `api_connection.credentials_encrypted`."""
    return encrypt_str(json.dumps(data, ensure_ascii=False, sort_keys=True))


def decrypt_dict(ciphertext: str) -> dict:
    """Reverso: Fernet → JSON → dict."""
    raw = decrypt_str(ciphertext)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise IntegracaoConfigError(
            "Credenciais decifradas não são JSON válido."
        ) from exc
    if not isinstance(data, dict):
        raise IntegracaoConfigError(
            f"Credenciais devem ser dict, recebi {type(data).__name__}"
        )
    return data
