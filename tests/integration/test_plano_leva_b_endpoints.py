"""Smoke + E2E da leva B da ADR-005 (mig 190): recursos que custam LLM por
mensagem passam a depender do plano — transcrição para o operador,
documentos/imagem do cliente, few-shot e catálogo completo de modelos.

Smoke (sem DB): as rotas existem e exigem service token.
E2E (stack rodando): empresa Pro e Free com o MESMO admin (padrão da leva A).
No Free: ligar `transcrever_audio_sempre` → 402; botão "Transcrever" → 402;
ligar `fewshot_enabled`/`aceita_documento` no agente → 402 (só a transição
off→on; salvar sem mexer passa); catálogo vem só com curados e
`plano.catalogo_completo=false`. Flag `plano.fewshot` (grandfathering)
libera. No Pro tudo passa e o catálogo traz não-curados.

Rodar E2E contra o dev:
    DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \\
    INTERNAL_SERVICE_TOKEN=dev-token-change-in-production \\
    uv run pytest tests/integration/test_plano_leva_b_endpoints.py -m docker_demo -v
"""

from __future__ import annotations

import uuid

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from .helpers import API_BASE_URL, get_db_url
from .test_plano_leva_a_endpoints import (  # mesmas fixtures/helpers da leva A
    _criar_empresa,
    _dar_perfil_admin,
    _esperar_cache_do_plano,
    _flag,
    _headers,
)


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmoke:
    @pytest.mark.parametrize(
        ("metodo", "caminho"),
        [
            ("PATCH", "/api/conexoes/1"),
            ("POST", "/api/atendimentos/1/mensagens/1/transcrever"),
            ("PUT", "/api/v1/agentes/x"),
            ("GET", "/api/v1/modelos-llm/catalogo"),
        ],
    )
    def test_rotas_gateadas_exigem_auth(self, metodo: str, caminho: str) -> None:
        resp = _client().request(metodo, caminho)
        assert resp.status_code == 401, (caminho, resp.text)


_RUN = uuid.uuid4().hex[:8]


@pytest.fixture(scope="module")
def db_url() -> str:
    try:
        r = httpx.get(f"{API_BASE_URL}/health", timeout=3)
        if r.status_code != 200:
            pytest.skip("API não saudável. Rode: make up")
    except Exception:
        pytest.skip("API não acessível. Rode: make up")
    url = get_db_url()
    try:
        with psycopg.connect(url) as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
    except Exception:
        pytest.skip("DB não acessível. Verifique DATABASE_URL")
    return url


@pytest.fixture(scope="module")
def empresa_id(db_url: str):
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        eid = _criar_empresa(cur, "pro", f"test-leva-b-pro-{_RUN}")
    yield eid
    _apagar_empresa(db_url, eid)


@pytest.fixture(scope="module")
def admin_user_id(db_url: str, empresa_id: int):
    user_id = f"test-leva-b-user-{_RUN}"
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO auth."user" (id, name, email, "emailVerified",
                                      "createdAt", "updatedAt", status, is_superadmin)
            VALUES (%s, 'Test Leva B', %s, TRUE, NOW(), NOW(), 'active', FALSE)
            """,
            (user_id, f"{user_id}@e2e.test"),
        )
        cur.execute(
            "INSERT INTO empresa_membro (empresa_id, user_id, role, is_default) "
            "VALUES (%s, %s, 'admin', TRUE)",
            (empresa_id, user_id),
        )
        _dar_perfil_admin(cur, empresa_id, user_id)
    yield user_id
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute('DELETE FROM auth."user" WHERE id = %s', (user_id,))


@pytest.fixture(scope="module")
def empresa_free_id(db_url: str, admin_user_id: str):
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        eid = _criar_empresa(cur, "free", f"test-leva-b-free-{_RUN}")
        cur.execute(
            "INSERT INTO empresa_membro (empresa_id, user_id, role, is_default) "
            "VALUES (%s, %s, 'admin', FALSE)",
            (eid, admin_user_id),
        )
        _dar_perfil_admin(cur, eid, admin_user_id)
    yield eid
    _apagar_empresa(db_url, eid)


def _apagar_empresa(db_url: str, eid: int) -> None:
    """`message_queue.empresa_id` não é ON DELETE CASCADE: as mensagens de
    áudio semeadas pelo teste saem antes da empresa."""
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("DELETE FROM message_queue WHERE empresa_id = %s", (eid,))
        cur.execute("DELETE FROM empresa WHERE id = %s", (eid,))


def _conexao(db_url: str, empresa_id: int) -> int:
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO conexao (empresa_id, provider, from_number, payload_json)
            VALUES (%s, 'evolution', %s, '{"instance_name": "e2e-leva-b"}')
            RETURNING id
            """,
            (empresa_id, f"+5598{uuid.uuid4().hex[:8]}"),
        )
        row = cur.fetchone()
        assert row is not None
        return int(row[0])


