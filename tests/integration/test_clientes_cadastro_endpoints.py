"""Smoke + E2E do cadastro manual de clientes, CSV e classificação (mig 201).

Smoke (sem DB): as rotas novas existem e exigem service token.
E2E (stack real): criar → 409 no repetido → classificar → filtrar →
importar CSV → exportar; permissões (sem `cliente.write` → 403) e
isolamento entre empresas.

    uv run pytest tests/integration/test_clientes_cadastro_endpoints.py::TestSmoke -v
    DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \\
    INTERNAL_SERVICE_TOKEN=dev-token-change-in-production \\
    uv run pytest tests/integration/test_clientes_cadastro_endpoints.py -m docker_demo -v
"""

from __future__ import annotations

import uuid

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from .helpers import API_BASE_URL, get_admin_api_headers, get_db_url


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmoke:
    def test_criar_sem_auth_401(self) -> None:
        assert (
            _client().post("/api/clientes", json={"telefone": "x"}).status_code == 401
        )

    def test_importar_sem_auth_401(self) -> None:
        r = _client().post("/api/clientes/importar", files={"arquivo": ("a.csv", b"x")})
        assert r.status_code == 401

    def test_exportar_sem_auth_401(self) -> None:
        assert _client().get("/api/clientes/exportar").status_code == 401

    def test_classificar_sem_auth_401(self) -> None:
        r = _client().put("/api/clientes/1/classificacao", json={})
        assert r.status_code == 401


# ============================================================================
# E2E
# ============================================================================

_RUN = uuid.uuid4().hex[:8]
# Telefones deste run: DDD 67 + 9 + 8 dígitos derivados do run (válidos).
_DIG = str(int(_RUN, 16))[-8:].rjust(8, "1")
TEL_A = f"+55679{_DIG}"
TEL_B = f"+55679{_DIG[::-1]}"
TEL_C = f"+55689{_DIG}"


@pytest.fixture(scope="module")
def db_url() -> str:
    try:
        r = httpx.get(f"{API_BASE_URL}/health", timeout=3)
        if r.status_code != 200:
            pytest.skip("API não saudável. Rode: make up")
    except Exception:
        pytest.skip("API não acessível. Rode: make up")
    return get_db_url()


def _criar_empresa(db_url: str, sufixo: str) -> int:
    with psycopg.connect(db_url, autocommit=True) as conn:
        row = conn.execute(
            "INSERT INTO empresa (nome, slug, plano, status) VALUES (%s, %s, 'pro', 'active') RETURNING id",
            (f"test-cli-{sufixo}-{_RUN}", f"test-cli-{sufixo}-{_RUN}"),
        ).fetchone()
    assert row is not None
    return int(row[0])


def _criar_usuario(
    db_url: str, empresa_id: int, nome: str, perms: list[str] | None
) -> str:
    """User + membro + perfil próprio com `perms` (None = catálogo inteiro)."""
    user_id = f"test-cli-{nome}-{_RUN}"
    with psycopg.connect(db_url, autocommit=True) as conn:
        conn.execute(
            """
            INSERT INTO auth."user" (id, name, email, "emailVerified", "createdAt",
                                     "updatedAt", status, is_superadmin)
            VALUES (%s, %s, %s, TRUE, NOW(), NOW(), 'active', FALSE)
            """,
            (user_id, nome, f"{user_id}@e2e.test"),
        )
        conn.execute(
            "INSERT INTO empresa_membro (empresa_id, user_id, role, is_default) VALUES (%s, %s, 'operator', TRUE)",
            (empresa_id, user_id),
        )
        row = conn.execute(
            "INSERT INTO perfil_acesso (empresa_id, nome, descricao, is_system) VALUES (%s, %s, 'e2e', FALSE) RETURNING id",
            (empresa_id, f"perfil-{nome}"),
        ).fetchone()
        assert row is not None
        perfil_id = int(row[0])
        if perms is None:
            conn.execute(
                "INSERT INTO perfil_permissao (perfil_id, permissao_codigo) SELECT %s, codigo FROM permissao",
                (perfil_id,),
            )
        else:
            for p in perms:
                conn.execute(
                    "INSERT INTO perfil_permissao (perfil_id, permissao_codigo) VALUES (%s, %s)",
                    (perfil_id, p),
                )
        conn.execute(
            "INSERT INTO usuario_perfil (user_id, perfil_id, empresa_id, assigned_by_user_id) VALUES (%s, %s, %s, %s)",
            (user_id, perfil_id, empresa_id, user_id),
        )
    return user_id


@pytest.fixture(scope="module")
def ctx(db_url: str):
    empresa_a = _criar_empresa(db_url, "a")
    empresa_b = _criar_empresa(db_url, "b")
    gestor = _criar_usuario(
        db_url, empresa_a, "gestor", ["cliente.read.all", "cliente.write.all"]
    )
    leitor = _criar_usuario(db_url, empresa_a, "leitor", ["cliente.read.all"])
    admin_b = _criar_usuario(db_url, empresa_b, "adminb", None)
    yield {
        "a": empresa_a,
        "b": empresa_b,
        "gestor": gestor,
        "leitor": leitor,
        "admin_b": admin_b,
    }
    with psycopg.connect(db_url, autocommit=True) as conn:
        for uid in (gestor, leitor, admin_b):
            conn.execute('DELETE FROM auth."user" WHERE id = %s', (uid,))
        conn.execute(
            "DELETE FROM empresa WHERE id = ANY(%s)", ([empresa_a, empresa_b],)
        )


