"""Mig 177 — smoke da feature de plano 'voz' (preview + PUT da empresa).

Voz do agente (mig 176) virou feature de PLANO: Pro/Enterprise têm,
Free/Pessoal não. Gate HTTP em 2 lugares — preview da voz e PUT da
empresa quando tenta LIGAR `voz_ativa` — ambos 402 com mensagem pt-BR
amigável. Mocka `plano_limits` como `test_plano_quotas_smoke.py` faz
(PlanoInfo montado na mão, sem DB).
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

_MSG_PT = "Resposta em áudio está disponível nos planos Pro e Enterprise."


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


def _plano(features: dict):
    from whatsapp_langchain.shared.plano_limits import PlanoInfo

    return PlanoInfo(
        empresa_id=1,
        plano_id=1,
        plano_slug="free",
        plano_nome="Free",
        preco_mensal_brl=0.0,
        limite_usuarios=2,
        limite_conexoes=1,
        limite_atendimentos_mes=100,
        limite_orcamento_ia_usd=5.0,
        limite_documentos_kb=5,
        features=features,
    )


@pytest.fixture
def client_admin():
    """TestClient com service token + user resolvidos (sem DB de auth)."""
    from whatsapp_langchain.server.dependencies import (
        get_user_id_from_request,
        verify_service_token,
    )
    from whatsapp_langchain.server.main import app

    app.dependency_overrides[verify_service_token] = lambda: None
    app.dependency_overrides[get_user_id_from_request] = lambda: "user-test"
    yield TestClient(app)
    app.dependency_overrides.clear()


def _patches_plano_sem_voz():
    """Empresa admin OK + plano SEM a feature 'voz' (ex.: free)."""
    return (
        patch(
            "whatsapp_langchain.server.routes.empresa_admin.get_pool",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "whatsapp_langchain.server.routes.empresa_admin.is_admin_of",
            new=AsyncMock(return_value=True),
        ),
        patch(
            "whatsapp_langchain.server.dependencies_plano.get_pool",
            new=AsyncMock(return_value=None),
        ),
        patch(
            "whatsapp_langchain.server.dependencies_plano.get_plano_info",
            new=AsyncMock(return_value=_plano({"voz": False})),
        ),
    )


class TestSmokeVozPlano:
    def test_preview_sem_auth_401(self) -> None:
        resp = _client().post(
            "/api/empresas/1/voz/preview",
            json={"voz_nome": "alloy", "voz_estilo": ""},
        )
        assert resp.status_code == 401, resp.text

    def test_preview_402_plano_sem_voz(self, client_admin: TestClient) -> None:
        p1, p2, p3, p4 = _patches_plano_sem_voz()
        with p1, p2, p3, p4:
            resp = client_admin.post(
                "/api/empresas/1/voz/preview",
                json={"voz_nome": "alloy", "voz_estilo": ""},
            )
        assert resp.status_code == 402, resp.text
        detail = resp.json()["detail"]
        assert detail["error"] == "feature_unavailable"
        assert detail["feature"] == "voz"
        assert detail["message"] == _MSG_PT

    def test_put_voz_ativa_true_402_plano_sem_voz(
        self, client_admin: TestClient
    ) -> None:
        p1, p2, p3, p4 = _patches_plano_sem_voz()
        with p1, p2, p3, p4:
            resp = client_admin.put("/api/empresas/1", json={"voz_ativa": True})
        assert resp.status_code == 402, resp.text
        assert resp.json()["detail"]["message"] == _MSG_PT

    def test_put_voz_ativa_false_nao_gateia(self, client_admin: TestClient) -> None:
        """Desligar (ou só mexer em voz_nome/estilo) continua livre."""
        from whatsapp_langchain.shared.models import Empresa

        now = datetime.now(UTC)
        emp = Empresa(id=1, nome="Emp", slug="emp", created_at=now, updated_at=now)
        gate = AsyncMock(side_effect=AssertionError("não deveria gatear"))
        p1, p2, _p3, _p4 = _patches_plano_sem_voz()
        with (
            p1,
            p2,
            patch(
                "whatsapp_langchain.server.routes.empresa_admin.assert_plano_feature",
                new=gate,
            ),
            patch(
                "whatsapp_langchain.server.routes.empresa_admin.update_empresa",
                new=AsyncMock(return_value=emp),
            ),
        ):
            resp = client_admin.put(
                "/api/empresas/1",
                json={"voz_ativa": False, "voz_nome": "coral"},
            )
        assert resp.status_code == 200, resp.text
        gate.assert_not_awaited()


class TestAssertPlanoFeature:
    """Unit do helper (mesmo payload do require_plano_feature)."""

    async def test_libera_com_feature(self) -> None:
        from whatsapp_langchain.server.dependencies_plano import (
            assert_plano_feature,
        )

        with (
            patch(
                "whatsapp_langchain.server.dependencies_plano.get_pool",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "whatsapp_langchain.server.dependencies_plano.get_plano_info",
                new=AsyncMock(return_value=_plano({"voz": True})),
            ),
        ):
            # Não levanta — plano tem a feature.
            await assert_plano_feature(1, "voz")

    async def test_402_com_mensagem_custom(self) -> None:
        from fastapi import HTTPException

        from whatsapp_langchain.server.dependencies_plano import (
            assert_plano_feature,
        )

        with (
            patch(
                "whatsapp_langchain.server.dependencies_plano.get_pool",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "whatsapp_langchain.server.dependencies_plano.get_plano_info",
                new=AsyncMock(return_value=_plano({"voz": False})),
            ),
            pytest.raises(HTTPException) as exc,
        ):
            await assert_plano_feature(1, "voz", mensagem=_MSG_PT)
        assert exc.value.status_code == 402
        assert exc.value.detail["message"] == _MSG_PT
        assert exc.value.detail["upgrade_to"] == "pro"
