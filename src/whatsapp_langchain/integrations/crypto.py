"""Cripto Fernet compartilhada entre providers (Sprint Conector API).

Refator de `wareline/credentials.py` — extrai encrypt/decrypt e adiciona
helpers pra dicts (JSON) usados pelo storage genérico
`api_connection.credentials_encrypted`.
"""

from __future__ import annotations

import json

from cryptography.fernet import Fernet, InvalidToken

from whatsapp_langchain.integrations.wareline.errors import (
    WarelineConfigError,
)
from whatsapp_langchain.shared.config import settings


class IntegracaoConfigError(WarelineConfigError):
    """Re-export pra novos providers (mesma semântica do Wareline)."""


def _get_fernet() -> Fernet:
    """Lazy + valida chave configurada. Compartilha mesma key do Wareline."""
    key = settings.wareline_encryption_key
    if key is None:
        raise IntegracaoConfigError(
            "WARELINE_ENCRYPTION_KEY não configurada. Gere com "
            "`python -c 'from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())'`"
        )
    raw = (
        key.get_secret_value() if hasattr(key, "get_secret_value") else str(key)
    )
    return Fernet(raw.encode() if isinstance(raw, str) else raw)


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
