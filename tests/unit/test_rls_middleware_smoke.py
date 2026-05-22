"""Sprint A.2.4 — testes smoke do middleware RLS + contextvar."""

from __future__ import annotations

import pytest

from whatsapp_langchain.shared.rls_context import (
    clear_request_context,
    empresa_scope,
    get_request_context,
    set_request_context,
)


@pytest.fixture(autouse=True)
def _reset_context():
    clear_request_context()
    yield
    clear_request_context()


class TestRlsContextVar:
    def test_default_e_none_e_bypass_false(self):
        assert get_request_context() == (None, False)

    def test_set_empresa_id(self):
        set_request_context(42)
        assert get_request_context() == (42, False)

    def test_set_bypass_separa_empresa(self):
        set_request_context(empresa_id=None, bypass=True)
        assert get_request_context() == (None, True)

    def test_clear_volta_pro_default(self):
        set_request_context(99)
        clear_request_context()
        assert get_request_context() == (None, False)

    def test_empresa_scope_restaura_apos_with(self):
        set_request_context(1)
        with empresa_scope(2):
            assert get_request_context() == (2, False)
        # Volta pra 1 (estado anterior preservado)
        assert get_request_context() == (1, False)

    def test_empresa_scope_aninhado(self):
        with empresa_scope(1):
            with empresa_scope(2):
                with empresa_scope(3):
                    assert get_request_context() == (3, False)
                assert get_request_context() == (2, False)
            assert get_request_context() == (1, False)
        assert get_request_context() == (None, False)


class TestRlsMiddleware:
    """Smoke: middleware extrai X-Empresa-Id e seta contextvar.

    Endpoint dummy lê contextvar pra confirmar propagação.
    """

    def test_middleware_seta_empresa_id_do_header(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from whatsapp_langchain.server.middlewares import install_rls_context

        app = FastAPI()
        install_rls_context(app)

        @app.get("/_test_rls")
        async def _test():
            empresa_id, bypass = get_request_context()
            return {"empresa_id": empresa_id, "bypass": bypass}

        with TestClient(app) as client:
            r = client.get("/_test_rls", headers={"X-Empresa-Id": "42"})
            assert r.status_code == 200
            assert r.json() == {"empresa_id": 42, "bypass": False}

    def test_middleware_sem_header_deixa_none(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from whatsapp_langchain.server.middlewares import install_rls_context

        app = FastAPI()
        install_rls_context(app)

        @app.get("/_test_rls")
        async def _test():
            return dict(zip(["empresa_id", "bypass"], get_request_context()))

        with TestClient(app) as client:
            r = client.get("/_test_rls")
            assert r.status_code == 200
            assert r.json() == {"empresa_id": None, "bypass": False}

    def test_middleware_ignora_header_invalido(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from whatsapp_langchain.server.middlewares import install_rls_context

        app = FastAPI()
        install_rls_context(app)

        @app.get("/_test_rls")
        async def _test():
            return dict(zip(["empresa_id", "bypass"], get_request_context()))

        with TestClient(app) as client:
            r = client.get("/_test_rls", headers={"X-Empresa-Id": "abc"})
            assert r.status_code == 200
            assert r.json() == {"empresa_id": None, "bypass": False}
