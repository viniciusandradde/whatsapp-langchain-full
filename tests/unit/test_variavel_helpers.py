"""Testes do helper de Variáveis de Ambiente (M5.d)."""

from datetime import UTC, datetime, time
from unittest.mock import AsyncMock, MagicMock

import pytest
from psycopg import errors as pg_errors

from whatsapp_langchain.shared import variavel
from whatsapp_langchain.shared.models import VariavelAmbienteInput


def _row(
    *,
    var_id=1,
    empresa_id=1,
    nome="suporte_email",
    valor="suporte@empresa.com",
    descricao=None,
    ativo=True,
    user_id=None,
):
    now = datetime.now(UTC)
    return (
        var_id,
        empresa_id,
        nome,
        valor,
        descricao,
        ativo,
        user_id,
        now,
        now,
    )


def _mock_pool(*results, rowcount: int = 1, multi: bool = False, fetchall=None):
    cur = AsyncMock()
    if fetchall is not None:
        cur.fetchall = AsyncMock(return_value=fetchall)
    elif multi:
        cur.fetchall = AsyncMock(return_value=list(results))
    else:
        fetchone_seq = list(results) if results else [None]
        cur.fetchone = AsyncMock(side_effect=fetchone_seq)
    cur.rowcount = rowcount
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cur)
    pool = MagicMock()
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn, cur


# --- render_template ---


def test_render_simple_substitution():
    ctx = {"empresa.nome": "VSA Tech", "data.hoje": "2026-05-02"}
    out = variavel.render_template("Olá da {{empresa.nome}} hoje ({{data.hoje}})!", ctx)
    assert out == "Olá da VSA Tech hoje (2026-05-02)!"


def test_render_missing_key_left_literal():
    ctx = {"empresa.nome": "X"}
    out = variavel.render_template("Oi {{var.algumacoisa}} fim", ctx)
    assert out == "Oi {{var.algumacoisa}} fim"


def test_render_handles_whitespace_inside_braces():
    ctx = {"empresa.nome": "X"}
    assert variavel.render_template("{{ empresa.nome }}", ctx) == "X"


def test_render_empty_string_passthrough():
    assert variavel.render_template("", {"empresa.nome": "X"}) == ""


def test_render_no_template_unchanged():
    assert variavel.render_template("texto puro", {"x": "y"}) == "texto puro"


def test_render_does_not_recurse():
    """Substituição não recursiva — ctx pode conter `{{...}}` sem looping."""
    ctx = {"var.x": "{{var.y}}"}
    assert variavel.render_template("eco: {{var.x}}", ctx) == "eco: {{var.y}}"


# --- CRUD ---


@pytest.mark.asyncio
async def test_get_variavel_filters_by_empresa():
    pool, conn, _ = _mock_pool(None)
    await variavel.get_variavel_by_id(pool, 7, 99)
    sql, params = conn.execute.await_args.args
    assert "empresa_id = %s" in sql
    assert params == (99, 7)


@pytest.mark.asyncio
async def test_list_variaveis_apenas_ativos_filters_in_sql():
    pool, conn, _ = _mock_pool(fetchall=[])
    await variavel.list_variaveis(pool, 1, apenas_ativos=True)
    sql = conn.execute.await_args.args[0]
    assert "AND ativo" in sql


@pytest.mark.asyncio
async def test_create_returns_variavel():
    pool, _, _ = _mock_pool(_row())
    out = await variavel.create_variavel(
        pool,
        1,
        VariavelAmbienteInput(nome="suporte_email", valor="x@y.com"),
        user_id="u",
    )
    assert out.nome == "suporte_email"


@pytest.mark.asyncio
async def test_create_raises_duplicate_on_unique_violation():
    pool = MagicMock()
    conn = MagicMock()
    conn.execute = AsyncMock(side_effect=pg_errors.UniqueViolation("dup"))
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    with pytest.raises(variavel.DuplicateNomeError):
        await variavel.create_variavel(
            pool,
            1,
            VariavelAmbienteInput(nome="x", valor="y"),
        )


@pytest.mark.asyncio
async def test_update_returns_none_when_missing():
    pool, _, _ = _mock_pool(None)
    out = await variavel.update_variavel(
        pool,
        1,
        99,
        VariavelAmbienteInput(nome="x", valor="y"),
    )
    assert out is None


@pytest.mark.asyncio
async def test_update_raises_duplicate_on_rename_conflict():
    pool = MagicMock()
    conn = MagicMock()
    conn.execute = AsyncMock(side_effect=pg_errors.UniqueViolation("dup"))
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    with pytest.raises(variavel.DuplicateNomeError):
        await variavel.update_variavel(
            pool,
            1,
            5,
            VariavelAmbienteInput(nome="conflito", valor="y"),
        )


@pytest.mark.asyncio
async def test_delete_returns_true_when_deleted():
    pool, _, _ = _mock_pool(rowcount=1)
    assert await variavel.delete_variavel(pool, 1, 1) is True


