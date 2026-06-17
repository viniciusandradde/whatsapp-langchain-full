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

    def test_preview_crm_sem_auth_401(self) -> None:
        r = self._client().post("/api/campanhas/preview-crm", json={"tags": ["vip"]})
        assert r.status_code == 401, r.text

    def test_patch_sem_auth_401(self) -> None:
        r = self._client().patch("/api/campanhas/1", json={"nome": "x"})
        assert r.status_code == 401, r.text

    def test_add_destinatarios_sem_auth_401(self) -> None:
        r = self._client().post(
            "/api/campanhas/1/destinatarios", json={"telefones": ["+5511999999999"]}
        )
        assert r.status_code == 401, r.text

    def test_remove_destinatario_sem_auth_401(self) -> None:
        r = self._client().delete("/api/campanhas/1/destinatarios/1")
        assert r.status_code == 401, r.text

    def test_clonar_sem_auth_401(self) -> None:
        r = self._client().post("/api/campanhas/1/clonar")
        assert r.status_code == 401, r.text


@pytest.mark.docker_demo
class TestEditar:
    @pytest.fixture(scope="class")
    def empresa(self):
        db = get_db_url()
        with psycopg.connect(db, autocommit=True) as conn:
            row = conn.execute(
                "INSERT INTO empresa (nome, slug) VALUES (%s, %s) RETURNING id",
                (f"edit-{_RUN}", f"edit-{_RUN}"),
            ).fetchone()
            assert row is not None
            eid = row[0]
        yield eid
        with psycopg.connect(db, autocommit=True) as conn:
            conn.execute("DELETE FROM empresa WHERE id = %s", (eid,))

    async def _nova(self, pool, empresa):
        from whatsapp_langchain.shared.campanha import create_campanha
        from whatsapp_langchain.shared.rls_context import empresa_scope

        with empresa_scope(empresa):
            return await create_campanha(
                pool,
                empresa,
                nome=f"e-{_RUN}",
                descricao=None,
                mensagem="oi",
                conexao_id=None,
                intervalo_ms=500,
                max_destinatarios=1000,
                telefones_brutos=["+5511960000001"],
                user_id=None,
            )

    async def test_update_add_remove(self, empresa) -> None:
        from whatsapp_langchain.shared.campanha import (
            add_destinatarios,
            get_campanha,
            list_destinatarios,
            remove_destinatario,
            update_campanha,
        )
        from whatsapp_langchain.shared.db import get_pool

        pool = await get_pool()
        camp = await self._nova(pool, empresa)
        cid = camp["id"]

        # update mensagem
        upd = await update_campanha(pool, empresa, cid, {"mensagem": "nova msg"})
        assert upd["mensagem"] == "nova msg"

        # add 2 telefones → total 3
        r = await add_destinatarios(pool, empresa, cid, ["+5511960000002", "+5511960000003"])
        assert r["novos"] == 2 and r["total"] == 3
        c2 = await get_campanha(pool, empresa, cid)
        assert c2["total_destinatarios"] == 3

        # remove 1 → total 2
        dests = await list_destinatarios(pool, cid, limit=10)
        rem = await remove_destinatario(pool, empresa, cid, dests[0]["id"])
        assert rem["removido"] is True and rem["total"] == 2

    async def test_update_rejeita_running(self, empresa) -> None:
        import pytest as _pytest

        from whatsapp_langchain.shared.campanha import update_campanha
        from whatsapp_langchain.shared.db import get_pool

        pool = await get_pool()
        camp = await self._nova(pool, empresa)
        with psycopg.connect(get_db_url(), autocommit=True) as conn:
            conn.execute(
                "UPDATE campanha SET status='running' WHERE id=%s", (camp["id"],)
            )
        with _pytest.raises(ValueError, match="não pode ser alterada"):
            await update_campanha(pool, empresa, camp["id"], {"mensagem": "x"})

    async def test_clonar_cria_rascunho_com_destinatarios(self, empresa) -> None:
        from whatsapp_langchain.shared.campanha import (
            add_destinatarios,
            clonar_campanha,
            get_campanha,
            list_destinatarios,
        )
        from whatsapp_langchain.shared.db import get_pool

        pool = await get_pool()
        camp = await self._nova(pool, empresa)  # 1 destinatário
        await add_destinatarios(pool, empresa, camp["id"], ["+5511960000099"])  # +1
        # marca a original como done (simula já-enviada)
        with psycopg.connect(get_db_url(), autocommit=True) as conn:
            conn.execute(
                "UPDATE campanha SET status='done' WHERE id=%s", (camp["id"],)
            )
        nova = await clonar_campanha(pool, empresa, camp["id"])
        assert nova["status"] == "draft"
        assert nova["nome"].endswith("(cópia)")
        assert nova["id"] != camp["id"]
        # destinatários copiados, todos pendente
        dn = await list_destinatarios(pool, nova["id"], limit=50)
        assert len(dn) == 2
        assert all(d["status"] == "pendente" for d in dn)
        # original intacta (ainda done)
        orig = await get_campanha(pool, empresa, camp["id"])
        assert orig["status"] == "done"


