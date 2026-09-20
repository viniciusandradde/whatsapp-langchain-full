"""Teto de gasto de IA: precisão do consumo e herança de configuração no mês novo.

Dois defeitos que se escondiam um no outro:

1. `consumo_usd` era `NUMERIC(10,2)`. O débito é um UPSERT que soma
   `EXCLUDED.consumo_usd`, e o EXCLUDED já chega convertido pro tipo da
   coluna — com uma chamada de LLM custando ~0.0014 USD, o incremento virava
   `0.00` antes da soma. O consumo nunca saía do lugar. Antes, com modelos a
   ~0.005/chamada, o efeito era o inverso: arredondava pra cima, a 0.01, e o
   valor gravado virava a contagem de chamadas dividida por 100.

2. A linha do mês nascia do próprio débito, com `limite_usd` zero fixo no
   INSERT, e nada copiava a configuração do mês anterior. Todo dia primeiro o
   teto de toda empresa voltava a zero — e como `get_budget_atual` trata
   limite zero como "sem teto", o estado nascido do defeito ficava
   indistinguível de "nunca configurado".

Só smoke:
    uv run pytest tests/integration/test_ia_budget.py::TestSmoke -v

E2E (precisa make up + migrações):
    uv run pytest tests/integration/test_ia_budget.py -v -s
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

import psycopg
import pytest
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.governanca_ia import acrescentar_consumo

from .helpers import get_db_url

# ============================================================================
# Smoke (sem DB — roda em CI)
# ============================================================================

_MIGRACAO = (
    Path(__file__).parents[2] / "db" / "migrations" / "161_ia_budget_precisao.sql"
)


class TestSmoke:
    def test_migracao_amplia_a_precisao(self) -> None:
        """Duas casas decimais não representam o custo de uma chamada.

        A escala tem que ser a mesma de `ia_execucao.custo_total` — escolher
        outra é o que criou o defeito.
        """
        assert _MIGRACAO.exists(), f"migração ausente: {_MIGRACAO.name}"
        sql = _MIGRACAO.read_text()
        assert "consumo_usd TYPE NUMERIC(14,8)" in sql

    def test_migracao_recalcula_a_partir_de_ia_execucao(self) -> None:
        """O valor histórico é irrecuperável de si mesmo: precisa vir da
        fonte. `llm_callback` grava a execução e debita no mesmo ponto, com o
        mesmo valor, então `ia_execucao` reconstrói o consumo."""
        sql = _MIGRACAO.read_text()
        assert "ia_execucao" in sql
        assert "custo_total" in sql

    def test_debito_nao_fixa_limite_zero(self) -> None:
        """O INSERT do débito é o que cria a linha do mês. Se ele fixar
        limite zero, o teto some todo dia primeiro."""
        import inspect

        src = inspect.getsource(acrescentar_consumo)
        assert "VALUES (%s, %s, 0, %s)" not in src, (
            "limite zero fixo no INSERT — o mês novo nasce sem teto"
        )

    def test_debito_busca_o_mes_anterior(self) -> None:
        import inspect

        src = inspect.getsource(acrescentar_consumo)
        assert "ano_mes <" in src, "nada procura a configuração do mês anterior"


# ============================================================================
# E2E (stack real)
# ============================================================================

_RUN = uuid.uuid4().hex[:8]


def _meses() -> tuple[str, str]:
    """(mês atual, mês anterior) no mesmo formato que o débito usa.

    App e banco rodam em UTC, então `datetime.now()` aqui e o `to_char` da
    migração caem no mesmo mês.
    """
    hoje = datetime.now()
    anterior = hoje.replace(day=1) - timedelta(days=1)
    return hoje.strftime("%Y-%m"), anterior.strftime("%Y-%m")


@pytest.fixture(scope="module")
def db_url() -> str:
    url = get_db_url()
    try:
        with psycopg.connect(url) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
    except Exception:
        pytest.skip("DB não acessível. Rode: make db")
    return url


@pytest.fixture
def empresa_id(db_url: str):
    """Empresa por teste: `ia_budget` é única por (empresa, mês), então
    compartilhar empresa faria um teste enxergar a linha do anterior.

    Enterprise (teto de IA US$ 500): os testes de herança usam limites de
    10–50, abaixo do teto — o teto do plano (ADR-005 D4) tem testes próprios
    com uma empresa Free (teto US$ 5)."""
    slug = f"test-budget-{_RUN}-{uuid.uuid4().hex[:6]}"
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO empresa (nome, slug, plano, status)
                VALUES (%s, %s, 'enterprise', 'active') RETURNING id
                """,
                (slug, slug),
            )
            row = cur.fetchone()
            assert row is not None
            eid = int(row[0])
    yield eid
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM empresa WHERE id = %s", (eid,))


