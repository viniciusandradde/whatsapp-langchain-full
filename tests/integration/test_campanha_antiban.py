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

    def test_ext_campanha_sem_apikey_401(self) -> None:
        r = self._client().post(
            "/api/disparador/ext/campanha",
            json={"nome": "x", "telefones": ["+5511999999999"]},
        )
        assert r.status_code == 401, r.text

    def test_ext_report_sem_apikey_401(self) -> None:
        r = self._client().post(
            "/api/disparador/ext/campanha/1/report",
            json={"items": [{"telefone": "+5511999999999", "status": "enviado"}]},
        )
        assert r.status_code == 401, r.text


@pytest.mark.docker_demo
class TestDisparoExt:
    @pytest.fixture(scope="class")
    def empresa(self):
        db = get_db_url()
        with psycopg.connect(db, autocommit=True) as conn:
            row = conn.execute(
                "INSERT INTO empresa (nome, slug) VALUES (%s, %s) RETURNING id",
                (f"ext-{_RUN}", f"ext-{_RUN}"),
            ).fetchone()
            assert row is not None
            eid = row[0]
        yield eid
        with psycopg.connect(db, autocommit=True) as conn:
            conn.execute("DELETE FROM empresa WHERE id = %s", (eid,))

    async def test_cria_running_e_report_finaliza(self, empresa) -> None:
        from whatsapp_langchain.shared.campanha import (
            aplicar_report_ext,
            create_campanha,
            get_campanha,
        )
        from whatsapp_langchain.shared.db import get_pool
        from whatsapp_langchain.shared.rls_context import empresa_scope

        pool = await get_pool()
        with empresa_scope(empresa):
            camp = await create_campanha(
                pool,
                empresa,
                nome=f"ext-{_RUN}",
                descricao=None,
                mensagem="oi",
                conexao_id=None,
                intervalo_ms=500,
                max_destinatarios=10_000,
                telefones_brutos=["+5511950000001", "+5511950000002"],
                user_id=None,
                origem_envio="extensao",
            )
        assert camp["status"] == "running"  # browser envia; backend não dispara
        assert camp["origem_envio"] == "extensao"

        # reporta 1 enviado → ainda em running (1 pendente)
        r1 = await aplicar_report_ext(
            pool,
            empresa,
            camp["id"],
            [{"telefone": "+5511950000001", "status": "enviado", "wamid": "X1"}],
        )
        assert r1["enviados"] == 1 and r1["status"] == "running"

        # reporta o 2º como falhou → acabou → partial
        r2 = await aplicar_report_ext(
            pool,
            empresa,
            camp["id"],
            [
                {
                    "telefone": "+5511950000002",
                    "status": "falhou",
                    "erro": "Connection Closed",
                }
            ],
        )
        assert r2["enviados"] == 1 and r2["falhas"] == 1
        assert r2["status"] == "partial"
        final = await get_campanha(pool, empresa, camp["id"])
        assert final["status"] == "partial" and final["finished_at"] is not None


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
        r = await add_destinatarios(
            pool, empresa, cid, ["+5511960000002", "+5511960000003"]
        )
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
            conn.execute("UPDATE campanha SET status='done' WHERE id=%s", (camp["id"],))
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
                [
                    ("+5511970000001", "ouro"),
                    ("+5511970000002", None),
                    ("+5511970000003", None),
                ]
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

    async def test_grava_pausa_periodica(self, empresa) -> None:
        """Pausa longa periódica anti-ban (mig 127): persiste + editável."""
        from whatsapp_langchain.shared.campanha import (
            create_campanha,
            update_campanha,
        )
        from whatsapp_langchain.shared.db import get_pool

        pool = await get_pool()
        out = await create_campanha(
            pool,
            empresa,
            nome=f"campanha-pausa-{_RUN}",
            descricao=None,
            mensagem="Olá",
            conexao_id=None,
            intervalo_ms=500,
            max_destinatarios=1000,
            telefones_brutos=["+5511999990005"],
            user_id=None,
            pausa_a_cada=50,
            pausa_segundos=600,
        )
        assert out["pausa_a_cada"] == 50
        assert out["pausa_segundos"] == 600

        # editável em rascunho
        upd = await update_campanha(
            pool, empresa, out["id"], {"pausa_a_cada": 30, "pausa_segundos": 300}
        )
        assert upd["pausa_a_cada"] == 30
        assert upd["pausa_segundos"] == 300

    async def test_grava_pool_conexoes(self, empresa) -> None:
        """Pool de rotação (mig 130): conexao_ids persiste + conexao_id = 1º."""
        from whatsapp_langchain.shared.campanha import create_campanha
        from whatsapp_langchain.shared.db import get_pool

        # 2 conexões reais (conexao_id tem FK; o 1º do pool vira o conexao_id).
        with psycopg.connect(get_db_url(), autocommit=True) as conn:
            c1 = conn.execute(
                "INSERT INTO conexao (empresa_id, provider, from_number) "
                "VALUES (%s, 'evolution', %s) RETURNING id",
                (empresa, f"+19{_RUN[:6]}a"),
            ).fetchone()[0]
            c2 = conn.execute(
                "INSERT INTO conexao (empresa_id, provider, from_number) "
                "VALUES (%s, 'evolution', %s) RETURNING id",
                (empresa, f"+19{_RUN[:6]}b"),
            ).fetchone()[0]
        pool = await get_pool()
        out = await create_campanha(
            pool,
            empresa,
            nome=f"campanha-pool-{_RUN}",
            descricao=None,
            mensagem="Olá",
            conexao_id=None,
            intervalo_ms=500,
            max_destinatarios=1000,
            telefones_brutos=["+5511999990006"],
            user_id=None,
            conexao_ids=[c1, c2, c1],  # dedup preserva ordem
        )
        assert out["conexao_ids"] == [c1, c2]
        assert out["conexao_id"] == c1  # 1º do pool (compat)


