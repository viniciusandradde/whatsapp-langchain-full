"""ADR-002, Etapa 4 — escopo de atendimento por conexão (Decisão 6).

Cobre a parte que pode regredir em silêncio: os guards de "set vazio = zero
resultados, sem nem abrir conexão com o banco" e a montagem do WHERE/params
em `historico._build_where` e `historico_relatorios._scope`. A escolha de
composição (só afeta `.own`, mesmo padrão do escopo por departamento) foi
decidida com o dono em 2026-09-17 — ver docs/ADR-002-modelo-de-autorizacao.md.
"""

from __future__ import annotations

import pytest

from whatsapp_langchain.shared.atendimento import list_atendimentos
from whatsapp_langchain.shared.historico import HistoricoFiltros, _build_where
from whatsapp_langchain.shared.historico_relatorios import _scope


class _PoolSemConexao:
    """Sentinela: qualquer tentativa de `pool.connection()` estoura
    AttributeError — prova que o guard de set vazio corta ANTES de tocar
    o banco (mesma garantia que `scope_departamento_ids` já tinha)."""


async def test_scope_conexao_vazio_nao_abre_conexao_com_banco():
    out = await list_atendimentos(
        _PoolSemConexao(),  # type: ignore[arg-type]
        1,
        tipo="todas",
        scope_conexao_ids=set(),
    )
    assert out == []


async def test_scope_conexao_none_nao_e_o_mesmo_que_vazio():
    """None = sem filtro (seguiria pro banco); só o SET VAZIO corta cedo.
    Confirma que `None` não aciona o mesmo guard de `scope_conexao_ids`."""
    with pytest.raises(AttributeError):
        await list_atendimentos(
            _PoolSemConexao(),  # type: ignore[arg-type]
            1,
            tipo="todas",
            scope_conexao_ids=None,
        )


def test_build_where_sem_nenhum_escopo():
    where, params = _build_where(1, HistoricoFiltros(), None, None)
    assert "conexao_id" not in where
    assert "departamento_id" not in where
    assert params == [1]


def test_build_where_so_conexao():
    where, params = _build_where(1, HistoricoFiltros(), None, {10, 20})
    assert "a.conexao_id = ANY(%s)" in where
    assert "departamento_id" not in where
    assert params == [1, [10, 20]]


def test_build_where_departamento_e_conexao_juntos():
    """As duas condições entram por AND — restringe mais, nunca alarga."""
    where, params = _build_where(1, HistoricoFiltros(), {5}, {10, 20})
    assert "a.departamento_id = ANY(%s)" in where
    assert "a.conexao_id = ANY(%s)" in where
    # Departamento vem antes de conexão — ordem dos params tem que bater.
    assert params == [1, [5], [10, 20]]


def test_scope_relatorios_sem_nenhum_escopo():
    sql, params = _scope(None, None)
    assert sql == ""
    assert params == []


def test_scope_relatorios_departamento_e_conexao():
    sql, params = _scope({1, 2}, {9})
    assert "a.departamento_id = ANY(%s)" in sql
    assert "a.conexao_id = ANY(%s)" in sql
    assert params == [[1, 2], [9]]
