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
    monkeypatch.setattr(settings, "wareline_encryption_key", SecretStr(key))


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


def test_decrypt_falha_sem_key(monkeypatch):
    monkeypatch.setattr(settings, "wareline_encryption_key", None)
    with pytest.raises(IntegracaoConfigError):
        encrypt_dict({"x": "y"})


def test_decrypt_cipher_corrompido_levanta():
    with pytest.raises(IntegracaoConfigError):
        decrypt_dict("notavalidciphertext")
