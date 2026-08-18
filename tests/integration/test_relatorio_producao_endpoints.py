"""Smoke + E2E do relatório de produção na gestão da plataforma (mig 173).

O que estas rotas fazem NÃO é gerar o relatório — quem gera é o script no host.
Aqui se lê o que ele publicou e se enfileira "gerar agora". Por isso o E2E
cobre o gate de acesso, a idempotência da fila e a configuração: são as três
coisas que o container decide sozinho.

    uv run pytest tests/integration/test_relatorio_producao_endpoints.py::TestSmoke -v

    DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \
    INTERNAL_SERVICE_TOKEN=dev-token-change-in-production \
    uv run pytest tests/integration/test_relatorio_producao_endpoints.py::TestE2E -v
"""

from __future__ import annotations

import uuid

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from .helpers import API_BASE_URL, get_admin_api_headers, get_db_url

_RUN = uuid.uuid4().hex[:8]


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmoke:
    def test_listar_sem_auth_401(self) -> None:
        assert _client().get("/api/relatorios/producao").status_code == 401

    def test_gerar_sem_auth_401(self) -> None:
        assert _client().post("/api/relatorios/producao/gerar").status_code == 401

    def test_config_sem_auth_401(self) -> None:
        r = _client().put(
            "/api/relatorios/producao/config",
            json={"ativo": True, "horario": "05:00", "tz": "America/Campo_Grande"},
        )
        assert r.status_code == 401


