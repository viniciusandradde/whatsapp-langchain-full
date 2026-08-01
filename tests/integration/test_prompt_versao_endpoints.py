"""Smoke + E2E do histórico de versões do prompt (mig 158).

Smoke (sem DB): valida que as rotas existem e exigem service token.
E2E (com stack rodando): criar agente → editar → restaurar, conferindo que
nada é reescrito e que salvar sem mexer no prompt não polui o histórico.

Para rodar só smoke:
    uv run pytest tests/integration/test_prompt_versao_endpoints.py::TestSmoke -v

Para rodar E2E (precisa make up + migrações aplicadas):
    uv run pytest tests/integration/test_prompt_versao_endpoints.py::TestE2E -v -s
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from .helpers import API_BASE_URL, get_admin_api_headers, get_db_url

# ============================================================================
# Smoke (TestClient — sem DB real, roda em CI)
# ============================================================================


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmoke:
    """Verifica que as rotas estão registradas e exigem auth."""

    def test_list_versoes_sem_auth_401(self) -> None:
        resp = _client().get("/api/v1/agentes/qualquer/prompt/versoes")
        assert resp.status_code == 401

    def test_get_versao_sem_auth_401(self) -> None:
        resp = _client().get("/api/v1/agentes/qualquer/prompt/versoes/1")
        assert resp.status_code == 401

    def test_restaurar_sem_auth_401(self) -> None:
        resp = _client().post("/api/v1/agentes/qualquer/prompt/versoes/1/restaurar")
        assert resp.status_code == 401

    def test_restaurar_exige_permissao(self) -> None:
        """Endpoint que muda o prompt não pode nascer sem `require_permission`.

        A checagem é estrutural (nas dependências da rota) porque um 401 por
        service token faltando passaria mesmo se o RBAC tivesse sido esquecido.
        """
        from whatsapp_langchain.server.main import app

        alvo = [
            r
            for r in app.routes
            if getattr(r, "path", "")
            == "/api/v1/agentes/{slug}/prompt/versoes/{versao}/restaurar"
        ]
        assert alvo, "rota de restaurar não registrada"
        nomes = {
            getattr(d.call, "__qualname__", "")
            for d in alvo[0].dependant.dependencies  # type: ignore[attr-defined]
        }
        assert any("require_permission" in n for n in nomes), nomes
        assert any("require_agente_access" in n for n in nomes), nomes


# ============================================================================
# E2E (stack real — precisa make up)
# ============================================================================


pytestmark_e2e = pytest.mark.docker_demo

_RUN = uuid.uuid4().hex[:8]


@pytest.fixture(scope="module")
def db_url() -> str:
    """Skip se stack não tá rodando."""
    try:
        r = httpx.get(f"{API_BASE_URL}/health", timeout=3)
        if r.status_code != 200:
            pytest.skip("API não saudável. Rode: make up")
    except Exception:
        pytest.skip("API não acessível. Rode: make up")
    url = get_db_url()
    try:
        with psycopg.connect(url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
    except Exception:
        pytest.skip("DB não acessível. Verifique DATABASE_URL")
    return url


def _cria_empresa(db_url: str, sufixo: str) -> int:
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO empresa (nome, slug, plano, status)
                VALUES (%s, %s, 'free', 'active')
                RETURNING id
                """,
                (f"test-promptver-{sufixo}", f"test-promptver-{sufixo}"),
            )
            row = cur.fetchone()
            assert row is not None
            return int(row[0])


def _apaga_empresa(db_url: str, empresa_id: int) -> None:
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM empresa WHERE id = %s", (empresa_id,))


def _cria_admin(db_url: str, empresa_id: int, sufixo: str) -> str:
    """User + membership + perfil Admin com todas as permissões."""
    user_id = f"test-promptver-user-{sufixo}"
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO auth."user" (id, name, email, "emailVerified",
                                         "createdAt", "updatedAt", status,
                                         is_superadmin)
                VALUES (%s, %s, %s, TRUE, NOW(), NOW(), 'active', FALSE)
                """,
                (user_id, f"Autor {sufixo}", f"{user_id}@e2e.test"),
            )
            cur.execute(
                """
                INSERT INTO empresa_membro (empresa_id, user_id, role, is_default)
                VALUES (%s, %s, 'admin', TRUE)
                """,
                (empresa_id, user_id),
            )
            cur.execute(
                """
                INSERT INTO perfil_acesso (empresa_id, nome, descricao, is_system)
                VALUES (%s, 'Admin', 'Acesso total', TRUE)
                ON CONFLICT (empresa_id, nome) DO NOTHING
                RETURNING id
                """,
                (empresa_id,),
            )
            row = cur.fetchone()
            if row is None:
                cur.execute(
                    "SELECT id FROM perfil_acesso "
                    " WHERE empresa_id = %s AND nome = 'Admin'",
                    (empresa_id,),
                )
                row = cur.fetchone()
            assert row is not None
            perfil_id = int(row[0])
            cur.execute(
                """
                INSERT INTO perfil_permissao (perfil_id, permissao_codigo)
                SELECT %s, codigo FROM permissao
                ON CONFLICT DO NOTHING
                """,
                (perfil_id,),
            )
            cur.execute(
                """
                INSERT INTO usuario_perfil (user_id, perfil_id, empresa_id,
                                            assigned_by_user_id)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (user_id, perfil_id, empresa_id, user_id),
            )
    return user_id


