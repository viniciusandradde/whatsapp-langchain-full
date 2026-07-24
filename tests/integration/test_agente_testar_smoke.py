"""Smoke do módulo Teste de Agente (chat no painel sem WhatsApp).

Valida registro da rota + exigência de auth. O comportamento real
(pipeline load_graph) é validado manualmente via painel — o handler abre
checkpointer/store reais, inviável em unit test sem stack.
"""

from fastapi.testclient import TestClient


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmoke:
    def test_testar_sem_auth_401(self) -> None:
        resp = _client().post(
            "/api/v1/agentes/qualquer/testar", json={"mensagem": "oi"}
        )
        assert resp.status_code == 401

    def test_testar_reset_sem_auth_401(self) -> None:
        resp = _client().post(
            "/api/v1/agentes/qualquer/testar",
            json={"mensagem": "", "resetar": True},
        )
        assert resp.status_code == 401


class TestSmokeBateria:
    def test_bateria_sem_auth_401(self) -> None:
        resp = _client().post(
            "/api/v1/agentes/qualquer/testar-bateria",
            json={"modelos": ["google/gemini-2.5-flash"]},
        )
        assert resp.status_code == 401

    def test_testar_com_modelo_sem_auth_401(self) -> None:
        resp = _client().post(
            "/api/v1/agentes/qualquer/testar",
            json={"mensagem": "oi", "modelo": "gpt-4o-mini"},
        )
        assert resp.status_code == 401


class TestContratoBateria:
    """Contrato de 1 a 4 modelos (comparação simultânea na aba Testar)."""

    def test_aceita_ate_4_modelos(self) -> None:
        from whatsapp_langchain.server.routes.agente import TestarBateriaInput

        body = TestarBateriaInput(
            modelos=[
                "google/gemini-2.5-flash",
                "deepseek/deepseek-v3.2",
                "z-ai/glm-4.7-flash",
                "anthropic/claude-haiku-4.5",
            ]
        )
        assert len(body.modelos) == 4

    def test_rejeita_lista_vazia(self) -> None:
        import pytest
        from pydantic import ValidationError

        from whatsapp_langchain.server.routes.agente import TestarBateriaInput

        with pytest.raises(ValidationError):
            TestarBateriaInput(modelos=[])

    def test_rejeita_mais_de_4_modelos(self) -> None:
        import pytest
        from pydantic import ValidationError

        from whatsapp_langchain.server.routes.agente import TestarBateriaInput

        with pytest.raises(ValidationError):
            TestarBateriaInput(modelos=["a", "b", "c", "d", "e"])


class TestContratoMidia:
    """Contrato do anexo de mídia (áudio/documento/imagem) no chat de teste."""

    def test_input_aceita_midia(self) -> None:
        from whatsapp_langchain.server.routes.agente import TestarAgenteInput

        body = TestarAgenteInput(
            mensagem="",
            midia_base64="QUJD",
            midia_tipo="audio/ogg",
            midia_nome="nota.ogg",
        )
        assert body.midia_tipo == "audio/ogg"
        assert body.midia_nome == "nota.ogg"

    def test_input_sem_midia_default_none(self) -> None:
        from whatsapp_langchain.server.routes.agente import TestarAgenteInput

        body = TestarAgenteInput(mensagem="oi")
        assert body.midia_base64 is None
        assert body.midia_tipo is None
