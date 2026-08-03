"""Smoke + E2E do dataset gold (CSAT local + provedor ativo) e do juiz do eval.

Até 2026-08-03 as duas metades da seção "Dataset & Eval" falhavam **em
silêncio**:

- `POST /dataset/from-langfuse` falava com o Langfuse hardcoded, ignorando o
  provedor escolhido em `/traces`. Com o Langfuse desligado, `list_scores()`
  devolvia `[]` best-effort e a tela dizia "0 novos" — indistinguível de
  "nenhuma conversa qualificou".
- O juiz do eval era `ChatOpenAI(model="gpt-4o-mini")` sem `base_url`, e
  `OPENAI_API_KEY` não existe neste projeto: todo exemplo voltava
  `score: None`, depois de já ter invocado os agentes e gasto OpenRouter.

Só smoke:
    uv run pytest tests/integration/test_dataset_gold.py::TestSmoke -v

E2E (precisa make up + migrações):
    uv run pytest tests/integration/test_dataset_gold.py -v -s
"""

from __future__ import annotations

import uuid

import httpx
import psycopg
import pytest
from fastapi.testclient import TestClient

from .helpers import API_BASE_URL, get_admin_api_headers, get_db_url

# ============================================================================
# Smoke (sem DB real — roda em CI)
# ============================================================================


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmoke:
    def test_rota_gold_exige_auth(self) -> None:
        r = _client().post("/api/admin/rag/dataset/gold", json={"dry_run": True})
        assert r.status_code == 401

    def test_rotas_registradas(self) -> None:
        from whatsapp_langchain.server.main import app

        rotas = {getattr(r, "path", "") for r in app.routes}
        assert "/api/admin/rag/dataset/gold" in rotas
        # A antiga continua no ar — não quebrar chamador existente.
        assert "/api/admin/rag/dataset/from-langfuse" in rotas

    def test_provider_efetivo_saiu_da_rota(self) -> None:
        """Enquanto morava em `routes/traces.py`, nenhum outro módulo conseguia
        reusar — foi por isso que o auto-dataset nasceu hardcoded no Langfuse."""
        from whatsapp_langchain.shared.obs_provider import (
            active_provider,
            langfuse_configurado,
            langsmith_configurado,
            provider_efetivo,
        )

        assert callable(provider_efetivo)
        assert callable(active_provider)
        assert isinstance(langfuse_configurado(), bool)
        assert isinstance(langsmith_configurado(), bool)

    def test_juiz_nao_instancia_chatopenai_direto(self) -> None:
        """A regressão que devolvia `score: None` em todo exemplo.

        `ChatOpenAI(...)` cru vai pra API da OpenAI; aqui só existe OpenRouter.
        Tem que passar por `create_chat_model`.
        """
        import inspect

        from scripts import eval_agentes_menu

        src = inspect.getsource(eval_agentes_menu.evaluate_agentes)
        # Comentários fora: o bloco que explica a regressão cita `ChatOpenAI(`
        # de propósito, e sem isto o teste acusaria a própria documentação.
        codigo = "\n".join(
            linha for linha in src.splitlines() if not linha.strip().startswith("#")
        )
        assert "create_chat_model" in codigo
        assert "ChatOpenAI(" not in codigo
        assert "openai:gpt-4o-mini" not in codigo

    def test_endpoint_pede_openevals_explicitamente(self) -> None:
        """Sem `judge=` explícito o default é o juiz de rubrica próprio — foi
        por isso que a tela nunca usou o openevals, mesmo instalado."""
        import inspect

        from whatsapp_langchain.server.routes import rag_stats

        src = inspect.getsource(rag_stats.run_eval_endpoint)
        assert 'judge="openevals"' in src

    def test_ping_do_langfuse_existe(self) -> None:
        """É o que separa 'fora do ar' de 'nenhum score no período'."""
        from whatsapp_langchain.shared import langfuse_client

        assert callable(langfuse_client.ping)

    def test_openevals_e_dependencia_de_runtime(self) -> None:
        """A regressão mais silenciosa das três.

        `openevals` vivia em `[project.optional-dependencies].dev`, e o
        Dockerfile exporta com `--no-dev` — então ele nunca entrou na imagem.
        O `except ImportError` do eval engolia a ausência e o endpoint devolvia
        `score: None` em todo exemplo, sem erro nenhum. Um endpoint da API
        depende dele: é dependência de runtime.
        """
        import tomllib
        from pathlib import Path

        raiz = Path(__file__).resolve().parents[2]
        cfg = tomllib.loads((raiz / "pyproject.toml").read_text())
        principais = " ".join(cfg["project"]["dependencies"])
        assert "openevals" in principais, (
            "openevals saiu das dependências principais — o eval volta a "
            "devolver score None dentro do container"
        )

    def test_juiz_usa_prompt_do_dominio(self) -> None:
        """O `CORRECTNESS_PROMPT` do pacote avalia correção factual genérica,
        em inglês. Aqui o que importa é se o cliente foi atendido — e a resposta
        do juiz vai pra tela em português."""
        from scripts.eval_agentes_menu import build_openevals_prompt

        prompt = build_openevals_prompt()
        # Contrato de formatação do openevals: sem os três, o judge estoura.
        for campo in ("{inputs}", "{outputs}", "{reference_outputs}"):
            assert campo in prompt, f"placeholder {campo} sumiu do prompt"
        assert "português" in prompt.lower()
        # A régua tem que sair de RUBRIC, e não estar duplicada à mão: mudar a
        # rubrica num lugar precisa valer pros dois juízes.
        from scripts.eval_agentes_menu import RUBRIC

        assert RUBRIC[0][2] in prompt

    def test_scripts_entra_na_imagem_da_api(self) -> None:
        """`run_eval_endpoint` importa `scripts.eval_agentes_menu`; sem o COPY
        o endpoint devolve 500 (`No module named 'scripts'`) — era o estado do
        botão "Rodar eval" em qualquer container."""
        from pathlib import Path

        raiz = Path(__file__).resolve().parents[2]
        dockerfile = (raiz / "Dockerfile.api").read_text()
        assert "COPY scripts/" in dockerfile


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
def cenario(db_url: str):
    """Empresa isolada com duas conversas avaliadas: uma nota 10, outra nota 3.

    A de nota 3 existe pra provar que o corte por `min_score` funciona — sem
    ela, um bug que ignorasse a nota passaria despercebido.
    """
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO empresa (nome, slug, plano, status) "
                "VALUES (%s, %s, 'free', 'active') RETURNING id",
                (f"test-gold-{_RUN}", f"test-gold-{_RUN}"),
            )
            row = cur.fetchone()
            assert row is not None
            eid = int(row[0])

            user_id = f"test-gold-user-{_RUN}"
            cur.execute(
                'INSERT INTO auth."user" (id, name, email, "emailVerified", '
                '"createdAt", "updatedAt", status, is_superadmin) '
                "VALUES (%s, 'Test Gold', %s, TRUE, NOW(), NOW(), 'active', TRUE)",
                (user_id, f"{user_id}@e2e.test"),
            )
            cur.execute(
                "INSERT INTO empresa_membro (empresa_id, user_id, role, is_default) "
                "VALUES (%s, %s, 'admin', TRUE)",
                (eid, user_id),
            )

            cur.execute(
                "INSERT INTO cliente (empresa_id, telefone) "
                "VALUES (%s, %s) RETURNING id",
                (eid, f"+5511{_RUN[:7]}"),
            )
            crow = cur.fetchone()
            assert crow is not None
            cliente_id = int(crow[0])

            # `categoria` segue a régua do NPS clássico (promotor/neutro/detrator)
            criados = []
            for nota, texto, categoria in (
                (10, "otimo", "promotor"),
                (3, "ruim", "detrator"),
            ):
                cur.execute(
                    "INSERT INTO atendimento (empresa_id, cliente_id, status) "
                    "VALUES (%s, %s, 'resolvido') RETURNING id",
                    (eid, cliente_id),
                )
                arow = cur.fetchone()
                assert arow is not None
                atd = int(arow[0])
                cur.execute(
                    """
                    INSERT INTO message_queue
                        (empresa_id, phone_number, agent_id, thread_id,
                         incoming_message, response, atendimento_id, status)
                    VALUES (%s, %s, 'atendimento', %s, %s, %s, %s, 'done')
                    RETURNING id
                    """,
                    (
                        eid,
                        f"+5511{_RUN[:7]}",
                        f"+5511{_RUN[:7]}:atendimento",
                        f"pergunta {texto} {_RUN}",
                        f"resposta {texto} {_RUN}",
                        atd,
                    ),
                )
                mrow = cur.fetchone()
                assert mrow is not None
                cur.execute(
                    "INSERT INTO atendimento_avaliacao "
                    "(atendimento_id, empresa_id, nota, categoria) "
                    "VALUES (%s, %s, %s, %s)",
                    (atd, eid, nota, categoria),
                )
                criados.append((nota, int(mrow[0])))

    yield {"empresa_id": eid, "user_id": user_id, "mensagens": criados}

    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute('DELETE FROM auth."user" WHERE id = %s', (user_id,))
            # `message_queue.empresa_id` não é ON DELETE CASCADE — sem apagar
            # antes, o DELETE da empresa estoura com ForeignKeyViolation e o
            # teardown deixa lixo pra trás.
            cur.execute("DELETE FROM message_queue WHERE empresa_id = %s", (eid,))
            cur.execute("DELETE FROM empresa WHERE id = %s", (eid,))