@pytest.mark.docker_demo
class TestAgendamento:
    @pytest.fixture(scope="class")
    def empresa(self):
        db = get_db_url()
        with psycopg.connect(db, autocommit=True) as conn:
            row = conn.execute(
                "INSERT INTO empresa (nome, slug) VALUES (%s, %s) RETURNING id",
                (f"agd-{_RUN}", f"agd-{_RUN}"),
            ).fetchone()
            assert row is not None
            eid = row[0]
        yield eid
        with psycopg.connect(db, autocommit=True) as conn:
            conn.execute("DELETE FROM empresa WHERE id = %s", (eid,))

    async def test_agenda_e_claim_atomico(self, empresa) -> None:
        from whatsapp_langchain.shared.campanha import (
            claim_scheduled_due,
            create_campanha,
        )
        from whatsapp_langchain.shared.db import get_pool
        from whatsapp_langchain.shared.rls_context import empresa_scope

        pool = await get_pool()
        with empresa_scope(empresa):
            out = await create_campanha(
                pool,
                empresa,
                nome=f"agendada-{_RUN}",
                descricao=None,
                mensagem="Olá",
                conexao_id=None,
                intervalo_ms=500,
                max_destinatarios=1000,
                telefones_brutos=["+5511970009999"],
                user_id=None,
                scheduled_at="2020-01-01T00:00:00+00:00",  # passado → vencida
                agendar=True,
            )
        assert out["status"] == "scheduled", out

        # 1º claim pega; 2º não devolve de novo (idempotente/atômico)
        due1 = await claim_scheduled_due(pool)
        assert (empresa, out["id"]) in due1
        due2 = await claim_scheduled_due(pool)
        assert (empresa, out["id"]) not in due2
        # status agora é running
        with psycopg.connect(get_db_url(), autocommit=True) as conn:
            st = conn.execute(
                "SELECT status FROM campanha WHERE id = %s", (out["id"],)
            ).fetchone()
        assert st[0] == "running", st


@pytest.mark.docker_demo
class TestCrmTargeting:
    @pytest.fixture(scope="class")
    def empresa(self):
        db = get_db_url()
        with psycopg.connect(db, autocommit=True) as conn:
            row = conn.execute(
                "INSERT INTO empresa (nome, slug) VALUES (%s, %s) RETURNING id",
                (f"crm-{_RUN}", f"crm-{_RUN}"),
            ).fetchone()
            assert row is not None
            eid = row[0]
        yield eid
        with psycopg.connect(db, autocommit=True) as conn:
            conn.execute("DELETE FROM empresa WHERE id = %s", (eid,))

    async def test_resolve_por_tag_e_segmento(self, empresa) -> None:
        from whatsapp_langchain.shared.cliente import resolve_telefones_por_filtro
        from whatsapp_langchain.shared.db import get_pool
        from whatsapp_langchain.shared.rls_context import empresa_scope

        with psycopg.connect(get_db_url(), autocommit=True) as conn:
            # 2 clientes VIP + 1 sem tag; 1 do segmento "ouro"
            ids = []
            for i, (tel, seg) in enumerate(
                [("+5511970000001", "ouro"), ("+5511970000002", None), ("+5511970000003", None)]
            ):
                r = conn.execute(
                    "INSERT INTO cliente (empresa_id, telefone, nome, segmento)"
                    " VALUES (%s, %s, %s, %s) RETURNING id",
                    (empresa, tel, f"C{i}", seg),
                ).fetchone()
                ids.append(r[0])
            # tag VIP nos 2 primeiros
            for cid in ids[:2]:
                conn.execute(
                    "INSERT INTO cliente_tag (cliente_id, tag) VALUES (%s, 'vip')",
                    (cid,),
                )

        pool = await get_pool()
        with empresa_scope(empresa):
            vip = await resolve_telefones_por_filtro(pool, empresa, tags=["vip"])
            ouro = await resolve_telefones_por_filtro(pool, empresa, segmento="ouro")
            todos = await resolve_telefones_por_filtro(pool, empresa)
        assert set(vip) == {"+5511970000001", "+5511970000002"}
        assert ouro == ["+5511970000001"]
        assert len(todos) == 3  # todos têm telefone


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
