"""Tests da validação HMAC + parsing inbound do webhook WABA."""

import hashlib
import hmac

from whatsapp_langchain.integrations.waba.webhook import (
    parse_inbound,
    parse_template_status_updates,
    verify_signature,
)


def _sign(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_verify_signature_ok():
    body = b'{"object":"whatsapp_business_account"}'
    secret = "test-secret"
    sig = _sign(body, secret)
    assert verify_signature(body, sig, secret) is True


def test_verify_signature_mismatch():
    body = b'{"a":1}'
    sig = _sign(body, "wrong-secret")
    assert verify_signature(body, sig, "right-secret") is False


def test_verify_signature_missing():
    assert verify_signature(b"x", "", "secret") is False
    assert verify_signature(b"x", "sha256=abc", "") is False


def test_verify_signature_bad_format():
    assert verify_signature(b"x", "md5=abc", "secret") is False


def test_parse_inbound_text():
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {
                                "phone_number_id": "PHONE1",
                                "display_phone_number": "+55 11 99999",
                            },
                            "messages": [
                                {
                                    "id": "wamid.ABC",
                                    "from": "5511988887777",
                                    "timestamp": "1700000000",
                                    "type": "text",
                                    "text": {"body": "olá mundo"},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }
    msgs = parse_inbound(payload)
    assert len(msgs) == 1
    assert msgs[0].waba_phone_id == "PHONE1"
    assert msgs[0].from_number == "+5511988887777"
    assert msgs[0].type == "text"
    assert msgs[0].text == "olá mundo"


def test_parse_inbound_image_extrai_media_id():
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"phone_number_id": "P"},
                            "messages": [
                                {
                                    "id": "wamid.IMG",
                                    "from": "5511",
                                    "timestamp": "1700",
                                    "type": "image",
                                    "image": {
                                        "id": "media-xyz",
                                        "mime_type": "image/jpeg",
                                        "caption": "olha",
                                    },
                                }
                            ],
                        },
                    }
                ]
            }
        ],
    }
    msgs = parse_inbound(payload)
    assert len(msgs) == 1
    assert msgs[0].type == "image"
    assert msgs[0].media_id == "media-xyz"
    assert msgs[0].media_mime_type == "image/jpeg"
    assert msgs[0].media_caption == "olha"


def test_parse_inbound_interactive_button_reply_vira_text():
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"phone_number_id": "P"},
                            "messages": [
                                {
                                    "id": "wamid.BTN",
                                    "from": "55",
                                    "timestamp": "1700",
                                    "type": "interactive",
                                    "interactive": {
                                        "type": "button_reply",
                                        "button_reply": {
                                            "id": "yes",
                                            "title": "Sim",
                                        },
                                    },
                                }
                            ],
                        },
                    }
                ]
            }
        ],
    }
    msgs = parse_inbound(payload)
    assert msgs[0].text == "Sim"


def test_parse_inbound_ignora_payload_diferente():
    msgs = parse_inbound({"object": "page"})
    assert msgs == []


def test_waba_post_rejects_missing_signature_outside_production(monkeypatch):
    """R18: com META_APP_SECRET configurado, assinatura AUSENTE é rejeitada
    mesmo fora de produção.

    Antes só rejeitava quando is_production — staging / env com
    ENVIRONMENT != 'production' aceitava webhook WABA forjado sem HMAC.
    """
    from fastapi.testclient import TestClient
    from pydantic import SecretStr

    from whatsapp_langchain.server.main import app
    from whatsapp_langchain.shared.config import settings

    monkeypatch.setattr(settings, "meta_app_secret", SecretStr("test-secret"))
    monkeypatch.setattr(settings, "environment", "development")

    resp = TestClient(app).post(
        "/webhook/waba", json={"object": "whatsapp_business_account"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "rejected_no_signature"}


def test_parse_template_status_updates_extrai_evento():
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "WABA1",
                "changes": [
                    {
                        "field": "message_template_status_update",
                        "value": {
                            "message_template_id": 12345,
                            "message_template_name": "boas_vindas",
                            "message_template_language": "pt_BR",
                            "event": "APPROVED",
                        },
                    }
                ],
            }
        ],
    }
    updates = parse_template_status_updates(payload)
    assert len(updates) == 1
    assert updates[0]["meta_template_id"] == "12345"
    assert updates[0]["event"] == "APPROVED"


def test_waba_post_rejeita_quando_nao_ha_secret(monkeypatch):
    """Sem META_APP_SECRET o webhook NÃO processa nada (fail-closed).

    A versão anterior validava assinatura dentro de `if app_secret:` — com a env
    vazia, que é o estado de qualquer instalação que ainda não ligou o WABA, o
    endpoint aceitava payload forjado sem assinatura nenhuma. Confirmado contra
    produção antes da correção: `POST /webhook/waba` devolvia `received`.
    """
    from fastapi.testclient import TestClient

    from whatsapp_langchain.server.main import app
    from whatsapp_langchain.shared.config import settings

    monkeypatch.setattr(settings, "meta_app_secret", None)

    resp = TestClient(app).post(
        "/webhook/waba", json={"object": "whatsapp_business_account"}
    )
    assert resp.status_code == 200
    assert resp.json() == {"status": "rejected_no_secret"}


def test_handshake_devolve_challenge_em_texto_puro(monkeypatch):
    """A Meta espera o challenge cru; JSON não fecha a verificação.

    O código antigo fazia `int(challenge)` e caía num `{"challenge": ...}`
    quando o valor não era numérico — passava enquanto a Meta mandasse dígitos.
    """
    from fastapi.testclient import TestClient
    from pydantic import SecretStr

    from whatsapp_langchain.server.main import app
    from whatsapp_langchain.shared.config import settings

    monkeypatch.setattr(
        settings, "waba_webhook_verify_token", SecretStr("token-de-teste")
    )
    client = TestClient(app)

    resp = client.get(
        "/webhook/waba",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "token-de-teste",
            "hub.challenge": "abc123XYZ",
        },
    )
    assert resp.status_code == 200
    assert resp.text == "abc123XYZ"
    assert resp.headers["content-type"].startswith("text/plain")

    # o caso numérico, que era o único que funcionava antes, segue igual
    resp = client.get(
        "/webhook/waba",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "token-de-teste",
            "hub.challenge": "1234567890",
        },
    )
    assert resp.text == "1234567890"


def test_handshake_recusa_token_errado(monkeypatch):
    from fastapi.testclient import TestClient
    from pydantic import SecretStr

    from whatsapp_langchain.server.main import app
    from whatsapp_langchain.shared.config import settings

    monkeypatch.setattr(settings, "waba_webhook_verify_token", SecretStr("certo"))
    resp = TestClient(app).get(
        "/webhook/waba",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "errado",
            "hub.challenge": "123",
        },
    )
    assert resp.status_code == 403