def _apaga_user(db_url: str, user_id: str) -> None:
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute('DELETE FROM auth."user" WHERE id = %s', (user_id,))


@pytest.fixture(scope="module")
def empresa_id(db_url: str) -> Iterator[int]:
    eid = _cria_empresa(db_url, _RUN)
    yield eid
    _apaga_empresa(db_url, eid)


@pytest.fixture(scope="module")
def admin_user_id(db_url: str, empresa_id: int) -> Iterator[str]:
    uid = _cria_admin(db_url, empresa_id, _RUN)
    yield uid
    _apaga_user(db_url, uid)


def _headers(user_id: str, empresa_id: int) -> dict[str, str]:
    h = get_admin_api_headers()
    h["X-User-Id"] = user_id
    h["X-Empresa-Id"] = str(empresa_id)
    return h


@pytest.mark.docker_demo
class TestE2E:
    """Fluxo completo: criar → editar → restaurar."""

    SLUG = f"ver-{_RUN}"

    def test_01_criar_agente_ja_nasce_com_versao_1(
        self, admin_user_id: str, empresa_id: int
    ) -> None:
        """Agente novo carrega o prompt da topologia e abre o histórico.

        Antes ele nascia com o campo vazio e respondia com o prompt do módulo
        Python — painel e runtime discordavam.
        """
        h = _headers(admin_user_id, empresa_id)
        r = httpx.post(
            f"{API_BASE_URL}/api/v1/agentes",
            headers=h,
            json={
                "slug": self.SLUG,
                "nome": "Agente de versão",
                "template_catalog": "agente",
            },
            timeout=20,
        )
        assert r.status_code == 201, r.text
        assert (r.json().get("prompt_override") or "").strip(), (
            "agente novo veio com prompt vazio"
        )

        r = httpx.get(
            f"{API_BASE_URL}/api/v1/agentes/{self.SLUG}/prompt/versoes",
            headers=h,
            timeout=20,
        )
        assert r.status_code == 200, r.text
        itens = r.json()["items"]
        assert len(itens) == 1, itens
        assert itens[0]["versao"] == 1
        assert itens[0]["origem"] == "inicial"
        assert itens[0]["caracteres"] > 0
        # a listagem não carrega o texto — ele passa de 30 KB por versão
        assert "texto" not in itens[0]

    def test_02_salvar_outro_campo_nao_cria_versao(
        self, admin_user_id: str, empresa_id: int
    ) -> None:
        h = _headers(admin_user_id, empresa_id)
        r = httpx.put(
            f"{API_BASE_URL}/api/v1/agentes/{self.SLUG}",
            headers=h,
            json={"max_tokens": 4096},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        r = httpx.get(
            f"{API_BASE_URL}/api/v1/agentes/{self.SLUG}/prompt/versoes",
            headers=h,
            timeout=20,
        )
        assert len(r.json()["items"]) == 1, r.text

    def test_03_salvar_texto_identico_nao_cria_versao(
        self, admin_user_id: str, empresa_id: int
    ) -> None:
        h = _headers(admin_user_id, empresa_id)
        r = httpx.get(
            f"{API_BASE_URL}/api/v1/agentes/{self.SLUG}/prompt/versoes/1",
            headers=h,
            timeout=20,
        )
        assert r.status_code == 200, r.text
        texto = r.json()["texto"]
        assert texto

        r = httpx.put(
            f"{API_BASE_URL}/api/v1/agentes/{self.SLUG}",
            headers=h,
            json={"prompt_override": texto},
            timeout=20,
        )
        assert r.status_code == 200, r.text
        r = httpx.get(
            f"{API_BASE_URL}/api/v1/agentes/{self.SLUG}/prompt/versoes",
            headers=h,
            timeout=20,
        )
        assert len(r.json()["items"]) == 1, r.text

    def test_04_editar_prompt_cria_versao_com_nota_e_autor(
        self, admin_user_id: str, empresa_id: int
    ) -> None:
        h = _headers(admin_user_id, empresa_id)
        r = httpx.put(
            f"{API_BASE_URL}/api/v1/agentes/{self.SLUG}",
            headers=h,
            json={
                "prompt_override": "Prompt reescrito pelo teste E2E.",
                "nota": "reescrita completa",
            },
            timeout=20,
        )
        assert r.status_code == 200, r.text

        r = httpx.get(
            f"{API_BASE_URL}/api/v1/agentes/{self.SLUG}/prompt/versoes",
            headers=h,
            timeout=20,
        )
        itens = r.json()["items"]
        assert len(itens) == 2, itens
        topo = itens[0]
        assert topo["versao"] == 2
        assert topo["origem"] == "edicao"
        assert topo["nota"] == "reescrita completa"
        assert topo["criado_por_user_id"] == admin_user_id
        # o nome resolvido é o que a UI mostra na lista
        assert topo["criado_por_nome"] == f"Autor {_RUN}"

    def test_05_nota_nao_vaza_pra_coluna_do_agente(
        self, admin_user_id: str, empresa_id: int
    ) -> None:
        """`nota` viaja no mesmo corpo do PATCH mas não é campo de `agente_ia`."""
        h = _headers(admin_user_id, empresa_id)
        r = httpx.get(
            f"{API_BASE_URL}/api/v1/agentes/{self.SLUG}", headers=h, timeout=20
        )
        assert r.status_code == 200, r.text
        assert "nota" not in r.json()

    def test_06_restaurar_cria_versao_nova_sem_apagar(
        self, admin_user_id: str, empresa_id: int, db_url: str
    ) -> None:
        h = _headers(admin_user_id, empresa_id)
        r = httpx.get(
            f"{API_BASE_URL}/api/v1/agentes/{self.SLUG}/prompt/versoes/1",
            headers=h,
            timeout=20,
        )
        original = r.json()["texto"]

        r = httpx.post(
            f"{API_BASE_URL}/api/v1/agentes/{self.SLUG}/prompt/versoes/1/restaurar",
            headers=h,
            timeout=30,
        )
        assert r.status_code == 200, r.text
        assert r.json()["prompt_override"] == original

        r = httpx.get(
            f"{API_BASE_URL}/api/v1/agentes/{self.SLUG}/prompt/versoes",
            headers=h,
            timeout=20,
        )
        itens = r.json()["items"]
        assert [i["versao"] for i in itens] == [3, 2, 1], itens
        assert itens[0]["origem"] == "restauracao"
        assert itens[0]["restaurada_de"] == 1

        # a versão 2 continua íntegra — restaurar não reescreve a história
        r = httpx.get(
            f"{API_BASE_URL}/api/v1/agentes/{self.SLUG}/prompt/versoes/2",
            headers=h,
            timeout=20,
        )
        assert r.json()["texto"] == "Prompt reescrito pelo teste E2E."

    def test_07_versao_inexistente_404(
        self, admin_user_id: str, empresa_id: int
    ) -> None:
        h = _headers(admin_user_id, empresa_id)
        r = httpx.get(
            f"{API_BASE_URL}/api/v1/agentes/{self.SLUG}/prompt/versoes/999",
            headers=h,
            timeout=20,
        )
        assert r.status_code == 404, r.text
        r = httpx.post(
            f"{API_BASE_URL}/api/v1/agentes/{self.SLUG}/prompt/versoes/999/restaurar",
            headers=h,
            timeout=20,
        )
        assert r.status_code == 404, r.text

    def test_08_agente_inexistente_404(
        self, admin_user_id: str, empresa_id: int
    ) -> None:
        h = _headers(admin_user_id, empresa_id)
        r = httpx.get(
            f"{API_BASE_URL}/api/v1/agentes/nao-existe-{_RUN}/prompt/versoes",
            headers=h,
            timeout=20,
        )
        assert r.status_code == 404, r.text


@pytest.mark.docker_demo
class TestE2EIsolamento:
    """Empresa B não enxerga nem restaura o histórico da empresa A."""

    @pytest.fixture(scope="class")
    def outra(self, db_url: str) -> Iterator[tuple[int, str]]:
        sufixo = f"{_RUN}b"
        eid = _cria_empresa(db_url, sufixo)
        uid = _cria_admin(db_url, eid, sufixo)
        yield eid, uid
        _apaga_user(db_url, uid)
        _apaga_empresa(db_url, eid)

    @pytest.fixture(scope="class")
    def dono_enxerga(self, admin_user_id: str, empresa_id: int) -> None:
        """Sem isto, 404 pro vizinho passaria mesmo se o agente não existisse
        — o teste diria "isolado" quando na verdade não há nada isolado."""
        r = httpx.get(
            f"{API_BASE_URL}/api/v1/agentes/ver-{_RUN}/prompt/versoes",
            headers=_headers(admin_user_id, empresa_id),
            timeout=20,
        )
        if r.status_code != 200 or not r.json()["items"]:
            pytest.skip("agente do TestE2E não está presente — rode a classe toda")

    def test_01_nao_lista_historico_de_outra_empresa(
        self, dono_enxerga: None, outra: tuple[int, str]
    ) -> None:
        outro_eid, outro_uid = outra
        r = httpx.get(
            f"{API_BASE_URL}/api/v1/agentes/ver-{_RUN}/prompt/versoes",
            headers=_headers(outro_uid, outro_eid),
            timeout=20,
        )
        assert r.status_code == 404, r.text

    def test_02_nao_restaura_versao_de_outra_empresa(
        self, dono_enxerga: None, outra: tuple[int, str]
    ) -> None:
        outro_eid, outro_uid = outra
        r = httpx.post(
            f"{API_BASE_URL}/api/v1/agentes/ver-{_RUN}/prompt/versoes/1/restaurar",
            headers=_headers(outro_uid, outro_eid),
            timeout=20,
        )
        assert r.status_code == 404, r.text
