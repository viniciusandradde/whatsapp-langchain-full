"""Smoke + E2E do preview de disparo (Task 7)."""

from __future__ import annotations

import uuid

import psycopg
import pytest

from .helpers import get_db_url

_RUN = uuid.uuid4().hex[:8]


class TestPreviewSmoke:
    def _client(self):
        from fastapi.testclient import TestClient

        from whatsapp_langchain.server.main import app

        return TestClient(app)

    def test_preview_sem_auth_401(self) -> None:
        r = self._client().post(
            "/api/disparador/preview",
            json={"origem": {"tipo": "contatos"}},
        )
        assert r.status_code == 401, r.text


@pytest.mark.docker_demo
class TestPreviewResolver:
    @pytest.fixture(scope="class")
    def empresa(self):
        db = get_db_url()
        with psycopg.connect(db, autocommit=True) as conn:
            row = conn.execute(
                "INSERT INTO empresa (nome) VALUES (%s) RETURNING id",
                (f"prev-{_RUN}",),
            ).fetchone()
            assert row is not None
            eid = row[0]
        yield eid
        with psycopg.connect(db, autocommit=True) as conn:
            conn.execute("DELETE FROM empresa WHERE id = %s", (eid,))

    async def test_preview_dedup_e_ignora_lid(self, empresa) -> None:
        from whatsapp_langchain.shared.db import get_pool
        from whatsapp_langchain.shared.disparo import OrigemConfig, preview_disparo

        tel = f"+5511{_RUN[:7]}"
        with psycopg.connect(get_db_url(), autocommit=True) as conn:
            # dois contatos com MESMO telefone (jids diferentes) → dedup
            conn.execute(
                "INSERT INTO contato_capturado (empresa_id, wa_jid, telefone)"
                " VALUES (%s, %s, %s), (%s, %s, %s)",
                (
                    empresa,
                    f"a{_RUN}@s.whatsapp.net",
                    tel,
                    empresa,
                    f"b{_RUN}@s.whatsapp.net",
                    tel,
                ),
            )
            # contato só-LID (telefone NULL) → não entra no disparo
            conn.execute(
                "INSERT INTO contato_capturado (empresa_id, wa_jid, telefone)"
                " VALUES (%s, %s, NULL)",
                (empresa, f"lid{_RUN}@lid"),
            )

        pool = await get_pool()
        res = await preview_disparo(
            pool, empresa, OrigemConfig(tipo="contatos"), validar_numeros=False
        )
        assert res.total_bruto == 2  # só os 2 com telefone foram resolvidos
        assert res.count_duplicado == 1  # mesmo telefone
        assert res.total_disponivel == 1  # após dedup
        assert res.amostra == [tel]