@pytest.mark.docker_demo
class TestE2E:
    @pytest.fixture(scope="class")
    def dados(self):
        """Dois usuários: um superadmin e um comum, para provar o gate."""
        conn = psycopg.connect(get_db_url(), autocommit=True)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO empresa (nome, slug, plano, status) "
            "VALUES (%s, %s, 'free', 'active') RETURNING id",
            (f"E2E RelProd {_RUN}", f"e2e-relprod-{_RUN}"),
        )
        empresa_id = cur.fetchone()[0]

        super_id = f"test-relprod-super-{_RUN}"
        comum_id = f"test-relprod-comum-{_RUN}"
        for uid, is_super in ((super_id, True), (comum_id, False)):
            cur.execute(
                """
                INSERT INTO auth."user" (id, name, email, "emailVerified",
                                          "createdAt", "updatedAt", status,
                                          is_superadmin)
                VALUES (%s, 'Test RelProd', %s, TRUE, NOW(), NOW(), 'active', %s)
                """,
                (uid, f"{uid}@e2e.test", is_super),
            )
        # O usuário comum precisa de membership: sem ela o 403 viria do
        # contexto de empresa, e o teste do gate de superadmin não provaria nada.
        cur.execute(
            "INSERT INTO empresa_membro (empresa_id, user_id, role, is_default) "
            "VALUES (%s, %s, 'admin', TRUE)",
            (empresa_id, comum_id),
        )

        # Um relatório já publicado, como se o host o tivesse gravado.
        cur.execute(
            """
            INSERT INTO relatorio_producao
                (origem, severidade, achados, texto, modelo, dados)
            VALUES ('agendado', 'atencao',
                    '[{"chave":"disco","severidade":"atencao",
                       "titulo":"Disco do host em 81%","evidencia":"81%",
                       "acao":"olhar du -sh"}]'::jsonb,
                    'Texto de exemplo', 'anthropic/claude-sonnet-4.5',
                    '{"disco_pct": 81}'::jsonb)
            RETURNING id
            """
        )
        relatorio_id = cur.fetchone()[0]

        yield {
            "empresa_id": empresa_id,
            "super_id": super_id,
            "comum_id": comum_id,
            "relatorio_id": relatorio_id,
        }

        cur.execute(
            "DELETE FROM relatorio_producao_pedido WHERE solicitado_por IN (%s, %s)",
            (super_id, comum_id),
        )
        cur.execute("DELETE FROM relatorio_producao WHERE id = %s", (relatorio_id,))
        cur.execute("DELETE FROM empresa_membro WHERE empresa_id = %s", (empresa_id,))
        cur.execute("DELETE FROM empresa WHERE id = %s", (empresa_id,))
        cur.execute(
            'DELETE FROM auth."user" WHERE id IN (%s, %s)', (super_id, comum_id)
        )
        conn.close()

    def _h(self, dados: dict, *, como: str) -> dict:
        h = get_admin_api_headers()
        h["X-User-Id"] = dados[como]
        h["X-Empresa-Id"] = str(dados["empresa_id"])
        return h

    def test_1_superadmin_lista_com_config_e_pendente(self, dados) -> None:
        r = httpx.get(
            f"{API_BASE_URL}/api/relatorios/producao",
            headers=self._h(dados, como="super_id"),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert "relatorios" in corpo and "config" in corpo
        # A config é semeada pela migration; sem ela a tela não sabe o horário.
        assert corpo["config"]["horario"]
        ids = [x["id"] for x in corpo["relatorios"]]
        assert dados["relatorio_id"] in ids

    def test_2_usuario_comum_recebe_403(self, dados) -> None:
        # É o teste que prova "só a VSA vê": admin da própria empresa, com
        # membership válida, e ainda assim barrado.
        r = httpx.get(
            f"{API_BASE_URL}/api/relatorios/producao",
            headers=self._h(dados, como="comum_id"),
            timeout=30,
        )
        assert r.status_code == 403, r.text

    def test_3_detalhe_traz_os_dados_crus(self, dados) -> None:
        r = httpx.get(
            f"{API_BASE_URL}/api/relatorios/producao/{dados['relatorio_id']}",
            headers=self._h(dados, como="super_id"),
            timeout=30,
        )
        assert r.status_code == 200, r.text
        # Sem os dados crus não há como conferir a conclusão contra a fonte.
        assert r.json()["dados"] == {"disco_pct": 81}
        assert r.json()["achados"][0]["chave"] == "disco"

    def test_4_gerar_enfileira_com_202(self, dados) -> None:
        r = httpx.post(
            f"{API_BASE_URL}/api/relatorios/producao/gerar",
            headers=self._h(dados, como="super_id"),
            timeout=30,
        )
        # 202: quem produz é o host, no próximo ciclo.
        assert r.status_code == 202, r.text
        assert r.json()["ja_existia"] is False

    def test_5_segundo_pedido_reaproveita_o_pendente(self, dados) -> None:
        # Duplo-clique não pode custar duas coletas e duas chamadas ao modelo.
        r = httpx.post(
            f"{API_BASE_URL}/api/relatorios/producao/gerar",
            headers=self._h(dados, como="super_id"),
            timeout=30,
        )
        assert r.status_code == 202, r.text
        assert r.json()["ja_existia"] is True

    def test_6_usuario_comum_nao_gera(self, dados) -> None:
        r = httpx.post(
            f"{API_BASE_URL}/api/relatorios/producao/gerar",
            headers=self._h(dados, como="comum_id"),
            timeout=30,
        )
        assert r.status_code == 403, r.text

    def test_7_salva_e_le_de_volta_o_horario(self, dados) -> None:
        r = httpx.put(
            f"{API_BASE_URL}/api/relatorios/producao/config",
            headers=self._h(dados, como="super_id"),
            json={"ativo": True, "horario": "06:30", "tz": "America/Sao_Paulo"},
            timeout=30,
        )
        assert r.status_code == 200, r.text
        lido = httpx.get(
            f"{API_BASE_URL}/api/relatorios/producao",
            headers=self._h(dados, como="super_id"),
            timeout=30,
        ).json()["config"]
        assert lido["horario"] == "06:30"
        assert lido["tz"] == "America/Sao_Paulo"
        # Devolve ao default para não deixar o ambiente alterado.
        httpx.put(
            f"{API_BASE_URL}/api/relatorios/producao/config",
            headers=self._h(dados, como="super_id"),
            json={"ativo": True, "horario": "05:00", "tz": "America/Campo_Grande"},
            timeout=30,
        )

    def test_8_horario_invalido_recusado(self, dados) -> None:
        r = httpx.put(
            f"{API_BASE_URL}/api/relatorios/producao/config",
            headers=self._h(dados, como="super_id"),
            json={"ativo": True, "horario": "99:99", "tz": "America/Campo_Grande"},
            timeout=30,
        )
        assert r.status_code == 422, r.text