@pytest.mark.asyncio
async def test_delete_returns_false_when_missing():
    pool, _, _ = _mock_pool(rowcount=0)
    assert await variavel.delete_variavel(pool, 1, 99) is False


# --- build_render_context ---


@pytest.mark.asyncio
async def test_build_render_context_assembles_namespaces():
    """Sem atendimento_id, retorna empresa.*, var.*, data.*."""
    cur = AsyncMock()
    # fetchone (empresa) + fetchall (vars)
    # Colunas 5-8: timezone (mig 174) + expediente (mig 175).
    cur.fetchone = AsyncMock(
        return_value=(
            "VSA Tech",
            "vsa",
            "12345",
            "free",
            "America/Campo_Grande",
            None,
            None,
            None,
        )
    )
    cur.fetchall = AsyncMock(
        return_value=[
            ("suporte_email", "suporte@vsa.com"),
            ("horario", "9-18h"),
        ]
    )
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cur)
    pool = MagicMock()
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)

    ctx = await variavel.build_render_context(
        pool,
        1,
        now=datetime(2026, 5, 2, 14, 30, tzinfo=UTC),
    )
    assert ctx["empresa.nome"] == "VSA Tech"
    assert ctx["empresa.slug"] == "vsa"
    assert ctx["var.suporte_email"] == "suporte@vsa.com"
    assert ctx["var.horario"] == "9-18h"
    assert ctx["data.hoje"] == "2026-05-02"
    assert ctx["data.ano"] == "2026"
    # cliente.* não foi populado (nenhum atendimento_id)
    assert "cliente.nome" not in ctx


@pytest.mark.asyncio
async def test_build_render_context_inclui_cliente_quando_atendimento():
    cur = AsyncMock()
    # 3 fetchone (empresa, menu_chatbot, cliente) + fetchall (vars).
    # A 2ª query é o lookup de menu.* (menu_chatbot) — None = sem menu ativo.
    cur.fetchone = AsyncMock(
        side_effect=[
            ("Empresa", "e", None, "free", "America/Campo_Grande", None, None, None),
            None,  # menu_chatbot ativo (nenhum)
            ("João", "+5511999999999", "joao@x.com", "12345"),
        ]
    )
    cur.fetchall = AsyncMock(return_value=[])
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cur)
    pool = MagicMock()
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)

    ctx = await variavel.build_render_context(pool, 1, atendimento_id=42)
    assert ctx["cliente.nome"] == "João"
    assert ctx["cliente.telefone"] == "+5511999999999"


# ---- mig 174: `data.*` no fuso da empresa ----
#
# O bug que originou estes testes: às 19h em Mato Grosso do Sul o relógio UTC
# já marca 23h, e um prompt que decide "estamos no horário de atendimento?"
# concluía que o expediente tinha acabado — no meio do expediente.


class TestContextoDeData:
    def test_hora_sai_no_fuso_da_empresa_nao_em_utc(self) -> None:
        # 23:30 UTC é 19:30 em Campo Grande (UTC-4).
        now = datetime(2026, 8, 20, 23, 30, tzinfo=UTC)
        ctx = variavel._contexto_de_data(now, "America/Campo_Grande")
        assert ctx["data.agora"] == "19:30"

    def test_data_nao_vira_o_dia_antes_da_meia_noite_local(self) -> None:
        # 01:00 UTC do dia 21 ainda é dia 20 em Campo Grande.
        now = datetime(2026, 8, 21, 1, 0, tzinfo=UTC)
        ctx = variavel._contexto_de_data(now, "America/Campo_Grande")
        assert ctx["data.hoje"] == "2026-08-20"
        assert ctx["data.ano"] == "2026"

    def test_dia_da_semana_em_portugues(self) -> None:
        # 2026-08-20 é uma quinta-feira; o locale do container é o C, então o
        # nome não pode vir do strftime.
        now = datetime(2026, 8, 20, 15, 0, tzinfo=UTC)
        ctx = variavel._contexto_de_data(now, "America/Campo_Grande")
        assert ctx["data.dia_semana"] == "quinta-feira"
        assert ctx["data.fim_de_semana"] == "não"

    def test_sabado_marca_fim_de_semana(self) -> None:
        now = datetime(2026, 8, 22, 15, 0, tzinfo=UTC)
        ctx = variavel._contexto_de_data(now, "America/Campo_Grande")
        assert ctx["data.dia_semana"] == "sábado"
        assert ctx["data.fim_de_semana"] == "sim"

    def test_fuso_diferente_e_respeitado(self) -> None:
        now = datetime(2026, 8, 20, 23, 30, tzinfo=UTC)
        ctx = variavel._contexto_de_data(now, "America/Sao_Paulo")
        assert ctx["data.agora"] == "20:30"
        assert ctx["data.fuso"] == "America/Sao_Paulo"

    def test_fuso_invalido_cai_no_padrao_em_vez_de_estourar(self) -> None:
        # Cadastro errado não pode deixar o agente sem prompt.
        now = datetime(2026, 8, 20, 23, 30, tzinfo=UTC)
        ctx = variavel._contexto_de_data(now, "Marte/Olympus")
        assert ctx["data.agora"] == "19:30"


