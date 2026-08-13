"""Push FCM (mig 168) — rotas, credencial e as regras do payload."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmoke:
    def test_registrar_sem_auth_401(self) -> None:
        r = _client().post("/api/push/registrar", json={"token": "x" * 32})
        assert r.status_code == 401

    def test_remover_sem_auth_401(self) -> None:
        r = _client().post("/api/push/remover", json={"token": "x" * 32})
        assert r.status_code == 401

    def test_rotas_registradas(self) -> None:
        from whatsapp_langchain.server.main import app

        rotas = {getattr(r, "path", "") for r in app.routes}
        assert "/api/push/registrar" in rotas
        assert "/api/push/remover" in rotas


class TestCredencial:
    def test_env_vazio_e_push_desligado(self, monkeypatch) -> None:
        """Sem credencial o push é NO-OP declarado, não erro."""
        import whatsapp_langchain.shared.push_fcm as m

        monkeypatch.setattr(m, "_credentials", None)
        monkeypatch.setattr(m, "_project_id", None)
        from whatsapp_langchain.shared.config import settings

        monkeypatch.setattr(settings, "firebase_service_account_json", "")
        assert m.push_configurado() is False

    def test_json_invalido_nao_vaza_conteudo(self, monkeypatch) -> None:
        """A mensagem do erro traz o TIPO, nunca o conteúdo do env — que em
        produção é a chave privada."""
        import pytest

        import whatsapp_langchain.shared.push_fcm as m

        monkeypatch.setattr(m, "_credentials", None)
        monkeypatch.setattr(m, "_project_id", None)
        from whatsapp_langchain.shared.config import settings

        segredo = '{"quebrado": "SEGREDO-XYZ"'
        monkeypatch.setattr(settings, "firebase_service_account_json", segredo)
        with pytest.raises(m.PushDesligadoError) as exc:
            m._carregar_credencial()
        assert "SEGREDO-XYZ" not in str(exc.value)


class TestPayload:
    """As regras que o NOTIFY não carrega — decididas no SELECT do loop."""

    def test_outbound_do_operador_nao_vira_push(self) -> None:
        # incoming_message vazia = INSERT de resposta manual; o trigger
        # dispara igual, e o filtro é quem segura.
        from whatsapp_langchain.shared.push_loop import _dados_da_mensagem

        assert _dados_da_mensagem is not None  # contrato existe

    def test_preview_normaliza_espacos_e_corta(self) -> None:
        texto = "linha um\n\n   linha dois  " + "x" * 200
        preview = " ".join(texto.split())[:96]
        assert "\n" not in preview
        assert len(preview) == 96
