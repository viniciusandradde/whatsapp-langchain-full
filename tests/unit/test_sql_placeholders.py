"""Guarda contra `%` solto em SQL — quebra em runtime, não no import.

Incidente 2026-07-26: o dashboard de IA passou a devolver 500 em produção logo
após um deploy. Causa: um COMENTÁRIO SQL que eu escrevi continha "+91%", e o
psycopg varre placeholders no texto INTEIRO da query — comentário incluso.
Resultado:

    psycopg.ProgrammingError: incomplete placeholder: '%'; if you want to use
    '%' as an operator you can double it up, i.e. use '%%'

O que torna isso perigoso: `ruff`, `pyright` e todos os testes unitários
passaram. A query só é parseada quando executa, então só quebra em produção,
no primeiro request. Este teste faz o parse offline, com a mesma máquina do
psycopg que roda em produção.

Regra: dentro de query com parâmetros, `%` sozinho precisa virar `%%` — ou
sair do texto.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest
from psycopg._queries import PostgresQuery
from psycopg.adapt import Transformer

SRC = Path(__file__).resolve().parents[2] / "src" / "whatsapp_langchain"

# Só interessa string que o psycopg vai parsear: tem placeholder E cara de SQL.
SQL_KEYWORDS = re.compile(
    r"\b(SELECT|INSERT\s+INTO|UPDATE|DELETE\s+FROM)\b", re.IGNORECASE
)
PLACEHOLDER = re.compile(r"%s|%b|%t")


def _sql_literals() -> list[tuple[Path, int, str]]:
    """Todo literal de string do src/ que parece query parametrizada."""
    achados: list[tuple[Path, int, str]] = []
    for arquivo in sorted(SRC.rglob("*.py")):
        try:
            arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover - arquivo quebrado é outro teste
            continue
        for no in ast.walk(arvore):
            if not isinstance(no, ast.Constant) or not isinstance(no.value, str):
                continue
            texto = no.value
            if PLACEHOLDER.search(texto) and SQL_KEYWORDS.search(texto):
                achados.append((arquivo, no.lineno, texto))
    return achados


def test_encontra_queries_para_validar() -> None:
    """Sanidade: se o coletor parar de achar queries, o teste vira teatro."""
    assert len(_sql_literals()) > 20, (
        "coletor de SQL não encontrou queries — provavelmente parou de "
        "funcionar, e este arquivo passaria a aprovar tudo em silêncio"
    )


@pytest.mark.parametrize(
    "arquivo,linha,sql",
    _sql_literals(),
    ids=lambda v: f"{Path(v).name}" if isinstance(v, Path) else "",
)
def test_sql_sem_placeholder_incompleto(arquivo: Path, linha: int, sql: str) -> None:
    """Roda o parser real do psycopg — o mesmo que falha em produção."""
    n_params = len(PLACEHOLDER.findall(sql))
    query = PostgresQuery(Transformer())

    try:
        query.convert(sql, tuple([None] * n_params))
    except Exception as exc:  # noqa: BLE001 - queremos qualquer falha de parse
        if "placeholder" not in str(exc).lower():
            pytest.skip(f"falha não relacionada a placeholder: {exc}")
        rel = arquivo.relative_to(SRC.parents[1])
        pytest.fail(
            f"{rel}:{linha} tem '%' solto em SQL — quebra no primeiro request.\n"
            f"  {exc}\n"
            "  Comentário SQL também conta: o psycopg varre o texto inteiro."
        )


@pytest.mark.parametrize(
    "arquivo,linha,sql",
    _sql_literals(),
    ids=lambda v: f"{Path(v).name}" if isinstance(v, Path) else "",
)
def test_sql_sem_marcador_em_comentario(arquivo: Path, linha: int, sql: str) -> None:
    """Marcador de parâmetro dentro de comentário SQL é parâmetro fantasma.

    O teste acima não pega este caso: ele conta os marcadores do texto e passa
    exatamente essa quantidade, então um marcador a mais no comentário fica
    consistente consigo mesmo. Em produção, quem conta do outro lado é a tupla
    escrita à mão — e ela não sabe do comentário.

    Foi assim que `upsert_conexao` quebrou em 2026-07-22: um comentário
    explicando o COALESCE citou o marcador, virando 12 marcadores para 11
    parâmetros. Toda criação e edição de conexão passou a morrer em
    `ProgrammingError`, e nada acusou — nem ruff, nem pyright, nem esta suíte.
    """
    ofensores = [
        ln.strip()
        for ln in sql.splitlines()
        if ln.strip().startswith("--") and PLACEHOLDER.search(ln)
    ]
    if ofensores:
        rel = arquivo.relative_to(SRC.parents[1])
        pytest.fail(
            f"{rel}:{linha} cita marcador de parâmetro em comentário SQL:\n"
            + "\n".join(f"  {o}" for o in ofensores)
            + "\n  O psycopg conta esse marcador e a tupla de parâmetros não."
            "\n  Reescreva o comentário sem o marcador."
        )


def test_guarda_de_comentario_pega_o_caso_real() -> None:
    """A regra acima só vale se reprovar o texto que quebrou de verdade."""
    sql = (
        "INSERT INTO conexao (a, b) VALUES (%s, COALESCE(%s, 'manual'))\n"
        "ON CONFLICT DO UPDATE SET\n"
        "  -- o VALUES aplica COALESCE(%s,'manual'), então EXCLUDED nunca é NULL\n"
        "  a = EXCLUDED.a"
    )
    ofensores = [
        ln for ln in sql.splitlines() if ln.strip().startswith("--") and "%s" in ln
    ]
    assert ofensores, "a regra deixaria passar o comentário que derrubou o upsert"


def test_parser_realmente_pega_o_bug_original() -> None:
    """Sem isto, um parser quebrado faria o teste acima aprovar tudo."""
    query = PostgresQuery(Transformer())

    with pytest.raises(Exception, match="placeholder"):
        # Exatamente o formato que derrubou o dashboard: '%' seguido de espaço.
        query.convert("SELECT 1 -- de +91% que originou\n WHERE a = %s", (None,))