@pytest.mark.docker_demo
class TestTetoDiario:
    """Teto diário por conexão + aquecimento (mig 126).

    Cobre os helpers DB-facing (`quota_status`, `incr_uso_hoje`) e o reagendamento
    pro dia seguinte (`_reagendar_warmup`) sem rodar o `_dispatch_loop` completo
    (que tem sleeps de jitter e gate de sessão — flaky em teste).
    """

    @pytest.fixture(scope="class")
    def empresa_conexao(self):
        db = get_db_url()
        with psycopg.connect(db, autocommit=True) as conn:
            eid = conn.execute(
                "INSERT INTO empresa (nome, slug) VALUES (%s, %s) RETURNING id",
                (f"teto-{_RUN}", f"teto-{_RUN}"),
            ).fetchone()[0]
            cid = conn.execute(
                "INSERT INTO conexao (empresa_id, provider, from_number, "
                "daily_send_cap) VALUES (%s, 'evolution', %s, 5) RETURNING id",
                (eid, f"+1555{_RUN[:7]}"),
            ).fetchone()[0]
        yield eid, cid
        with psycopg.connect(db, autocommit=True) as conn:
            conn.execute("DELETE FROM empresa WHERE id = %s", (eid,))

    async def test_quota_conta_e_incrementa(self, empresa_conexao) -> None:
        eid, cid = empresa_conexao
        from whatsapp_langchain.shared.conexao import get_conexao_by_id
        from whatsapp_langchain.shared.conexao_quota import (
            incr_uso_hoje,
            quota_status,
        )
        from whatsapp_langchain.shared.db import get_pool
        from whatsapp_langchain.shared.rls_context import empresa_scope

        pool = await get_pool()
        with empresa_scope(eid):
            conexao = await get_conexao_by_id(pool, cid)
            assert conexao is not None
            assert conexao.daily_send_cap == 5

            # 1) Nada enviado hoje → cap 5, usados 0, restante 5.
            q = await quota_status(pool, conexao)
            assert q.cap == 5
            assert q.usados == 0
            assert q.restante == 5
            assert q.motivo == "teto manual"

            # 2) Incrementa 3 → restante cai pra 2.
            async with pool.connection() as conn:
                await incr_uso_hoje(conn, eid, cid, 3)
                await conn.commit()
            q2 = await quota_status(pool, conexao)
            assert q2.usados == 3
            assert q2.restante == 2

    async def test_warmup_limita_abaixo_do_manual(self, empresa_conexao) -> None:
        eid, cid = empresa_conexao
        from whatsapp_langchain.shared.conexao import (
            get_conexao_by_id,
            patch_conexao,
        )
        from whatsapp_langchain.shared.conexao_quota import quota_status
        from whatsapp_langchain.shared.db import get_pool
        from whatsapp_langchain.shared.rls_context import empresa_scope

        pool = await get_pool()
        with empresa_scope(eid):
            # Sobe o teto manual pra 500 e liga aquecimento → curva (dia 0 = 20)
            # vira o limite efetivo.
            await patch_conexao(pool, cid, daily_send_cap=500, warmup_enabled=True)
            conexao = await get_conexao_by_id(pool, cid)
            assert conexao is not None
            assert conexao.warmup_started_at is not None
            q = await quota_status(pool, conexao)
            assert q.cap == 20  # WARMUP_BASE, menor que 500
            assert "aquecimento" in (q.motivo or "")

    async def test_reagenda_warmup_vira_scheduled(self, empresa_conexao) -> None:
        eid, cid = empresa_conexao
        from whatsapp_langchain.shared.campanha import (
            _reagendar_warmup,
            create_campanha,
        )
        from whatsapp_langchain.shared.db import get_pool
        from whatsapp_langchain.shared.rls_context import empresa_scope

        pool = await get_pool()
        with empresa_scope(eid):
            out = await create_campanha(
                pool,
                eid,
                nome=f"teto-camp-{_RUN}",
                descricao=None,
                mensagem="Olá",
                conexao_id=cid,
                intervalo_ms=500,
                max_destinatarios=1000,
                telefones_brutos=["+5511970001111", "+5511970002222"],
                user_id=None,
            )
            await _reagendar_warmup(pool, out["id"], 20, "aquecimento (dia 0)")

        with psycopg.connect(get_db_url(), autocommit=True) as conn:
            row = conn.execute(
                "SELECT status, scheduled_at FROM campanha WHERE id = %s",
                (out["id"],),
            ).fetchone()
        assert row[0] == "scheduled", row
        assert row[1] is not None  # reagendada pro dia seguinte
