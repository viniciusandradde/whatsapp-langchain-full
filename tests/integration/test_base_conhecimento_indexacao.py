"""Smoke + E2E do `chunks_count` na listagem da base de conhecimento.

`chunks_count` é o que diz se um documento **existe pro agente**. A busca do
RAG é feita em `documento_conhecimento_chunk` com
`d.ativo AND c.embedding IS NOT NULL` — um documento sem chunk vetorizado
aparece na tela, ocupa espaço na pasta e nunca é encontrado. Antes disso a
única forma de descobrir era consultando o banco.

Só smoke:
    uv run pytest tests/integration/test_base_conhecimento_indexacao.py::TestSmoke -v

E2E (precisa make up + migrações):
    uv run pytest tests/integration/test_base_conhecimento_indexacao.py -v -s
"""

from __future__ import annotations

import uuid

import httpx
import psycopg
import pytest

from .helpers import API_BASE_URL, get_admin_api_headers, get_db_url

# ============================================================================
# Smoke (sem DB — roda em CI)
# ============================================================================


class TestSmoke:
    def test_model_expoe_chunks_count(self) -> None:
        from whatsapp_langchain.shared.models import DocumentoConhecimento

        assert "chunks_count" in DocumentoConhecimento.model_fields

    def test_default_zero(self) -> None:
        """Default 0 e não None: os outros seis chamadores de
        `_row_to_documento` não preenchem o campo, e `0` mantém o tipo
        estável pro frontend (que compara com `=== 0`)."""
        from whatsapp_langchain.shared.models import DocumentoConhecimento

        assert DocumentoConhecimento.model_fields["chunks_count"].default == 0

    def test_listagem_conta_apenas_chunk_com_vetor(self) -> None:
        """A contagem tem que filtrar `embedding IS NOT NULL`.

        Chunk sem vetor não entra na busca — contá-lo faria um documento
        invisível parecer indexado, que é exatamente o engano que este campo
        existe pra desfazer.
        """
        import inspect

        from whatsapp_langchain.shared import base_conhecimento

        src = inspect.getsource(base_conhecimento.list_documentos)
        assert "documento_conhecimento_chunk" in src
        assert "embedding IS NOT NULL" in src


# ============================================================================
# E2E (stack real)
# ============================================================================

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
        with psycopg.connect(url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
    except Exception:
        pytest.skip("DB não acessível.")
    return url


@pytest.fixture(scope="module")
def empresa_id(db_url: str):
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO empresa (nome, slug, plano, status)
                VALUES (%s, %s, 'free', 'active') RETURNING id
                """,
                (f"test-kb-{_RUN}", f"test-kb-{_RUN}"),
            )
            row = cur.fetchone()
            assert row is not None
            eid = int(row[0])
    yield eid
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM empresa WHERE id = %s", (eid,))


@pytest.fixture(scope="module")
def admin_user_id(db_url: str, empresa_id: int):
    user_id = f"test-kb-user-{_RUN}"
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO auth."user" (id, name, email, "emailVerified",
                                          "createdAt", "updatedAt", status,
                                          is_superadmin)
                VALUES (%s, 'Test KB', %s, TRUE, NOW(), NOW(), 'active', TRUE)
                """,
                (user_id, f"{user_id}@e2e.test"),
            )
            cur.execute(
                """
                INSERT INTO empresa_membro (empresa_id, user_id, role, is_default)
                VALUES (%s, %s, 'admin', TRUE)
                """,
                (empresa_id, user_id),
            )
    yield user_id
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute('DELETE FROM auth."user" WHERE id = %s', (user_id,))


def _headers(user_id: str, empresa_id: int) -> dict[str, str]:
    h = get_admin_api_headers()
    h["X-User-Id"] = user_id
    h["X-Empresa-Id"] = str(empresa_id)
    return h


@pytest.mark.docker_demo
class TestE2E:
    def test_documento_sem_chunk_vem_com_zero(
        self, db_url: str, empresa_id: int, admin_user_id: str
    ) -> None:
        """O caso que a tela precisa flagrar: cadastrado e invisível."""
        with psycopg.connect(db_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO documento_conhecimento
                        (empresa_id, titulo, conteudo, tags, ativo)
                    VALUES (%s, %s, 'conteudo sem indexacao', ARRAY['e2e'], TRUE)
                    RETURNING id
                    """,
                    (empresa_id, f"sem-chunk-{_RUN}"),
                )
                row = cur.fetchone()
                assert row is not None
                doc_id = int(row[0])

        r = httpx.get(
            f"{API_BASE_URL}/api/base-conhecimento",
            headers=_headers(admin_user_id, empresa_id),
            timeout=20,
        )
        assert r.status_code == 200, r.text
        alvo = [d for d in r.json()["documentos"] if d["id"] == doc_id]
        assert alvo, f"documento {doc_id} não veio na listagem: {r.text}"
        assert alvo[0]["chunks_count"] == 0, alvo[0]

    def test_chunk_sem_vetor_nao_conta(
        self, db_url: str, empresa_id: int, admin_user_id: str
    ) -> None:
        """Chunk existe mas `embedding` é NULL — a busca ignora, a contagem
        também tem que ignorar. Contar aqui faria um documento invisível
        aparecer como indexado."""
        with psycopg.connect(db_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO documento_conhecimento
                        (empresa_id, titulo, conteudo, tags, ativo)
                    VALUES (%s, %s, 'tem chunk mas sem vetor', ARRAY['e2e'], TRUE)
                    RETURNING id
                    """,
                    (empresa_id, f"chunk-sem-vetor-{_RUN}"),
                )
                row = cur.fetchone()
                assert row is not None
                doc_id = int(row[0])
                cur.execute(
                    """
                    INSERT INTO documento_conhecimento_chunk
                        (empresa_id, documento_id, chunk_idx, conteudo, embedding)
                    VALUES (%s, %s, 0, 'pedaco sem vetor', NULL)
                    """,
                    (empresa_id, doc_id),
                )

        r = httpx.get(
            f"{API_BASE_URL}/api/base-conhecimento",
            headers=_headers(admin_user_id, empresa_id),
            timeout=20,
        )
        assert r.status_code == 200, r.text
        alvo = [d for d in r.json()["documentos"] if d["id"] == doc_id][0]
        assert alvo["chunks_count"] == 0, (
            "chunk sem embedding foi contado — documento invisível pro agente "
            f"apareceria como indexado: {alvo}"
        )