class TestExpedienteAgora:
    """mig 175 — a conta de "estamos abertos?" sai do prompt e vem pro código.

    Três modelos diferentes erraram essa decisão quando ela ficava no prompt:
    um dizia "fora do horário" às 19h (dentro), outro atendia à 01h (fora).
    """

    UTEIS = [1, 2, 3, 4, 5]

    def _em(self, dia: int, hora: int, minuto: int = 0) -> datetime:
        # 2026-08-17 é uma segunda-feira; dia=1 → segunda, 6 → sábado.
        return datetime(2026, 8, 16 + dia, hora, minuto, tzinfo=UTC)

    def test_dentro_do_expediente(self) -> None:
        agora = self._em(4, 19, 30)  # quinta, 19:30
        r = variavel._expediente_agora(agora, time(6, 0), time(23, 0), self.UTEIS)
        assert r == "ABERTO"

    def test_antes_de_abrir(self) -> None:
        r = variavel._expediente_agora(
            self._em(4, 5, 59), time(6), time(23), self.UTEIS
        )
        assert r == "FECHADO"

    def test_na_hora_exata_de_abrir_ja_esta_aberto(self) -> None:
        r = variavel._expediente_agora(self._em(4, 6, 0), time(6), time(23), self.UTEIS)
        assert r == "ABERTO"

    def test_na_hora_exata_de_fechar_ja_fechou(self) -> None:
        r = variavel._expediente_agora(
            self._em(4, 23, 0), time(6), time(23), self.UTEIS
        )
        assert r == "FECHADO"

    def test_sabado_fechado_quando_so_dias_uteis(self) -> None:
        r = variavel._expediente_agora(
            self._em(6, 10, 0), time(6), time(23), self.UTEIS
        )
        assert r == "FECHADO"

    def test_sabado_aberto_quando_incluido(self) -> None:
        r = variavel._expediente_agora(
            self._em(6, 10, 0), time(6), time(23), [1, 2, 3, 4, 5, 6]
        )
        assert r == "ABERTO"

    def test_sem_expediente_cadastrado_fica_vazio(self) -> None:
        # Empresa que não usa o recurso não ganha a variável — o prompt dela
        # continua exatamente como era.
        assert variavel._expediente_agora(self._em(4, 12), None, None, None) == ""

    def test_turno_que_cruza_a_meia_noite(self) -> None:
        # Plantão 22h→06h: 01h de sexta ainda é o turno que abriu na quinta.
        madrugada = self._em(5, 1, 0)
        r = variavel._expediente_agora(madrugada, time(22), time(6), [4])
        assert r == "ABERTO"

    def test_turno_que_cruza_meia_noite_fecha_no_fim(self) -> None:
        r = variavel._expediente_agora(self._em(5, 6, 30), time(22), time(6), [4, 5])
        assert r == "FECHADO"


class TestJanelaTexto:
    """A janela vira texto a partir do MESMO cadastro que decide ABERTO/FECHADO.

    Sem isso o prompt repetia "das 6h às 23h" à mão: mudar o cadastro para 20h
    deixava o texto mentindo, e o modelo obedece ao texto, não ao cálculo.
    """

    def test_dias_uteis(self) -> None:
        assert (
            variavel._janela_texto(time(6), time(23), [1, 2, 3, 4, 5])
            == "segunda a sexta, das 06:00 às 23:00"
        )

    def test_dias_avulsos(self) -> None:
        assert (
            variavel._janela_texto(time(8), time(12), [1, 3])
            == "segunda, quarta, das 08:00 às 12:00"
        )

    def test_sem_cadastro_fica_vazio(self) -> None:
        assert variavel._janela_texto(None, None, None) == ""


class TestInstrucaoExpediente:
    """A frase de "fora do horário" só existe no prompt quando ele está fechado.

    Em produção o agente mandou a frase mesmo com `ATENDIMENTO AGORA: ABERTO`
    escrito no prompt — ela estava logo abaixo, pronta para copiar. Tirar a
    frase do prompt quando não cabe é mais confiável do que proibir o uso.
    """

    def test_aberto_nao_contem_a_frase_de_aviso(self) -> None:
        txt = variavel._instrucao_expediente(
            "ABERTO", "segunda a sexta, das 06:00 às 23:00"
        )
        assert "fora do horário de atendimento" not in txt
        assert "ABERTO" in txt

    def test_fechado_traz_a_frase_pronta_com_a_janela(self) -> None:
        txt = variavel._instrucao_expediente(
            "FECHADO", "segunda a sexta, das 06:00 às 23:00"
        )
        assert (
            "fora do horário de atendimento (segunda a sexta, das 06:00 às 23:00)"
            in txt
        )

    def test_sem_expediente_cadastrado_nao_diz_nada(self) -> None:
        assert variavel._instrucao_expediente("", "") == ""
