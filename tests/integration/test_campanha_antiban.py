"""E2E do anti-ban configurável na criação de campanha (jitter + kill-switch).

Smoke (CI): o endpoint existe e exige auth.
E2E (docker_demo): `create_campanha` GRAVA intervalo_min/max_ms e kill_switch_pct
(antes caíam só nos defaults do banco, sem como o usuário ajustar).
"""

from __future__ import annotations

import uuid

import psycopg
import pytest

from .helpers import get_db_url

_RUN = uuid.uuid4().hex[:8]


class TestCampanhaCreateSmoke:
    def _client(self):
        from fastapi.testclient import TestClient

        from whatsapp_langchain.server.main import app

        return TestClient(app)

    def test_create_sem_auth_401(self) -> None:
        r = self._client().post(
            "/api/campanhas",
            json={"nome": "x", "mensagem": "oi", "telefones": ["+5511999999999"]},
        )
        assert r.status_code == 401, r.text

    def test_upload_media_sem_auth_401(self) -> None:
        r = self._client().post(
            "/api/campanhas/upload-media",
            files={"file": ("f.png", b"x", "image/png")},
        )
        assert r.status_code == 401, r.text


@pytest.mark.docker_demo
class TestCampanhaAntiBanPersistencia:
    @pytest.fixture(scope="class")
    def empresa(self):
        db = get_db_url()
        with psycopg.connect(db, autocommit=True) as conn:
            row = conn.execute(
                "INSERT INTO empresa (nome, slug) VALUES (%s, %s) RETURNING id",
                (f"ab-{_RUN}", f"ab-{_RUN}"),
            ).fetchone()
            assert row is not None
            eid = row[0]
        yield eid
        with psycopg.connect(db, autocommit=True) as conn:
            conn.execute("DELETE FROM empresa WHERE id = %s", (eid,))

    async def test_grava_jitter_e_kill_switch(self, empresa) -> None:
        from whatsapp_langchain.shared.campanha import create_campanha
        from whatsapp_langchain.shared.db import get_pool

        pool = await get_pool()
        out = await create_campanha(
            pool,
            empresa,
            nome=f"campanha-{_RUN}",
            descricao=None,
            mensagem="Olá",
            conexao_id=None,
            intervalo_ms=500,
            max_destinatarios=1000,
            telefones_brutos=["+5511999990001", "+5511999990002"],
            user_id=None,
            intervalo_min_ms=5000,
            intervalo_max_ms=15000,
            kill_switch_pct=25,
        )
        with psycopg.connect(get_db_url(), autocommit=True) as conn:
            row = conn.execute(
                "SELECT intervalo_min_ms, intervalo_max_ms, kill_switch_pct"
                " FROM campanha WHERE id = %s",
                (out["id"],),
            ).fetchone()
        assert row == (5000, 15000, 25), row

    async def test_min_maior_que_max_e_normalizado(self, empresa) -> None:
        """Helper troca min/max invertidos pra respeitar o CHECK do banco."""
        from whatsapp_langchain.shared.campanha import create_campanha
        from whatsapp_langchain.shared.db import get_pool

        pool = await get_pool()
        out = await create_campanha(
            pool,
            empresa,
            nome=f"campanha-inv-{_RUN}",
            descricao=None,
            mensagem="Olá",
            conexao_id=None,
            intervalo_ms=500,
            max_destinatarios=1000,
            telefones_brutos=["+5511999990003"],
            user_id=None,
            intervalo_min_ms=15000,
            intervalo_max_ms=5000,
        )
        with psycopg.connect(get_db_url(), autocommit=True) as conn:
            row = conn.execute(
                "SELECT intervalo_min_ms, intervalo_max_ms FROM campanha WHERE id = %s",
                (out["id"],),
            ).fetchone()
        assert row == (5000, 15000), row  # trocados

    async def test_grava_media(self, empresa) -> None:
        """Campanha com foto: media_url/media_tipo persistidos (legenda opcional)."""
        from whatsapp_langchain.shared.campanha import create_campanha
        from whatsapp_langchain.shared.db import get_pool

        pool = await get_pool()
        out = await create_campanha(
            pool,
            empresa,
            nome=f"campanha-foto-{_RUN}",
            descricao=None,
            mensagem="Confira a promoção!",
            conexao_id=None,
            intervalo_ms=500,
            max_destinatarios=1000,
            telefones_brutos=["+5511999990004"],
            user_id=None,
            media_url="/uploads/disparador/foto.jpg",
            media_tipo="image",
        )
        assert out["media_url"] == "/uploads/disparador/foto.jpg"
        assert out["media_tipo"] == "image"
