"""Tests da cifragem/decifragem de credentials_encrypted (Fernet round-trip)."""

import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr

from whatsapp_langchain.integrations.crypto import (
    IntegracaoConfigError,
    decrypt_dict,
    encrypt_dict,
)
from whatsapp_langchain.shared.config import settings


@pytest.fixture(autouse=True)
def _patch_fernet(monkeypatch):
    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "integracoes_encryption_key", SecretStr(key))


def test_roundtrip_waba_credentials():
    payload = {
        "access_token": "EAAEXAMPLEverylongtoken",
        "waba_account_id": "12345",
        "phone_id": "67890",
    }
    cipher = encrypt_dict(payload)
    assert "EAAEXAMPLE" not in cipher  # access_token não em plaintext
    assert cipher.startswith("gAAAAA")  # Fernet ciphertext prefix
    restored = decrypt_dict(cipher)
    assert restored == payload


def test_roundtrip_evolution_credentials():
    payload = {
        "instance_name": "empresa1_test",
        "api_key": "abc-def-ghi",
        "api_url": "https://evo.example.com",
    }
    cipher = encrypt_dict(payload)
    assert "abc-def-ghi" not in cipher
    restored = decrypt_dict(cipher)
    assert restored == payload


def test_decrypt_falha_sem_nenhuma_key(monkeypatch):
    # Sem WARELINE_ENCRYPTION_KEY E sem INTERNAL_SERVICE_TOKEN → erro claro.
    monkeypatch.setattr(settings, "integracoes_encryption_key", None)
    monkeypatch.setattr(settings, "internal_service_token", "")
    with pytest.raises(IntegracaoConfigError):
        encrypt_dict({"x": "y"})


def test_deriva_key_do_internal_service_token(monkeypatch):
    # Sem WARELINE_ENCRYPTION_KEY mas COM INTERNAL_SERVICE_TOKEN → deriva a key
    # e o round-trip funciona (não exige env nova).
    monkeypatch.setattr(settings, "integracoes_encryption_key", None)
    monkeypatch.setattr(
        settings, "internal_service_token", "dev-token-change-in-production"
    )
    payload = {"instance_name": "empresa1_x", "api_key": "k", "api_url": "u"}
    restored = decrypt_dict(encrypt_dict(payload))
    assert restored == payload


def test_derivacao_deterministica(monkeypatch):
    # Mesmo token → mesma key (decifra entre "restarts").
    monkeypatch.setattr(settings, "integracoes_encryption_key", None)
    monkeypatch.setattr(settings, "internal_service_token", "tok-estavel-123456")
    cipher = encrypt_dict({"a": "b"})
    monkeypatch.setattr(settings, "internal_service_token", "tok-estavel-123456")
    assert decrypt_dict(cipher) == {"a": "b"}


def test_decrypt_cipher_corrompido_levanta():
    with pytest.raises(IntegracaoConfigError):
        decrypt_dict("notavalidciphertext")