def _headers(user_id: str, empresa_id: int) -> dict[str, str]:
    h = get_admin_api_headers()
    h["X-User-Id"] = user_id
    h["X-Empresa-Id"] = str(empresa_id)
    return h


@pytest.mark.docker_demo
class TestE2E:
    def test_1_dry_run_nao_escreve(self, db_url: str, cenario: dict) -> None:
        r = httpx.post(
            f"{API_BASE_URL}/api/admin/rag/dataset/gold",
            headers=_headers(cenario["user_id"], cenario["empresa_id"]),
            json={"min_score": 8, "days": 3650, "dry_run": True},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        assert r.json()["novos"] == 1, r.text  # só a nota 10
        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) FROM fewshot_example WHERE empresa_id = %s",
                    (cenario["empresa_id"],),
                )
                row = cur.fetchone()
        assert row is not None and row[0] == 0, "dry_run gravou no banco"

    def test_2_gera_do_csat_e_respeita_nota_minima(
        self, db_url: str, cenario: dict
    ) -> None:
        r = httpx.post(
            f"{API_BASE_URL}/api/admin/rag/dataset/gold",
            headers=_headers(cenario["user_id"], cenario["empresa_id"]),
            json={"min_score": 8, "days": 3650, "dry_run": False},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        assert r.json()["novos"] == 1, r.text
        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT fonte, source_trace_id, csat_nota, status, "
                    "       embedding IS NOT NULL "
                    "FROM fewshot_example WHERE empresa_id = %s",
                    (cenario["empresa_id"],),
                )
                linhas = cur.fetchall()
        assert len(linhas) == 1, f"a conversa nota 3 não podia entrar: {linhas}"
        fonte, trace, nota, status, tem_vetor = linhas[0]
        assert fonte == "csat"
        assert trace.startswith("csat:")
        assert nota == 10
        # Nasce 'pending' e o backfill do endpoint promove pra 'ready' gerando o
        # vetor. Conferir os dois juntos é o que prova o pipeline inteiro: sem
        # vetor o exemplo existe e não serve pra busca por similaridade.
        assert status == "ready", linhas[0]
        assert tem_vetor, "ficou ready sem embedding — o backfill não rodou"

    def test_3_rerun_nao_duplica(self, db_url: str, cenario: dict) -> None:
        """O ponto que o índice único `ux_fewshot_source_trace` protege."""
        r = httpx.post(
            f"{API_BASE_URL}/api/admin/rag/dataset/gold",
            headers=_headers(cenario["user_id"], cenario["empresa_id"]),
            json={"min_score": 8, "days": 3650, "dry_run": False},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        corpo = r.json()
        assert corpo["novos"] == 0, corpo
        assert corpo["skipped"] == 1, corpo
        with psycopg.connect(db_url) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) FROM fewshot_example WHERE empresa_id = %s",
                    (cenario["empresa_id"],),
                )
                row = cur.fetchone()
        assert row is not None and row[0] == 1

    def test_4_avisa_quando_provedor_nao_contribui(self, cenario: dict) -> None:
        """O anti-silêncio: antes, provedor fora e "nada qualificou" davam o
        mesmo zero e a tela mostrava esse zero como se fosse resposta."""
        r = httpx.post(
            f"{API_BASE_URL}/api/admin/rag/dataset/gold",
            headers=_headers(cenario["user_id"], cenario["empresa_id"]),
            json={"min_score": 8, "days": 3650, "dry_run": True},
            timeout=60,
        )
        corpo = r.json()
        assert "avisos" in corpo, corpo
        assert corpo["avisos"], "sem provedor contribuindo, tem que avisar"
        assert "por_fonte" in corpo and "csat" in corpo["por_fonte"], corpo

    def test_5_isolamento(self, db_url: str, cenario: dict) -> None:
        """Membro de outra empresa não gera dataset na empresa alheia."""
        with psycopg.connect(db_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO empresa (nome, slug, plano, status) "
                    "VALUES (%s, %s, 'free', 'active') RETURNING id",
                    (f"test-gold-x-{_RUN}", f"test-gold-x-{_RUN}"),
                )
                row = cur.fetchone()
                assert row is not None
                outra = int(row[0])
                estranho = f"test-gold-x-user-{_RUN}"
                cur.execute(
                    'INSERT INTO auth."user" (id, name, email, "emailVerified", '
                    '"createdAt", "updatedAt", status, is_superadmin) '
                    "VALUES (%s, 'X', %s, TRUE, NOW(), NOW(), 'active', FALSE)",
                    (estranho, f"{estranho}@e2e.test"),
                )
                cur.execute(
                    "INSERT INTO empresa_membro (empresa_id, user_id, role, "
                    "is_default) VALUES (%s, %s, 'admin', TRUE)",
                    (outra, estranho),
                )
        try:
            r = httpx.post(
                f"{API_BASE_URL}/api/admin/rag/dataset/gold",
                headers=_headers(estranho, cenario["empresa_id"]),
                json={"dry_run": True},
                timeout=60,
            )
            assert r.status_code == 403, r.text
        finally:
            with psycopg.connect(db_url, autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute('DELETE FROM auth."user" WHERE id = %s', (estranho,))
                    cur.execute("DELETE FROM empresa WHERE id = %s", (outra,))