def _h(user_id: str, empresa_id: int) -> dict[str, str]:
    h = get_admin_api_headers()
    h["X-User-Id"] = user_id
    h["X-Empresa-Id"] = str(empresa_id)
    return h


@pytest.mark.docker_demo
class TestE2E:
    def test_fluxo_completo(self, ctx, db_url: str) -> None:
        base = f"{API_BASE_URL}/api/clientes"
        h = _h(ctx["gestor"], ctx["a"])

        # 1. cria com telefone formatado → normalizado em E.164
        r = httpx.post(
            base,
            headers=h,
            json={
                "telefone": f"(67) 9{_DIG[:4]}-{_DIG[4:]}",
                "nome": "Ana E2E",
                "email": "ana@e2e.test",
                "source": "Feira",
                "lifecycle_stage": "mql",
                "temperatura": "morno",
            },
        )
        assert r.status_code == 201, r.text
        ana = r.json()
        assert ana["telefone"] == TEL_A
        assert (ana["lifecycle_stage"], ana["temperatura"]) == ("mql", "morno")
        assert ana["classificacao_origem"] == "manual"

        # 2. mesmo número → 409 com o id existente
        r = httpx.post(base, headers=h, json={"telefone": TEL_A})
        assert r.status_code == 409, r.text
        assert r.json()["detail"]["cliente_id"] == ana["id"]

        # 3. telefone sem DDD → 422
        r = httpx.post(base, headers=h, json={"telefone": "+55996460034"})
        assert r.status_code == 422, r.text

        # 4. IA sugere (simulada no banco) e o operador confirma → manual
        with psycopg.connect(db_url, autocommit=True) as conn:
            conn.execute(
                "UPDATE cliente SET classificacao_origem = 'ia', temperatura = 'quente' WHERE id = %s",
                (ana["id"],),
            )
        r = httpx.put(
            f"{base}/{ana['id']}/classificacao",
            headers=h,
            json={"lifecycle_stage": "sql", "temperatura": "quente", "score": 70},
        )
        assert r.status_code == 200, r.text
        assert r.json()["classificacao_origem"] == "manual"
        assert r.json()["score"] == 70

        # 5. estágio fora do funil → 422
        r = httpx.put(
            f"{base}/{ana['id']}/classificacao",
            headers=h,
            json={"lifecycle_stage": "qualified"},
        )
        assert r.status_code == 422

        # 6. importar CSV: 1 novo, 1 já existia, 1 inválido
        csv = f"nome;telefone;email\nBia;{TEL_B};\nAna de novo;{TEL_A};\nCaio;123;\n".encode()
        r = httpx.post(
            f"{base}/importar",
            headers=h,
            files={"arquivo": ("clientes.csv", csv, "text/csv")},
        )
        assert r.status_code == 200, r.text
        out = r.json()
        assert (out["criados"], out["ja_existiam"]) == (1, 1)
        assert [i["linha"] for i in out["invalidos"]] == [4]

        # 7. filtros da listagem
        r = httpx.get(
            base, headers=h, params={"lifecycle_stage": "sql", "temperatura": "quente"}
        )
        assert r.status_code == 200, r.text
        assert [c["id"] for c in r.json()["clientes"]] == [ana["id"]]
        r = httpx.get(base, headers=h, params={"search": "e2e.test"})
        assert [c["id"] for c in r.json()["clientes"]] == [ana["id"]]

        # 8. exportar com o filtro
        r = httpx.get(f"{base}/exportar", headers=h, params={"temperatura": "quente"})
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("text/csv")
        linhas = r.content.decode("utf-8-sig").splitlines()
        assert linhas[0].startswith("nome;telefone;email")
        assert len(linhas) == 2
        assert "Ana E2E" in linhas[1] and "Lead qualificado (vendas)" in linhas[1]

    def test_sem_permissao_de_escrita(self, ctx) -> None:
        h = _h(ctx["leitor"], ctx["a"])
        base = f"{API_BASE_URL}/api/clientes"
        assert httpx.get(base, headers=h).status_code == 200
        r = httpx.post(base, headers=h, json={"telefone": TEL_C})
        assert r.status_code == 403, r.text
        r = httpx.post(
            f"{base}/importar",
            headers=h,
            files={"arquivo": ("a.csv", f"telefone\n{TEL_C}\n".encode())},
        )
        assert r.status_code == 403, r.text

    def test_isolamento_entre_empresas(self, ctx) -> None:
        base = f"{API_BASE_URL}/api/clientes"
        r = httpx.get(
            base, headers=_h(ctx["gestor"], ctx["a"]), params={"search": TEL_A[3:]}
        )
        cid = r.json()["clientes"][0]["id"]
        hb = _h(ctx["admin_b"], ctx["b"])
        assert httpx.get(f"{base}/{cid}", headers=hb).status_code in (403, 404)
        r = httpx.put(
            f"{base}/{cid}/classificacao", headers=hb, json={"temperatura": "frio"}
        )
        assert r.status_code in (403, 404)
        # empresa B cadastra o MESMO número: é outro cliente, na empresa dela
        r = httpx.post(base, headers=hb, json={"telefone": TEL_A})
        assert r.status_code == 201, r.text
        assert r.json()["id"] != cid
        linhas = (
            httpx.get(f"{base}/exportar", headers=hb)
            .content.decode("utf-8-sig")
            .splitlines()
        )
        assert len(linhas) == 2  # só o dela
