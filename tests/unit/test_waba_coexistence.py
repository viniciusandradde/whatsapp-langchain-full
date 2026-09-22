"""WhatsApp Coexistence (mig 200) — parsers, eco, histórico e rota do webhook.

Os payloads são os da doc da Meta "Onboard WhatsApp Business app users"
(Graph v25.0, conferida em 22/09/2026), copiados literalmente.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from whatsapp_langchain.integrations.waba.webhook import (
    ERRO_HISTORICO_RECUSADO,
    parse_account_updates,
    parse_history,
    parse_inbound,
    parse_message_echoes,
    parse_state_sync,
)

ECHO = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "102290129340398",
            "changes": [
                {
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "display_phone_number": "15550783881",
                            "phone_number_id": "106540352242922",
                        },
                        "message_echoes": [
                            {
                                "from": "15550783881",
                                "to": "16505551234",
                                "id": "wamid.HBgLMTY0NjcwNDM1OTUVAgARGBIyNDlBOEI5QUQ4NDc0N0FCNjMA",
                                "timestamp": "1700255121",
                                "type": "text",
                                "text": {
                                    "body": "Here's the info you requested! https://www.meta.com/quest/quest-3/"
                                },
                            }
                        ],
                    },
                    "field": "smb_message_echoes",
                }
            ],
        }
    ],
}

HISTORY = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "102290129340398",
            "changes": [
                {
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "display_phone_number": "15550783881",
                            "phone_number_id": "106540352242922",
                        },
                        "history": [
                            {
                                "metadata": {
                                    "phase": 0,
                                    "chunk_order": 1,
                                    "progress": 55,
                                },
                                "threads": [
                                    {
                                        "id": "16505551234",
                                        "messages": [
                                            {
                                                "from": "15550783881",
                                                "id": "wamid.HBgLMTY0NjcwNDM1OTUVAgARGBIyNDlBOEI5QUQ4NDc0N0FCNjMA",
                                                "timestamp": "1739230955",
                                                "type": "text",
                                                "text": {
                                                    "body": "Here's the info you requested! https://www.meta.com/quest/quest-3/"
                                                },
                                                "history_context": {"status": "READ"},
                                            }
                                        ],
                                    }
                                ],
                            }
                        ],
                    },
                    "field": "history",
                }
            ],
        }
    ],
}

# A doc mostra só o `value` do caso recusado; o envelope é o mesmo do aprovado.
HISTORY_RECUSADO_VALUE = {
    "messaging_product": "whatsapp",
    "metadata": {
        "display_phone_number": "15550783881",
        "phone_number_id": "106540352242922",
    },
    "history": [
        {
            "errors": [
                {
                    "code": 2593109,
                    "title": "History sync is turned off by the business from the WhatsApp Business App",
                    "message": "History sync is turned off by the business from the WhatsApp Business App",
                    "error_data": {
                        "details": "History sharing is turned off by the business"
                    },
                }
            ]
        }
    ],
}

STATE_SYNC = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "102290129340398",
            "changes": [
                {
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "display_phone_number": "15550783881",
                            "phone_number_id": "106540352242922",
                        },
                        "state_sync": [
                            {
                                "type": "contact",
                                "contact": {
                                    "full_name": "Pablo Morales",
                                    "first_name": "Pablo",
                                    "phone_number": "16505551234",
                                },
                                "action": "add",
                                "metadata": {"timestamp": "1738346006"},
                            }
                        ],
                    },
                    "field": "smb_app_state_sync",
                }
            ],
        }
    ],
}

ACCOUNT_UPDATE = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "102290129340398",
            "time": 1739212624,
            "changes": [
                {
                    "value": {
                        "phone_number": "15550783881",
                        "event": "PARTNER_REMOVED",
                        "disconnection_info": {
                            "reason": "PRIMARY_INACTIVITY",
                            "initiated_by": "SYSTEM",
                        },
                    },
                    "field": "account_update",
                }
            ],
        }
    ],
}

INBOUND = {
    "object": "whatsapp_business_account",
    "entry": [
        {
            "id": "102290129340398",
            "changes": [
                {
                    "field": "messages",
                    "value": {
                        "metadata": {
                            "phone_number_id": "106540352242922",
                            "display_phone_number": "15550783881",
                        },
                        "contacts": [
                            {"wa_id": "16505551234", "profile": {"name": "Pablo"}}
                        ],
                        "messages": [
                            {
                                "id": "wamid.CLIENTE1",
                                "from": "16505551234",
                                "timestamp": "1700000000",
                                "type": "text",
                                "text": {"body": "Olá"},
                            }
                        ],
                    },
                }
            ],
        }
    ],
}


# ---------- parsers ----------


def test_parse_echo_payload_da_meta():
    (eco,) = parse_message_echoes(ECHO)
    assert eco.waba_phone_id == "106540352242922"
    assert eco.to_number == "+16505551234"  # o CLIENTE, não a empresa
    assert eco.message_id.startswith("wamid.")
    assert eco.type == "text"
    assert eco.text and eco.text.startswith("Here's the info")


def test_echo_nao_e_mensagem_de_cliente():
    """O eco nunca pode cair no parser de inbound (senão a IA responderia)."""
    assert parse_inbound(ECHO) == []
    assert parse_message_echoes(INBOUND) == []


def test_parse_history_aprovado():
    (lote,) = parse_history(HISTORY)
    assert (lote.phase, lote.chunk_order, lote.progress) == (0, 1, 55)
    (conversa,) = lote.conversas
    assert conversa.cliente_number == "+16505551234"
    (msg,) = conversa.mensagens
    assert msg.da_empresa is True  # from == display_phone_number
    assert msg.text and msg.text.startswith("Here's the info")
    assert lote.erros == []


def test_parse_history_recusado():
    payload = json.loads(json.dumps(HISTORY))
    payload["entry"][0]["changes"][0]["value"] = HISTORY_RECUSADO_VALUE
    (lote,) = parse_history(payload)
    assert lote.erros == [ERRO_HISTORICO_RECUSADO]
    assert lote.conversas == []


def test_parse_state_sync_contato():
    (contato,) = parse_state_sync(STATE_SYNC)
    assert contato.phone_number == "+16505551234"
    assert contato.nome == "Pablo Morales"
    assert contato.action == "add"


def test_parse_account_update_partner_removed():
    (evento,) = parse_account_updates(ACCOUNT_UPDATE)
    assert evento.waba_account_id == "102290129340398"
    assert evento.event == "PARTNER_REMOVED"
    assert evento.phone_number == "+15550783881"
    assert evento.reason == "PRIMARY_INACTIVITY"


def test_parse_inbound_traz_nome_do_perfil():
    (msg,) = parse_inbound(INBOUND)
    assert msg.profile_name == "Pablo"


# ---------- texto do eco ----------


def _eco(tipo: str, texto: str | None):
    from whatsapp_langchain.integrations.waba.models import WabaEcho

    return WabaEcho(
        waba_phone_id="P",
        to_number="+5511",
        message_id="wamid.X",
        timestamp=datetime.now(UTC),
        type=tipo,
        text=texto,
    )


def test_texto_do_eco_midia_e_revoke():
    from whatsapp_langchain.shared.waba_coexistence import texto_do_eco

    assert texto_do_eco(_eco("text", "oi")) == "oi"
    assert texto_do_eco(_eco("image", "foto")) == (
        "foto\n[imagem enviado pelo celular]"
    )
    assert texto_do_eco(_eco("document", None)) == "[documento enviado pelo celular]"
    assert texto_do_eco(_eco("revoke", None)) is None
    assert texto_do_eco(_eco("edit", None)) is None


# ---------- registrar_eco: pausa a IA ----------


def _conexao(**kw):
    from whatsapp_langchain.shared.models import Conexao

    base = {
        "id": 7,
        "empresa_id": 3,
        "provider": "waba",
        "from_number": "+15550783881",
        "default_agent_id": "agente",
        "created_at": datetime.now(UTC),
        "updated_at": datetime.now(UTC),
        "waba_phone_id": "106540352242922",
        "waba_account_id": "102290129340398",
        "waba_mode": "coexistence",
        "connection_state": "open",
    }
    base.update(kw)
    return Conexao(**base)


def _atendimento(atd_id: int, dono: str | None):
    atd = MagicMock()
    atd.id = atd_id
    atd.assigned_to_user_id = dono
    return atd


@pytest.fixture
def coex(monkeypatch):
    from whatsapp_langchain.shared import waba_coexistence as mod

    cliente = MagicMock(id=11)
    m = {
        "upsert": AsyncMock(return_value=cliente),
        "open": AsyncMock(),
        "claim": AsyncMock(),
        "persist": AsyncMock(),
    }
    monkeypatch.setattr(mod, "upsert_cliente", m["upsert"])
    monkeypatch.setattr(mod, "open_or_attach_atendimento", m["open"])
    monkeypatch.setattr(mod, "claim_atendimento", m["claim"])
    monkeypatch.setattr(mod, "_persist_outbound_row", m["persist"])
    return mod, m


async def test_eco_em_conversa_com_ia_assume_pelo_celular(coex):
    mod, m = coex
    m["open"].return_value = (_atendimento(5, None), False)
    m["claim"].return_value = _atendimento(5, mod.HUMANO_APP)
    (eco,) = parse_message_echoes(ECHO)

    await mod.registrar_eco(MagicMock(), _conexao(), eco)

    m["claim"].assert_awaited_once()
    assert m["claim"].await_args.args[1:] == (5, mod.HUMANO_APP)
    kw = m["persist"].await_args.kwargs
    assert kw["origem_resposta"] == "whatsapp_business_app"
    assert kw["user_id"] == "app:whatsapp_business"  # → manual:app:…
    assert kw["provider_message_id"] == eco.message_id
    assert kw["phone_number"] == "+16505551234"


async def test_eco_nao_rouba_conversa_de_operador(coex):
    mod, m = coex
    m["open"].return_value = (_atendimento(5, "user-operador"), False)
    (eco,) = parse_message_echoes(ECHO)

    await mod.registrar_eco(MagicMock(), _conexao(), eco)

    m["claim"].assert_not_awaited()
    m["persist"].assert_awaited_once()


async def test_eco_abre_conversa_nova_ja_com_humano(coex):
    mod, m = coex
    m["open"].return_value = (_atendimento(9, mod.HUMANO_APP), True)
    (eco,) = parse_message_echoes(ECHO)

    await mod.registrar_eco(MagicMock(), _conexao(), eco)

    assert m["open"].await_args.kwargs["assigned_to_user_id"] == mod.HUMANO_APP
    assert m["open"].await_args.kwargs["iniciado_cliente"] is False
    m["claim"].assert_not_awaited()


async def test_eco_revoke_nao_grava(coex):
    mod, m = coex
    await mod.registrar_eco(MagicMock(), _conexao(), _eco("revoke", None))
    m["upsert"].assert_not_awaited()
    m["persist"].assert_not_awaited()


# ---------- account_update ----------


async def test_partner_removed_desconecta(monkeypatch):
    from whatsapp_langchain.shared import waba_coexistence as mod

    estado = AsyncMock()
    saude = AsyncMock()
    monkeypatch.setattr(
        mod, "list_conexoes_by_waba_account_id", AsyncMock(return_value=[_conexao()])
    )
    monkeypatch.setattr(mod, "set_connection_state", estado)
    monkeypatch.setattr(mod, "record_health_check", saude)

    (evento,) = parse_account_updates(ACCOUNT_UPDATE)
    assert await mod.processar_account_update(MagicMock(), evento) == 1
    assert estado.await_args.kwargs["state"] == "disconnected"
    mensagem = estado.await_args.kwargs["message"]
    assert "celular" in mensagem and "_" not in mensagem
    assert saude.await_args.kwargs["ok"] is False


async def test_account_update_de_outro_numero_nao_mexe(monkeypatch):
    from whatsapp_langchain.shared import waba_coexistence as mod

    estado = AsyncMock()
    monkeypatch.setattr(
        mod,
        "list_conexoes_by_waba_account_id",
        AsyncMock(return_value=[_conexao(from_number="+5567000000000")]),
    )
    monkeypatch.setattr(mod, "set_connection_state", estado)
    (evento,) = parse_account_updates(ACCOUNT_UPDATE)
    assert await mod.processar_account_update(MagicMock(), evento) == 0
    estado.assert_not_awaited()


# ---------- rota /webhook/waba ----------

SECRET = "segredo-de-teste"


def _post(payload: dict, *, assinatura: str | None = None):
    from whatsapp_langchain.server.main import app

    corpo = json.dumps(payload).encode()
    sig = (
        assinatura
        if assinatura is not None
        else "sha256=" + hmac.new(SECRET.encode(), corpo, hashlib.sha256).hexdigest()
    )
    return TestClient(app).post(
        "/webhook/waba",
        content=corpo,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": sig},
    )


@pytest.fixture
def rota(monkeypatch):
    """Rota com todo o I/O mockado (sem pool real — ver gotcha do TestClient)."""
    from whatsapp_langchain.server.routes import webhook_waba as mod
    from whatsapp_langchain.shared.config import settings

    monkeypatch.setattr(settings, "meta_app_secret", SecretStr(SECRET))
    m = {
        "conexao": AsyncMock(return_value=_conexao()),
        "reivindicar": AsyncMock(return_value=True),
        "liberar": AsyncMock(),
        "eco": AsyncMock(),
        "historico": AsyncMock(return_value=1),
        "contato": AsyncMock(return_value=True),
        "conta": AsyncMock(return_value=1),
        "enqueue": AsyncMock(),
        "upsert": AsyncMock(return_value=MagicMock(id=11, telefone="+1", nome=None)),
        "open": AsyncMock(return_value=(_atendimento(5, None), False)),
        "guiado": AsyncMock(return_value=False),
        "hook": AsyncMock(),
    }
    monkeypatch.setattr(mod, "get_pool", AsyncMock(return_value=MagicMock()))
    monkeypatch.setattr(mod, "get_conexao_by_waba_phone_id", m["conexao"])
    monkeypatch.setattr(mod, "reivindicar_wamid", m["reivindicar"])
    monkeypatch.setattr(mod, "liberar_wamid", m["liberar"])
    monkeypatch.setattr(mod.waba_coexistence, "registrar_eco", m["eco"])
    monkeypatch.setattr(mod.waba_coexistence, "importar_historico", m["historico"])
    monkeypatch.setattr(mod.waba_coexistence, "sincronizar_contato", m["contato"])
    monkeypatch.setattr(mod.waba_coexistence, "processar_account_update", m["conta"])
    monkeypatch.setattr(mod, "enqueue_or_buffer", m["enqueue"])
    monkeypatch.setattr(mod, "upsert_cliente", m["upsert"])
    monkeypatch.setattr(mod, "open_or_attach_atendimento", m["open"])
    monkeypatch.setattr(mod, "detectar_fluxo_guiado", m["guiado"])
    monkeypatch.setattr(mod, "dispatch_event", m["hook"])
    monkeypatch.setattr(mod, "_resolve_waba_media_url", AsyncMock(return_value=None))
    return m


def test_rota_eco_nao_enfileira_para_a_ia(rota):
    r = _post(ECHO)
    assert r.status_code == 200, r.text
    rota["eco"].assert_awaited_once()
    rota["enqueue"].assert_not_awaited()


def test_rota_inbound_abre_atendimento_e_enfileira(rota):
    r = _post(INBOUND)
    assert r.status_code == 200, r.text
    rota["upsert"].assert_awaited_once()
    assert rota["upsert"].await_args.kwargs["nome"] == "Pablo"
    assert rota["enqueue"].await_args.kwargs["atendimento_id"] == 5
    rota["eco"].assert_not_awaited()


def test_rota_wamid_repetido_processa_uma_vez(rota):
    rota["reivindicar"].return_value = False
    assert _post(ECHO).status_code == 200
    assert _post(INBOUND).status_code == 200
    rota["eco"].assert_not_awaited()
    rota["enqueue"].assert_not_awaited()


def test_rota_phone_desconhecido_nao_grava(rota):
    rota["conexao"].return_value = None
    assert _post(ECHO).status_code == 200
    assert _post(HISTORY).status_code == 200
    rota["reivindicar"].assert_not_awaited()
    rota["eco"].assert_not_awaited()
    rota["historico"].assert_not_awaited()


def test_rota_hmac_invalido_nao_grava(rota):
    r = _post(ECHO, assinatura="sha256=" + "0" * 64)
    assert r.json()["status"] == "rejected"
    rota["conexao"].assert_not_awaited()
    rota["eco"].assert_not_awaited()


def test_rota_falha_no_eco_libera_wamid_e_devolve_503(rota):
    rota["eco"].side_effect = RuntimeError("banco fora")
    r = _post(ECHO)
    assert r.status_code == 503
    rota["liberar"].assert_awaited_once()


def test_rota_history_state_sync_e_account_update(rota):
    assert _post(HISTORY).status_code == 200
    assert _post(STATE_SYNC).status_code == 200
    assert _post(ACCOUNT_UPDATE).status_code == 200
    rota["historico"].assert_awaited_once()
    rota["contato"].assert_awaited_once()
    rota["conta"].assert_awaited_once()
    rota["enqueue"].assert_not_awaited()
