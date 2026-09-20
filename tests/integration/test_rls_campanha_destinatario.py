"""RLS em `campanha_destinatario` (mig 182, F2a).

Era a única tabela do módulo Prospecção fora do isolamento por linha: a
mig 101 varre tabelas COM coluna `empresa_id`, e esta só tinha FK pra
`campanha`. O isolamento dependia inteiramente de o código sempre filtrar
por uma `campanha_id` já validada — invariante correta, mas sem rede.

Estes testes cobrem a rede, não o código: falam com o banco por baixo das
funções, então falham se a policy sair do lugar mesmo que a aplicação
continue filtrando certo.

    DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \
    uv run pytest tests/integration/test_rls_campanha_destinatario.py -v
"""

from __future__ import annotations

import uuid

import psycopg
import pytest

from .helpers import get_db_url

_RUN = uuid.uuid4().hex[:8]


@pytest.mark.docker_demo
class TestRlsCampanhaDestinatario:
    @pytest.fixture(scope="class")
    def duas_empresas(self):
        """Duas empresas, cada uma com campanha e 1 destinatário."""
        db = get_db_url()
        ids = {}
        with psycopg.connect(db, autocommit=True) as conn:
            for lado in ("a", "b"):
                eid = conn.execute(
                    "INSERT INTO empresa (nome, slug, plano) VALUES (%s, %s, 'pro') RETURNING id",
                    (f"rls-{lado}-{_RUN}", f"rls-{lado}-{_RUN}"),
                ).fetchone()[0]
                cid = conn.execute(
                    "INSERT INTO campanha (empresa_id, nome, mensagem, intervalo_ms,"
                    " max_destinatarios, total_destinatarios, status)"
                    " VALUES (%s, %s, 'oi', 500, 100, 1, 'draft') RETURNING id",
                    (eid, f"camp-{lado}-{_RUN}"),
                ).fetchone()[0]
                did = conn.execute(
                    "INSERT INTO campanha_destinatario"
                    " (campanha_id, empresa_id, telefone) VALUES (%s, %s, %s)"
                    " RETURNING id",
                    (cid, eid, f"+55119{lado}{_RUN[:6]}"),
                ).fetchone()[0]
                ids[lado] = {"empresa": eid, "campanha": cid, "dest": did}
        yield ids
        with psycopg.connect(db, autocommit=True) as conn:
            for lado in ("a", "b"):
                conn.execute(
                    "DELETE FROM empresa WHERE id = %s", (ids[lado]["empresa"],)
                )

    def _com_contexto(self, empresa_id: int | None):
        """Conexão COMO A APLICAÇÃO: role `chat_nexus_app` + `app.empresa_id`.

        O `SET ROLE` é o detalhe que faz o teste valer alguma coisa. A
        `DATABASE_URL` dos testes aponta pro `postgres`, que é SUPERUSER — e
        superuser **bypassa RLS mesmo com FORCE** (FORCE só obriga o dono da
        tabela). Sem trocar de role, todos os asserts abaixo passariam com a
        policy desligada.

        `chat_nexus_app` tem `rolbypassrls=false` (mig 100). Em produção o
        runtime já conecta com ele via `DATABASE_URL_APP`; no dev a URL é a
        de superuser, então o RLS fica inerte lá — mais um motivo pra este
        teste forçar o role em vez de confiar no ambiente.
        """
        conn = psycopg.connect(get_db_url(), autocommit=False)
        conn.execute("SET ROLE chat_nexus_app")
        if empresa_id is not None:
            conn.execute(
                "SELECT set_config('app.empresa_id', %s, false)", (str(empresa_id),)
            )
        return conn

    # ---------- a coluna e a policy existem ----------

    def test_1_coluna_e_not_null(self, duas_empresas) -> None:
        with psycopg.connect(get_db_url(), autocommit=True) as conn:
            row = conn.execute(
                "SELECT is_nullable FROM information_schema.columns"
                " WHERE table_name='campanha_destinatario' AND column_name='empresa_id'"
            ).fetchone()
        assert row is not None, "coluna empresa_id não existe"
        assert row[0] == "NO", "empresa_id deveria ser NOT NULL"

    def test_2_rls_ligado_e_forcado(self, duas_empresas) -> None:
        """FORCE importa: sem ele o dono da tabela ignora a policy."""
        with psycopg.connect(get_db_url(), autocommit=True) as conn:
            row = conn.execute(
                "SELECT c.relrowsecurity, c.relforcerowsecurity FROM pg_class c"
                " JOIN pg_namespace n ON n.oid = c.relnamespace"
                " WHERE n.nspname='public' AND c.relname='campanha_destinatario'"
            ).fetchone()
        assert row == (True, True), f"RLS/FORCE não ativos: {row}"

    def test_3_policy_tenant_isolation_existe(self, duas_empresas) -> None:
        with psycopg.connect(get_db_url(), autocommit=True) as conn:
            row = conn.execute(
                "SELECT qual FROM pg_policies WHERE schemaname='public'"
                " AND tablename='campanha_destinatario'"
                " AND policyname='tenant_isolation'"
            ).fetchone()
        assert row is not None, "policy tenant_isolation ausente"
        assert "_rls_tenant_match" in (row[0] or ""), row

    # ---------- o isolamento de verdade ----------

    def test_4_empresa_A_ve_so_o_proprio(self, duas_empresas) -> None:
        a, b = duas_empresas["a"], duas_empresas["b"]
        conn = self._com_contexto(a["empresa"])
        try:
            vistos = {
                r[0]
                for r in conn.execute(
                    "SELECT id FROM campanha_destinatario WHERE id = ANY(%s)",
                    ([a["dest"], b["dest"]],),
                ).fetchall()
            }
        finally:
            conn.close()
        assert a["dest"] in vistos, "empresa A não enxerga o próprio destinatário"
        assert b["dest"] not in vistos, "VAZAMENTO: A enxergou destinatário de B"

    def test_5_empresa_B_nao_apaga_o_de_A(self, duas_empresas) -> None:
        """DELETE cross-tenant não pode achar linha — nem erro, some do escopo."""
        a, b = duas_empresas["a"], duas_empresas["b"]
        conn = self._com_contexto(b["empresa"])
        try:
            cur = conn.execute(
                "DELETE FROM campanha_destinatario WHERE id = %s", (a["dest"],)
            )
            afetadas = cur.rowcount
            conn.commit()
        finally:
            conn.close()
        assert afetadas == 0, "VAZAMENTO: B apagou destinatário de A"

        with psycopg.connect(get_db_url(), autocommit=True) as conn:
            ainda = conn.execute(
                "SELECT count(*) FROM campanha_destinatario WHERE id = %s",
                (a["dest"],),
            ).fetchone()[0]
        assert ainda == 1, "a linha de A sumiu"

    def test_6_insert_cross_tenant_e_recusado(self, duas_empresas) -> None:
        """WITH CHECK: B não grava linha marcada como de A."""
        a, b = duas_empresas["a"], duas_empresas["b"]
        conn = self._com_contexto(b["empresa"])
        try:
            with pytest.raises(psycopg.errors.Error):
                conn.execute(
                    "INSERT INTO campanha_destinatario"
                    " (campanha_id, empresa_id, telefone) VALUES (%s, %s, %s)",
                    (a["campanha"], a["empresa"], f"+5511977{_RUN[:6]}"),
                )
            conn.rollback()
        finally:
            conn.close()

    def test_7_sem_contexto_nao_ve_nada(self, duas_empresas) -> None:
        """Policy é ESTRITA desde a mig 102 — sem contexto, some tudo.

        É o inverso do teste 4 e o motivo de `list_destinatarios` passar a
        exigir `empresa_id`: sem ele a resposta seria uma lista vazia
        indistinguível de "campanha sem ninguém".
        """
        a, b = duas_empresas["a"], duas_empresas["b"]
        conn = self._com_contexto(None)
        try:
            n = conn.execute(
                "SELECT count(*) FROM campanha_destinatario WHERE id = ANY(%s)",
                ([a["dest"], b["dest"]],),
            ).fetchone()[0]
        finally:
            conn.close()
        assert n == 0, f"sem contexto deveria ver 0 linhas, viu {n}"
