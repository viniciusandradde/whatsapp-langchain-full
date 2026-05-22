"""Sprint Q.6 — smoke tests dos endpoints + dependencies de quota."""

from __future__ import annotations

from fastapi.testclient import TestClient


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmokeQuotaEndpoint:
    def test_get_quota_sem_auth_401(self) -> None:
        resp = _client().get("/api/empresas/1/quota")
        assert resp.status_code == 401, resp.text


class TestPlanoLimits:
    """Tests unitários da lógica PlanoInfo (sem DB)."""

    def test_plano_info_limite_de_recurso(self):
        from whatsapp_langchain.shared.plano_limits import PlanoInfo

        plano = PlanoInfo(
            empresa_id=1, plano_id=1, plano_slug="free", plano_nome="Free",
            preco_mensal_brl=0.0,
            limite_usuarios=2, limite_conexoes=1,
            limite_atendimentos_mes=100, limite_orcamento_ia_usd=5.0,
            limite_documentos_kb=5,
            features={"calendar": False, "mcp": False},
        )
        assert plano.limite_de("conexoes") == 1
        assert plano.limite_de("usuarios") == 2

    def test_passou_limite_strict(self):
        from whatsapp_langchain.shared.plano_limits import PlanoInfo

        plano = PlanoInfo(
            empresa_id=1, plano_id=1, plano_slug="free", plano_nome="Free",
            preco_mensal_brl=0.0,
            limite_usuarios=2, limite_conexoes=1,
            limite_atendimentos_mes=100, limite_orcamento_ia_usd=5.0,
            limite_documentos_kb=5,
        )
        # exatamente no limite = passou (próximo INSERT cria #2 em plano max=1)
        assert plano.passou_limite("conexoes", 1) is True
        assert plano.passou_limite("conexoes", 0) is False
        assert plano.passou_limite("conexoes", 99) is True

    def test_limite_none_e_ilimitado(self):
        from whatsapp_langchain.shared.plano_limits import PlanoInfo

        plano = PlanoInfo(
            empresa_id=1, plano_id=3, plano_slug="enterprise",
            plano_nome="Enterprise", preco_mensal_brl=1499.0,
            limite_usuarios=None, limite_conexoes=None,
            limite_atendimentos_mes=None, limite_orcamento_ia_usd=500.0,
            limite_documentos_kb=None,
        )
        assert plano.limite_de("conexoes") is None
        assert plano.passou_limite("conexoes", 999) is False
        assert plano.passou_limite("usuarios", 100_000) is False

    def test_feature_check(self):
        from whatsapp_langchain.shared.plano_limits import PlanoInfo

        plano = PlanoInfo(
            empresa_id=1, plano_id=2, plano_slug="pro", plano_nome="Pro",
            preco_mensal_brl=299.0,
            limite_usuarios=10, limite_conexoes=3,
            limite_atendimentos_mes=5000, limite_orcamento_ia_usd=100.0,
            limite_documentos_kb=100,
            features={"calendar": True, "rbac": True, "mcp": False, "white_label": False},
        )
        assert plano.tem_feature("calendar") is True
        assert plano.tem_feature("rbac") is True
        assert plano.tem_feature("mcp") is False
        assert plano.tem_feature("white_label") is False
        assert plano.tem_feature("inexistente") is False

    def test_upgrade_sugerido(self):
        from whatsapp_langchain.shared.plano_limits import PlanoInfo

        def make(slug: str):
            return PlanoInfo(
                empresa_id=1, plano_id=1, plano_slug=slug, plano_nome=slug.title(),
                preco_mensal_brl=0.0,
                limite_usuarios=2, limite_conexoes=1,
                limite_atendimentos_mes=100, limite_orcamento_ia_usd=5.0,
                limite_documentos_kb=5,
            )

        assert make("free").upgrade_sugerido() == "pro"
        assert make("pro").upgrade_sugerido() == "enterprise"
        assert make("enterprise").upgrade_sugerido() is None

    def test_recurso_invalido_raises(self):
        from whatsapp_langchain.shared.plano_limits import PlanoInfo
        import pytest

        plano = PlanoInfo(
            empresa_id=1, plano_id=1, plano_slug="free", plano_nome="Free",
            preco_mensal_brl=0.0,
            limite_usuarios=2, limite_conexoes=1,
            limite_atendimentos_mes=100, limite_orcamento_ia_usd=5.0,
            limite_documentos_kb=5,
        )
        with pytest.raises(ValueError, match="Recurso desconhecido"):
            plano.limite_de("hacking")


class TestDependencyFactory:
    """Tests da factory require_plano_limit / require_plano_feature."""

    def test_require_plano_limit_recurso_invalido(self):
        from whatsapp_langchain.server.dependencies_plano import require_plano_limit
        import pytest

        with pytest.raises(ValueError, match="recurso inválido"):
            require_plano_limit("hacking")

    def test_require_plano_feature_aceita_qualquer_string(self):
        # feature é validada em runtime contra plano.features (dict livre)
        from whatsapp_langchain.server.dependencies_plano import require_plano_feature

        dep = require_plano_feature("calendar")
        assert callable(dep)
