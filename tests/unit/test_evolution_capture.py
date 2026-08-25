"""Testes unitários dos métodos de captura do EvolutionClient (Task 4.4).

Mocka `httpx.AsyncClient` (o client cria a instância internamente) pra validar
o parsing das respostas da Evolution, e cobre o modo mock (sem HTTP).
"""

from __future__ import annotations

import pytest

from whatsapp_langchain.worker import evolution_client as ec
from whatsapp_langchain.worker.evolution_client import EvolutionClient, phone_from_jid


class _FakeResp:
    def __init__(self, json_data, status: int = 200):
        self._j = json_data
        self.status_code = status
        self.text = "" if status < 300 else "erro"

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self):
        return self._j


class _FakeClient:
    def __init__(self, resp: _FakeResp):
        self._resp = resp
        self.calls: list[tuple] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, **kw):
        self.calls.append(("POST", url, kw))
        return self._resp

    async def get(self, url, **kw):
        self.calls.append(("GET", url, kw))
        return self._resp


def _patch_httpx(monkeypatch, resp: _FakeResp) -> _FakeClient:
    fake = _FakeClient(resp)
    monkeypatch.setattr(ec.httpx, "AsyncClient", lambda *a, **k: fake)
    return fake


def _real_client() -> EvolutionClient:
    return EvolutionClient("https://evo.example.com", "k", "inst", delivery_mode="real")


def _mock_client() -> EvolutionClient:
    return EvolutionClient("", "", "", delivery_mode="mock")


class TestPhoneFromJid:
    def test_individual(self):
        assert phone_from_jid("5511999999999@s.whatsapp.net") == "+5511999999999"

    def test_lid_retorna_none(self):
        assert phone_from_jid("123456@lid") is None

    def test_vazio(self):
        assert phone_from_jid("") is None


class TestCheckNumbers:
    async def test_mock_assume_existem(self):
        out = await _mock_client().check_numbers(["+5511988887777", "5511.222"])
        assert len(out) == 2
        assert all(n["exists"] for n in out)
        assert out[0]["wa_jid"].endswith("@s.whatsapp.net")

    async def test_parse_resposta(self, monkeypatch):
        resp = _FakeResp(
            [
                {
                    "jid": "5511999999999@s.whatsapp.net",
                    "exists": True,
                    "number": "5511999999999",
                },
                {"jid": "5511000000000@s.whatsapp.net", "exists": False},
            ]
        )
        _patch_httpx(monkeypatch, resp)
        out = await _real_client().check_numbers(["x", "y"])
        assert out[0]["exists"] is True
        assert out[0]["telefone"] == "5511999999999"
        assert out[1]["exists"] is False
        assert out[1]["telefone"] == "+5511000000000"  # derivado do jid

    async def test_erro_http_levanta(self, monkeypatch):
        _patch_httpx(monkeypatch, _FakeResp({}, status=500))
        with pytest.raises(ec.EvolutionSendError):
            await _real_client().check_numbers(["x"])


class TestFetchContacts:
    async def test_mock_vazio(self):
        assert await _mock_client().fetch_contacts() == []

    async def test_parse_is_business(self, monkeypatch):
        resp = _FakeResp(
            [
                {
                    "id": "5511@s.whatsapp.net",
                    "pushName": "João",
                    "verifiedName": "Loja X",
                },
                {"id": "5512@s.whatsapp.net", "pushName": "Maria"},
                {"pushName": "sem-jid"},  # descartado
            ]
        )
        _patch_httpx(monkeypatch, resp)
        out = await _real_client().fetch_contacts()
        assert len(out) == 2
        assert out[0]["is_business"] is True
        assert out[0]["verified_name"] == "Loja X"
        assert out[1]["is_business"] is False

    async def test_usa_remotejid_e_ignora_cuid_interno(self, monkeypatch):
        """Evolution v2: `id` é cuid interno; o JID real vem em `remoteJid`."""
        resp = _FakeResp(
            [
                # cuid interno + remoteJid real → usa remoteJid (telefone derivável)
                {
                    "id": "cmq866i4j1wzjpn4xlm0kbk0i",
                    "remoteJid": "5511999999999@s.whatsapp.net",
                    "pushName": "Ariel",
                },
                # só cuid (sem remoteJid/number) → descartado (não vira telefone)
                {"id": "cmpwqmhki1vp5pn4xh025ykkv", "pushName": "SemJid"},
                # número em `number` → constrói JID @s.whatsapp.net
                {"id": "cmqzzz", "number": "5511888887777", "pushName": "Por número"},
            ]
        )
        _patch_httpx(monkeypatch, resp)
        out = await _real_client().fetch_contacts()
        jids = [c["wa_jid"] for c in out]
        assert "5511999999999@s.whatsapp.net" in jids
        assert "5511888887777@s.whatsapp.net" in jids
        assert not any(j.startswith(("cmq", "cmp")) for j in jids)
        assert len(out) == 2  # o só-cuid foi descartado