def _atendimento_com_audio(db_url: str, empresa_id: int) -> tuple[int, int]:
    """Atendimento + mensagem de áudio JÁ transcrita (o gate vem antes do
    caminho idempotente — sem LLM)."""
    tel = f"+5567{uuid.uuid4().hex[:8]}"
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO cliente (empresa_id, telefone, nome) VALUES (%s, %s, 'E2E') RETURNING id",
            (empresa_id, tel),
        )
        cliente_id = cur.fetchone()[0]  # type: ignore[index]
        cur.execute(
            "INSERT INTO atendimento (empresa_id, cliente_id, agente_atual, status) "
            "VALUES (%s, %s, 'agente', 'aguardando') RETURNING id",
            (empresa_id, cliente_id),
        )
        atd_id = cur.fetchone()[0]  # type: ignore[index]
        cur.execute(
            """
            INSERT INTO message_queue
                (phone_number, agent_id, thread_id, incoming_message, status,
                 empresa_id, atendimento_id, media_url, media_type, transcricao)
            VALUES (%s, 'agente', %s, '', 'done', %s, %s,
                    'data:audio/ogg;base64,T2dnUw==', 'audio/ogg', 'texto já transcrito')
            RETURNING id
            """,
            (tel, f"{tel}:agente", empresa_id, atd_id),
        )
        msg_id = cur.fetchone()[0]  # type: ignore[index]
    return int(atd_id), int(msg_id)


