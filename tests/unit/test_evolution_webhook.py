"""Testes do webhook inbound da Evolution API (M2.b P4).

Cobre:
- happy path: messages.upsert válido enfileira mensagem
- fromMe=true ignorado (não enfileira)
- evento ≠ messages.upsert respondido 200 silently
- instance desconhecida → 200 silent (evita retry da Evolution)
- apikey inválida → 401 quando EVOLUTION_VALIDATE_APIKEY=true
- text vazio (mídia/sticker no MVP) → 200 silent
- normalização de remoteJid (com/sem @s.whatsapp.net)
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from whatsapp_langchain.server.main import app
from whatsapp_langchain.shared.models import Atendimento, Cliente, Conexao

client = TestClient(app, raise_server_exceptions=False)


TEST_INSTANCE = "vsa-tecnologia"
TEST_API_KEY = "evo-test-apikey-12345"


def _conexao_evolution() -> Conexao:
    now = datetime.now(UTC)
    return Conexao(
        id=7,
        empresa_id=1,
        provider="evolution",
        sid=None,
        from_number="+5567984249725",
        display_name="VSA Evolution",
        default_agent_id="vsa_tech",
        status="active",
        is_default=False,
        payload_json={"instance_name": TEST_INSTANCE},
        created_at=now,
        updated_at=now,
    )


def _cliente() -> Cliente:
    now = datetime.now(UTC)
    return Cliente(
        id=11,
        empresa_id=1,
        telefone="+5511999999999",
        nome=None,
        created_at=now,
        updated_at=now,
    )


def _atendimento() -> Atendimento:
    now = datetime.now(UTC)
    return Atendimento(
        id=22,
        empresa_id=1,
        cliente_id=11,
        conexao_id=7,
        last_message_at=now,
        created_at=now,
        updated_at=now,
    )


def _payload(
    *,
    event: str = "messages.upsert",
    instance: str = TEST_INSTANCE,
    from_me: bool = False,
    remote_jid: str = "5511999999999@s.whatsapp.net",
    msg_id: str = "BAE5ABC123",
    conversation: str | None = "Olá!",
    extended_text: str | None = None,
    push_name: str | None = "João",
) -> dict:
    message: dict = {}
    if conversation is not None:
        message["conversation"] = conversation
    if extended_text is not None:
        message["extendedTextMessage"] = {"text": extended_text}
    return {
        "event": event,
        "instance": instance,
        "data": {
            "key": {
                "remoteJid": remote_jid,
                "fromMe": from_me,
                "id": msg_id,
            },
            "message": message,
            "pushName": push_name,
            "messageTimestamp": "1730000000",
        },
    }


@pytest.fixture(autouse=True)
def mock_db(monkeypatch):
    """Mock do banco + dependências externas (M2 + M3 + M4.d).

    NOTA: usa a referência `settings` do MÓDULO do webhook (não do
    config). Outros testes (`test_cors_config.py`) fazem
    `importlib.reload` em `shared.config`, o que cria um novo
    singleton — mas o webhook mantém a referência local antiga
    importada no boot. Patchar via módulo do webhook garante que o
    runtime enxerga as mudanças.
    """
    from whatsapp_langchain.server.routes import evolution_webhook as ew

    mock_pool = AsyncMock()
    monkeypatch.setattr(
        ew.settings, "internal_service_token", "test-internal-token"
    )
    # Default: validate OFF — testes específicos sobreescrevem.
    monkeypatch.setattr(ew.settings, "evolution_validate_apikey", False)
    monkeypatch.setattr(ew.settings, "evolution_api_key", SecretStr(TEST_API_KEY))

    enqueue_mock = AsyncMock(return_value=None)

    async def fake_lookup(_pool, instance: str):
        if instance == TEST_INSTANCE:
            return _conexao_evolution()
        return None

    with (
        patch(
            "whatsapp_langchain.server.routes.evolution_webhook.get_pool",
            return_value=mock_pool,
        ),
        patch(
            "whatsapp_langchain.server.routes.evolution_webhook"
            ".get_conexao_by_evolution_instance",
            side_effect=fake_lookup,
        ),
        patch(
            "whatsapp_langchain.server.routes.evolution_webhook.upsert_cliente",
            new=AsyncMock(return_value=_cliente()),
        ),
        patch(
            "whatsapp_langchain.server.routes.evolution_webhook"
            ".open_or_attach_atendimento",
            new=AsyncMock(return_value=(_atendimento(), True)),
        ),
        patch(
            "whatsapp_langchain.server.routes.evolution_webhook.enqueue_or_buffer",
            new=enqueue_mock,
        ),
        patch(
            "whatsapp_langchain.server.routes.evolution_webhook.dispatch_event",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "whatsapp_langchain.server.routes.evolution_webhook.check_rate_limit",
            new=AsyncMock(return_value=None),
        ),
        patch("whatsapp_langchain.shared.db.get_pool", return_value=mock_pool),
    ):
        yield enqueue_mock


# === Happy path ===


def test_messages_upsert_enqueues(mock_db):
    """Payload válido enfileira via enqueue_or_buffer com agent default."""
    response = client.post("/webhook/evolution", json=_payload())
    assert response.status_code == 200
    mock_db.assert_awaited_once()
    kwargs = mock_db.await_args.kwargs
    assert kwargs["phone_number"] == "+5511999999999"
    assert kwargs["agent_id"] == "vsa_tech"
    assert kwargs["body"] == "Olá!"
    assert kwargs["empresa_id"] == 1
    assert kwargs["conexao_id"] == 7


def test_extracts_text_from_extendedTextMessage(mock_db):
    """Texto pode vir em extendedTextMessage.text quando há link/preview."""
    payload = _payload(conversation=None, extended_text="Veja: https://exemplo.com")
    response = client.post("/webhook/evolution", json=payload)
    assert response.status_code == 200
    mock_db.assert_awaited_once()
    assert mock_db.await_args.kwargs["body"] == "Veja: https://exemplo.com"


def test_normalizes_remote_jid_without_suffix(mock_db):
    """remoteJid sem @suffix também é aceito (algumas variants Evolution)."""
    payload = _payload(remote_jid="5511999999999")
    response = client.post("/webhook/evolution", json=payload)
    assert response.status_code == 200
    assert mock_db.await_args.kwargs["phone_number"] == "+5511999999999"


# === Filtros silenciosos ===


def test_skips_fromMe_true(mock_db):
    """Mensagem enviada PELA própria instância não é enfileirada."""
    response = client.post("/webhook/evolution", json=_payload(from_me=True))
    assert response.status_code == 200
    mock_db.assert_not_awaited()


def test_ignores_other_events(mock_db):
    """Eventos como connection.update / chats.upsert respondem 200 silently."""
    response = client.post(
        "/webhook/evolution", json=_payload(event="connection.update")
    )
    assert response.status_code == 200
    mock_db.assert_not_awaited()


def test_accepts_uppercase_event_name(mock_db):
    """Evolution envia event como MESSAGES_UPSERT em algumas configs — normaliza."""
    response = client.post(
        "/webhook/evolution", json=_payload(event="MESSAGES_UPSERT")
    )
    assert response.status_code == 200
    mock_db.assert_awaited_once()


def test_unknown_instance_returns_200_silently(mock_db):
    """Instance não cadastrada → 200 silent (evita retry storm da Evolution)."""
    response = client.post(
        "/webhook/evolution",
        json=_payload(instance="instance-inexistente"),
    )
    assert response.status_code == 200
    mock_db.assert_not_awaited()


def test_unsupported_message_type_returns_200_silently(mock_db):
    """Mídia/áudio/sticker (sem campo text) → 200, não enfileira (MVP só texto)."""
    payload = _payload(conversation=None)
    payload["data"]["message"] = {"imageMessage": {"url": "https://..."}}
    response = client.post("/webhook/evolution", json=payload)
    assert response.status_code == 200
    mock_db.assert_not_awaited()


# === Validação ===


def test_missing_instance_returns_400(mock_db):
    """Payload sem `instance` é malformado — 400."""
    response = client.post(
        "/webhook/evolution",
        json=_payload(instance=""),
    )
    assert response.status_code == 400


def test_missing_remoteJid_returns_400(mock_db):
    """messages.upsert sem remoteJid não tem como identificar remetente — 400."""
    response = client.post(
        "/webhook/evolution",
        json=_payload(remote_jid=""),
    )
    assert response.status_code == 400


def test_apikey_validation_off_accepts_missing_header(mock_db):
    """Default `evolution_validate_apikey=False` aceita request sem header."""
    response = client.post("/webhook/evolution", json=_payload())
    assert response.status_code == 200


def test_apikey_validation_on_rejects_invalid(mock_db, monkeypatch):
    """Quando ON, header `apikey` errada → 401 antes de qualquer enqueue."""
    from whatsapp_langchain.server.routes import evolution_webhook as ew

    monkeypatch.setattr(ew.settings, "evolution_validate_apikey", True)
    response = client.post(
        "/webhook/evolution",
        json=_payload(),
        headers={"apikey": "wrong-key"},
    )
    assert response.status_code == 401
    mock_db.assert_not_awaited()


def test_apikey_validation_on_accepts_valid(mock_db, monkeypatch):
    """Header correto autoriza."""
    from whatsapp_langchain.server.routes import evolution_webhook as ew

    monkeypatch.setattr(ew.settings, "evolution_validate_apikey", True)
    response = client.post(
        "/webhook/evolution",
        json=_payload(),
        headers={"apikey": TEST_API_KEY},
    )
    assert response.status_code == 200
    mock_db.assert_awaited_once()