class TestFetchGroups:
    async def test_parse_invite_link_e_count(self, monkeypatch):
        resp = _FakeResp(
            [
                {
                    "id": "12036@g.us",
                    "subject": "Grupo A",
                    "desc": "desc",
                    "size": 3,
                    "inviteCode": "abc123",
                },
                {"subject": "sem-id"},  # descartado
            ]
        )
        _patch_httpx(monkeypatch, resp)
        out = await _real_client().fetch_groups()
        assert len(out) == 1
        assert out[0]["wa_group_id"] == "12036@g.us"
        assert out[0]["invite_link"] == "https://chat.whatsapp.com/abc123"
        assert out[0]["participantes_count"] == 3


class TestFetchGroupParticipants:
    async def test_parse_admin(self, monkeypatch):
        resp = _FakeResp(
            {
                "participants": [
                    {"id": "5511@s.whatsapp.net", "admin": "admin"},
                    {"id": "9988@lid", "admin": None},
                ]
            }
        )
        _patch_httpx(monkeypatch, resp)
        out = await _real_client().fetch_group_participants("12036@g.us")
        assert len(out) == 2
        assert out[0]["is_admin"] is True
        assert out[1]["is_admin"] is False
        assert out[1]["wa_jid"].endswith("@lid")


class TestSendMedia:
    async def test_mock_retorna_id(self):
        mid = await _mock_client().send_media(
            "+5511999999999", "https://x/foto.jpg", caption="oi"
        )
        assert mid.startswith("mock-evo-media-")

    async def test_real_posta_payload(self, monkeypatch):
        fake = _patch_httpx(monkeypatch, _FakeResp({"key": {"id": "MID123"}}))
        mid = await _real_client().send_media(
            "+5511999999999",
            "https://x/foto.jpg",
            mediatype="image",
            caption="legenda",
        )
        assert mid == "MID123"
        # confere que mandou number/mediatype/media/caption pro sendMedia
        method, url, kw = fake.calls[-1]
        assert method == "POST"
        assert "/message/sendMedia/" in url
        body = kw["json"]
        assert body["mediatype"] == "image"
        assert body["media"] == "https://x/foto.jpg"
        assert body["caption"] == "legenda"
        assert body["number"] == "5511999999999"

    async def test_erro_http_levanta(self, monkeypatch):
        _patch_httpx(monkeypatch, _FakeResp({}, status=400))
        with pytest.raises(ec.EvolutionSendError):
            await _real_client().send_media("+5511999999999", "https://x/f.jpg")


class TestHealth:
    async def test_mock(self):
        h = await _mock_client().health()
        assert h["state"] == "open"


class TestTimeoutDeGrupo:
    """Listar grupos precisa de MUITO mais tempo que o resto.

    Medido em produção (instância do Luis, 2026-08-25): `fetchAllGroups`
    devolveu 456 grupos em **149,7s** já sem participantes, enquanto
    `findContacts` traz 2.463 contatos em segundos — o Baileys consulta o
    servidor do WhatsApp ao vivo pra grupos e lê cache local pra contatos.
    Nos 60s antigos a captura de grupos daquela conta falhava sempre
    (lotes 4, 6 e 7, todos ReadTimeout em 60,03s).
    """

    async def test_fetch_groups_usa_o_teto_de_grupo(self, monkeypatch):
        fake = _patch_httpx(monkeypatch, _FakeResp([]))
        await _real_client().fetch_groups()
        assert fake.calls[0][2]["timeout"] == ec.EVOLUTION_GROUP_TIMEOUT

    async def test_fetch_group_participants_usa_o_teto_de_grupo(self, monkeypatch):
        fake = _patch_httpx(monkeypatch, _FakeResp({"participants": []}))
        await _real_client().fetch_group_participants("123@g.us")
        assert fake.calls[0][2]["timeout"] == ec.EVOLUTION_GROUP_TIMEOUT

    async def test_teto_com_folga_sobre_a_medicao(self):
        assert ec.EVOLUTION_GROUP_TIMEOUT >= 2 * 149.7

    async def test_envio_NAO_herda_o_teto_de_grupo(self, monkeypatch):
        """Guarda do erro cometido ao aplicar esta mudança.

        Uma primeira tentativa trocou o timeout de `send_media`/`send_audio`
        por engano: mensagem presa 5 minutos num provedor mudo é o oposto do
        que se quer no caminho de envio.
        """
        for enviar in (
            lambda c: c.send_media("+5511999999999", "https://x/f.jpg"),
            lambda c: c.send_audio("+5511999999999", "YmFzZTY0"),
        ):
            fake = _patch_httpx(monkeypatch, _FakeResp({"key": {"id": "m1"}}))
            await enviar(_real_client())
            assert fake.calls[0][2]["timeout"] < ec.EVOLUTION_GROUP_TIMEOUT
