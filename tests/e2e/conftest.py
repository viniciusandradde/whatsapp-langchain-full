"""Fixtures compartilhadas para tests/e2e/.

Sprint K — bateria E2E profissional. Reusa helpers de tests/integration/
e adiciona fixtures específicas pra jornadas multi-setor com mídia.
"""

from __future__ import annotations

import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import psycopg
import pytest

from tests.integration.helpers import API_BASE_URL, get_db_url

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"


# Lista de setores cobertos pela bateria. Mantém em sync com:
# - menu_chatbot items (id 4-11 na empresa 1)
# - agente_ia.slug (8 ativos)
# - agente_ia.departamento_default_id (mig 061)
SETORES: list[dict] = [
    {"slug": "atendimento", "opcao": 1, "agente": "atendimento", "depto": 3},
    {
        "slug": "atendimento-cliente",
        "opcao": 2,
        "agente": "atendimento-cliente",
        "depto": None,  # admin não setou — testa fluxo de fallback
    },
    {"slug": "agendamentos", "opcao": 3, "agente": "agendamentos", "depto": 5},
    {"slug": "exames", "opcao": 4, "agente": "exames", "depto": 7},
    {"slug": "orcamento", "opcao": 5, "agente": "orcamento", "depto": 6},
    {"slug": "ouvidoria", "opcao": 6, "agente": "ouvidoria", "depto": 1},
    {
        "slug": "rh-recrutamento-selecao",
        "opcao": 7,
        "agente": "rh-recrutamento-selecao",
        "depto": 4,
    },
    {"slug": "tesouraria", "opcao": 8, "agente": "tesouraria", "depto": 2},
]

MODALIDADES = ["texto", "imagem", "audio", "pdf"]


@pytest.fixture(scope="session")
def db_url() -> str:
    """Valida pré-requisitos da stack e retorna URL do DB."""
    try:
        r = httpx.get(f"{API_BASE_URL}/health", timeout=3)
        if r.status_code != 200:
            pytest.skip("API não saudável — rode `make up`")
    except Exception:
        pytest.skip("API não acessível — rode `make up`")

    url = get_db_url()
    try:
        with psycopg.connect(url) as conn, conn.cursor() as cur:
            cur.execute("SELECT 1")
    except Exception:
        pytest.skip("DB não acessível")
    return url


@pytest.fixture(scope="session")
def media_server_urls():
    """HTTP server local servindo sample.png/ogg/pdf.

    URL hostname configurável via env `MEDIA_SERVER_HOST` (default
    `host.docker.internal` — funciona quando pytest roda no host e workers
    em container). Em prod, container `tests` está na rede Docker → setar
    `MEDIA_SERVER_HOST=tests` pro worker baixar via `http://tests:PORT/...`.
    """
    import os

    for arquivo in ("sample.png", "sample.ogg", "sample.pdf"):
        if not (ASSETS_DIR / arquivo).exists():
            pytest.skip(f"Asset {arquivo} ausente em tests/assets/")

    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:  # noqa: A002
            return

    handler = partial(QuietHandler, directory=str(ASSETS_DIR))
    server = ThreadingHTTPServer(("0.0.0.0", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    host = os.getenv("MEDIA_SERVER_HOST", "host.docker.internal")
    try:
        yield {
            "image_url": f"http://{host}:{port}/sample.png",
            "audio_url": f"http://{host}:{port}/sample.ogg",
            "pdf_url": f"http://{host}:{port}/sample.pdf",
        }
    finally:
        server.shutdown()
        thread.join(timeout=5)


SEED_SQL = Path(__file__).resolve().parent / "fixtures" / "seed.sql"


@pytest.fixture(scope="session", autouse=True)
def seed_test_data(db_url: str):
    """Aplica `tests/e2e/fixtures/seed.sql` antes de qualquer teste.

    Cria empresa+deptos+agentes+menu+items+atendentes idempotentemente
    (ON CONFLICT DO UPDATE/NOTHING). Garante reprodutibilidade local + CI
    sem precisar dump do prod.
    """
    if not SEED_SQL.exists():
        pytest.skip(f"Seed SQL não encontrado: {SEED_SQL}")
    sql = SEED_SQL.read_text(encoding="utf-8")
    try:
        with psycopg.connect(db_url) as conn, conn.cursor() as cur:
            cur.execute(sql)
            conn.commit()
    except Exception as e:
        pytest.fail(f"Seed E2E falhou: {e}")
    yield