def _budget(db_url: str, empresa_id: int, ano_mes: str) -> tuple | None:
    with psycopg.connect(db_url, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT limite_usd, consumo_usd, acao_estouro, alerta_pct
                  FROM ia_budget WHERE empresa_id = %s AND ano_mes = %s
                """,
                (empresa_id, ano_mes),
            )
            return cur.fetchone()


@pytest.mark.docker_demo
class TestE2E:
    async def test_acumulador_tem_a_escala_da_origem(self, db_url: str) -> None:
        """O acumulador não pode ser mais grosso que o valor que ele soma.

        Foi essa divergência — `custo_total` com 8 casas somando dentro de um
        `consumo_usd` de 2 — que zerou o teto.
        """
        with psycopg.connect(db_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT table_name, numeric_scale
                      FROM information_schema.columns
                     WHERE (table_name = 'ia_budget' AND column_name = 'consumo_usd')
                        OR (table_name = 'ia_execucao' AND column_name = 'custo_total')
                    """
                )
                escalas = dict(cur.fetchall())
        assert escalas["ia_budget"] >= escalas["ia_execucao"], (
            f"acumulador com escala {escalas['ia_budget']} soma valores de "
            f"escala {escalas['ia_execucao']} — o incremento some no caminho"
        )

    async def test_consumo_acumula_valores_sub_centavo(
        self, db_url: str, empresa_id: int
    ) -> None:
        """O caso real: 10 chamadas de gemini-3.1-flash-lite.

        Com `NUMERIC(10,2)` cada incremento virava 0.00 e o total ficava em
        zero, que é como o teto de agosto ficou cego em produção.
        """
        atual, _ = _meses()
        async with AsyncConnectionPool(db_url, min_size=1, max_size=2) as pool:
            for _ in range(10):
                await acrescentar_consumo(pool, empresa_id, 0.0014)

        row = _budget(db_url, empresa_id, atual)
        assert row is not None, "nenhuma linha criada pelo débito"
        assert row[1] == pytest.approx(Decimal("0.014"), abs=Decimal("0.0001"))

    async def test_mes_novo_herda_configuracao_do_anterior(
        self, db_url: str, empresa_id: int
    ) -> None:
        atual, anterior = _meses()
        with psycopg.connect(db_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ia_budget
                        (empresa_id, ano_mes, limite_usd, consumo_usd,
                         acao_estouro, alerta_pct)
                    VALUES (%s, %s, 35.00, 12.00, 'bloquear', 90)
                    """,
                    (empresa_id, anterior),
                )

        async with AsyncConnectionPool(db_url, min_size=1, max_size=2) as pool:
            await acrescentar_consumo(pool, empresa_id, 0.0014)

        row = _budget(db_url, empresa_id, atual)
        assert row is not None
        assert row[0] == Decimal("35.00"), "o teto do mês anterior não veio junto"
        assert row[2] == "bloquear"
        assert row[3] == 90
        assert row[1] == pytest.approx(Decimal("0.0014"), abs=Decimal("0.0001")), (
            "o consumo tem que começar do zero no mês novo, não herdar"
        )

    async def test_sem_mes_anterior_nasce_com_o_teto_do_plano(
        self, db_url: str, empresa_id: int
    ) -> None:
        """ADR-005 D4: sem linha anterior o mês nasce com o teto do plano
        (Enterprise = 500), não mais com 0 = "sem teto"."""
        atual, _ = _meses()
        async with AsyncConnectionPool(db_url, min_size=1, max_size=2) as pool:
            await acrescentar_consumo(pool, empresa_id, 0.0014)

        row = _budget(db_url, empresa_id, atual)
        assert row is not None
        assert row[0] == Decimal("500.00")
        assert row[2] == "alertar"
        assert row[3] == 80

    async def test_teto_do_plano_limita_a_heranca(self, db_url: str) -> None:
        """ADR-005 D4: `LEAST(limite anterior, teto do plano)` — a empresa
        Free (teto US$ 5) que tinha 35 no mês anterior nasce com 5."""
        atual, anterior = _meses()
        slug = f"test-budget-free-{_RUN}-{uuid.uuid4().hex[:6]}"
        with psycopg.connect(db_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO empresa (nome, slug, plano, status) "
                    "VALUES (%s, %s, 'free', 'active') RETURNING id",
                    (slug, slug),
                )
                row = cur.fetchone()
                assert row is not None
                eid = int(row[0])
                cur.execute(
                    """
                    INSERT INTO ia_budget
                        (empresa_id, ano_mes, limite_usd, acao_estouro, alerta_pct)
                    VALUES (%s, %s, 35.00, 'bloquear', 90)
                    """,
                    (eid, anterior),
                )
        try:
            async with AsyncConnectionPool(db_url, min_size=1, max_size=2) as pool:
                await acrescentar_consumo(pool, eid, 0.0014)
            row = _budget(db_url, eid, atual)
            assert row is not None
            assert row[0] == Decimal("5.00"), "o teto do plano não limitou a herança"
            assert row[2] == "bloquear" and row[3] == 90  # o resto herda igual
        finally:
            with psycopg.connect(db_url, autocommit=True) as conn:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM empresa WHERE id = %s", (eid,))

    async def test_debito_nao_sobrescreve_limite_ja_configurado(
        self, db_url: str, empresa_id: int
    ) -> None:
        """A herança vale só no nascimento da linha. Se o dono já configurou
        o mês corrente, o débito não pode desfazer."""
        atual, anterior = _meses()
        with psycopg.connect(db_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ia_budget
                        (empresa_id, ano_mes, limite_usd, acao_estouro, alerta_pct)
                    VALUES (%s, %s, 35.00, 'bloquear', 90), (%s, %s, 50.00, 'alertar', 70)
                    """,
                    (empresa_id, anterior, empresa_id, atual),
                )

        async with AsyncConnectionPool(db_url, min_size=1, max_size=2) as pool:
            await acrescentar_consumo(pool, empresa_id, 0.0014)

        row = _budget(db_url, empresa_id, atual)
        assert row is not None
        assert row[0] == Decimal("50.00"), "o débito sobrescreveu o teto do mês"
        assert row[2] == "alertar"
        assert row[3] == 70

    async def test_herda_do_mes_mais_recente_e_nao_do_mais_antigo(
        self, db_url: str, empresa_id: int
    ) -> None:
        """`ano_mes` é CHAR(7) 'YYYY-MM': a ordem lexicográfica é a
        cronológica, mas só se a busca ordenar de verdade."""
        atual, anterior = _meses()
        antigo = (
            datetime.strptime(anterior + "-01", "%Y-%m-%d").replace(day=1)
            - timedelta(days=1)
        ).strftime("%Y-%m")
        with psycopg.connect(db_url, autocommit=True) as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ia_budget
                        (empresa_id, ano_mes, limite_usd, acao_estouro, alerta_pct)
                    VALUES (%s, %s, 10.00, 'alertar', 50), (%s, %s, 35.00, 'bloquear', 90)
                    """,
                    (empresa_id, antigo, empresa_id, anterior),
                )

        async with AsyncConnectionPool(db_url, min_size=1, max_size=2) as pool:
            await acrescentar_consumo(pool, empresa_id, 0.0014)

        row = _budget(db_url, empresa_id, atual)
        assert row is not None
        assert row[0] == Decimal("35.00"), "herdou de um mês mais antigo"