@pytest.mark.docker_demo
class TestE2E:
    def test_01_free_nao_liga_transcricao_do_operador(
        self, db_url: str, empresa_free_id: int, empresa_id: int, admin_user_id: str
    ) -> None:
        cid = _conexao(db_url, empresa_free_id)
        h = _headers(admin_user_id, empresa_free_id)
        r = httpx.patch(
            f"{API_BASE_URL}/api/conexoes/{cid}",
            headers=h,
            json={"transcrever_audio_sempre": True},
            timeout=15,
        )
        assert r.status_code == 402, r.text
        d = r.json()["detail"]
        assert d["error"] == "feature_unavailable"
        assert d["feature"] == "transcricao_operador"
        assert d["plano_atual"] == "free" and d["upgrade_to"] == "pro"
        assert "não está incluída no seu plano" in d["message"]
        # Desligar (ou não mexer) sempre passa.
        r = httpx.patch(
            f"{API_BASE_URL}/api/conexoes/{cid}",
            headers=h,
            json={"transcrever_audio_sempre": False},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        # Pro liga.
        cid_pro = _conexao(db_url, empresa_id)
        r = httpx.patch(
            f"{API_BASE_URL}/api/conexoes/{cid_pro}",
            headers=_headers(admin_user_id, empresa_id),
            json={"transcrever_audio_sempre": True},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json()["transcrever_audio_sempre"] is True

    def test_02_free_botao_transcrever_402(
        self, db_url: str, empresa_free_id: int, empresa_id: int, admin_user_id: str
    ) -> None:
        atd, msg = _atendimento_com_audio(db_url, empresa_free_id)
        r = httpx.post(
            f"{API_BASE_URL}/api/atendimentos/{atd}/mensagens/{msg}/transcrever",
            headers=_headers(admin_user_id, empresa_free_id),
            timeout=15,
        )
        assert r.status_code == 402, r.text
        assert r.json()["detail"]["feature"] == "transcricao_operador"
        # Pro: caminho idempotente devolve o texto salvo.
        atd, msg = _atendimento_com_audio(db_url, empresa_id)
        r = httpx.post(
            f"{API_BASE_URL}/api/atendimentos/{atd}/mensagens/{msg}/transcrever",
            headers=_headers(admin_user_id, empresa_id),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json()["transcricao"] == "texto já transcrito"

    def test_03_free_nao_liga_fewshot_nem_documentos_no_agente(
        self, db_url: str, empresa_free_id: int, admin_user_id: str
    ) -> None:
        h = _headers(admin_user_id, empresa_free_id)
        slug = f"lb-{_RUN}"
        r = httpx.post(
            f"{API_BASE_URL}/api/v1/agentes",
            headers=h,
            json={"slug": slug, "nome": "Leva B", "template_catalog": "agente"},
            timeout=15,
        )
        assert r.status_code == 201, r.text
        # Agente nasce com aceita_* ligados e few-shot desligado: começa
        # desligando documentos para testar a transição off→on.
        r = httpx.put(
            f"{API_BASE_URL}/api/v1/agentes/{slug}",
            headers=h,
            json={"aceita_documento": False, "aceita_imagem": False},
            timeout=15,
        )
        assert r.status_code == 200, r.text

        for campo, chave in (
            ("fewshot_enabled", "fewshot"),
            ("aceita_documento", "documentos_cliente"),
            ("aceita_imagem", "imagem_cliente"),
        ):
            r = httpx.put(
                f"{API_BASE_URL}/api/v1/agentes/{slug}",
                headers=h,
                json={campo: True},
                timeout=15,
            )
            assert r.status_code == 402, (campo, r.text)
            assert r.json()["detail"]["feature"] == chave

        # Salvar sem mexer nos interruptores continua passando (o editor
        # reenvia todos os campos; só a transição off→on é gateada).
        r = httpx.put(
            f"{API_BASE_URL}/api/v1/agentes/{slug}",
            headers=h,
            json={"nome": "Leva B renomeado", "fewshot_enabled": False},
            timeout=15,
        )
        assert r.status_code == 200, r.text

        # Grandfathering (D3): flag `plano.fewshot` libera a mesma chamada.
        _flag(db_url, empresa_free_id, "fewshot", "true")
        _esperar_cache_do_plano()
        try:
            r = httpx.put(
                f"{API_BASE_URL}/api/v1/agentes/{slug}",
                headers=h,
                json={"fewshot_enabled": True},
                timeout=15,
            )
            assert r.status_code == 200, r.text
            assert r.json()["fewshot_enabled"] is True
        finally:
            _flag(db_url, empresa_free_id, "fewshot", None)

    def test_04_catalogo_free_so_curados_e_pro_completo(
        self, empresa_free_id: int, empresa_id: int, admin_user_id: str
    ) -> None:
        r = httpx.get(
            f"{API_BASE_URL}/api/v1/modelos-llm/catalogo",
            headers=_headers(admin_user_id, empresa_free_id),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["plano"]["catalogo_completo"] is False
        assert corpo["itens"], "sem curados no catálogo — o sync rodou?"
        assert all(i["curado"] for i in corpo["itens"])

        r = httpx.get(
            f"{API_BASE_URL}/api/v1/modelos-llm/catalogo",
            headers=_headers(admin_user_id, empresa_id),
            timeout=15,
        )
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["plano"]["catalogo_completo"] is True
        assert any(not i["curado"] for i in corpo["itens"])
