"""Cadastro manual, CSV e classificação do lead (mig 201)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from whatsapp_langchain.shared.cliente import (
    ESTAGIOS_FUNIL,
    TEMPERATURAS,
    classificar_cliente,
    update_cliente_partial,
)
from whatsapp_langchain.shared.cliente_importacao import (
    escrever_csv_clientes,
    ler_csv_clientes,
    normalizar_telefone_cadastro,
)


def _pool(fetchone=None):
    cur = AsyncMock()
    cur.fetchone = AsyncMock(return_value=fetchone)
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cur)
    pool = MagicMock()
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


# ---------- telefone ----------


@pytest.mark.parametrize(
    ("raw", "esperado"),
    [
        ("(67) 99646-0034", "+5567996460034"),
        ("5567996460034", "+5567996460034"),
        ("+55 67 99646-0034", "+5567996460034"),
        ("+1 415 555 0100", "+14155550100"),
        ("+55996460034", None),  # país declarado, falta DDD
        ("12345", None),
        ("", None),
    ],
)
def test_normalizar_telefone_cadastro(raw, esperado):
    assert normalizar_telefone_cadastro(raw) == esperado


# ---------- leitura do CSV ----------


def test_csv_ponto_e_virgula_com_bom_e_cabecalho_acentuado():
    conteudo = (
        "\ufeffNome;Número de Telefone;E-mail;Região / Origem\n"
        "Ana;(67) 99646-0034;ana@x.com;Instagram\n"
    ).encode()
    res = ler_csv_clientes(conteudo)
    assert res.erro is None
    assert len(res.validas) == 1
    linha = res.validas[0]
    assert (linha.nome, linha.telefone, linha.email, linha.origem) == (
        "Ana",
        "+5567996460034",
        "ana@x.com",
        "Instagram",
    )


def test_csv_virgula_e_linhas_recusadas_com_motivo():
    conteudo = (
        b"nome,telefone,email\n"
        b"Ana,67996460034,\n"
        b"Bia,123,\n"  # telefone inválido
        b"Caio,67996460034,\n"  # repetido no arquivo
        b"Duda,67999990000,sem-arroba\n"  # e-mail inválido
        b",,\n"  # linha vazia é ignorada
        b"Eva,,\n"  # telefone vazio
    )
    res = ler_csv_clientes(conteudo)
    assert [v.nome for v in res.validas] == ["Ana"]
    assert [(i["linha"], i["motivo"][:8]) for i in res.invalidas] == [
        (3, "Telefone"),
        (4, "Telefone"),
        (5, "E-mail i"),
        (7, "Telefone"),
    ]


def test_csv_latin1_do_excel_antigo():
    conteudo = "nome;telefone\nJoão;67996460034\n".encode("latin-1")
    res = ler_csv_clientes(conteudo)
    assert res.validas[0].nome == "João"


def test_csv_sem_coluna_de_telefone_recusa_o_arquivo():
    res = ler_csv_clientes(b"nome;email\nAna;a@b.com\n")
    assert res.erro is not None
    assert "telefone" in res.erro


def test_csv_vazio():
    assert ler_csv_clientes(b"   ").erro == "O arquivo está vazio."


def test_exportacao_neutraliza_formula_e_mantem_telefone():
    out = escrever_csv_clientes(
        [["=HYPERLINK(1)", "+5567996460034", None, 80]],
        ["nome", "telefone", "email", "pontuacao"],
    ).decode("utf-8")
    assert out.startswith("\ufeff")
    linha = out.splitlines()[1]
    assert linha == "'=HYPERLINK(1);+5567996460034;;80"


# ---------- classificação ----------


def test_vocabulario_do_funil():
    assert list(ESTAGIOS_FUNIL) == [
        "lead",
        "mql",
        "sql",
        "oportunidade",
        "cliente",
        "perdido",
    ]
    assert list(TEMPERATURAS) == ["frio", "morno", "quente"]


async def test_classificar_ia_nao_sobrescreve_manual():
    pool, conn = _pool(fetchone=None)  # UPDATE não casou: manual preservada
    out = await classificar_cliente(
        pool, 1, 7, estagio="sql", temperatura="quente", pontuacao=80, origem="ia"
    )
    assert out is None
    sql = conn.execute.await_args.args[0]
    assert "classificacao_origem IS DISTINCT FROM 'manual'" in sql


async def test_classificar_manual_sem_guarda():
    pool, conn = _pool(fetchone=(7,))
    with patch(
        "whatsapp_langchain.shared.cliente.get_cliente_by_id",
        new=AsyncMock(return_value="cliente"),
    ):
        out = await classificar_cliente(
            pool,
            1,
            7,
            estagio=None,
            temperatura="frio",
            pontuacao=None,
            origem="manual",
        )
    assert out == "cliente"
    sql = conn.execute.await_args.args[0]
    assert "IS DISTINCT FROM" not in sql
    assert conn.execute.await_args.args[1][:4] == (None, "frio", None, "manual")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"estagio": "qualified", "temperatura": None, "pontuacao": None},
        {"estagio": None, "temperatura": "fervendo", "pontuacao": None},
        {"estagio": None, "temperatura": None, "pontuacao": 101},
    ],
)
async def test_classificar_recusa_valor_invalido(kwargs):
    pool, _ = _pool()
    with pytest.raises(ValueError):
        await classificar_cliente(pool, 1, 7, origem="manual", **kwargs)


async def test_ficha_com_estagio_marca_manual():
    pool, conn = _pool(fetchone=None)
    await update_cliente_partial(pool, 1, 7, lifecycle_stage="mql")
    sql = conn.execute.await_args.args[0]
    assert "classificacao_origem = 'manual'" in sql


async def test_ficha_sem_classificacao_nao_mexe_na_origem():
    pool, conn = _pool(fetchone=None)
    await update_cliente_partial(pool, 1, 7, nome="Ana")
    sql = conn.execute.await_args.args[0]
    assert "classificacao_origem" not in sql.split("RETURNING")[0]


# ---------- instrução no prompt do agente genérico ----------


@pytest.mark.parametrize(
    ("slugs", "tem_bloco"), [(["classificar_lead"], True), (["tag_cliente"], False)]
)
def test_prompt_ganha_instrucao_so_com_a_tool_ligada(slugs, tem_bloco):
    from whatsapp_langchain.agents.catalog.agente import agent as mod

    capturado = {}

    def _fake_create_agent(**kwargs):
        capturado.update(kwargs)
        return "grafo"

    with (
        patch.object(mod, "create_agent", _fake_create_agent),
        patch.object(mod, "create_chat_model", lambda **_: MagicMock()),
    ):
        mod.build_graph(
            tools_enabled=slugs, system_prompt_override="Prompt da empresa."
        )
    prompt = capturado["system_prompt"]
    assert prompt.startswith("Prompt da empresa.")
    assert ("<classificacao_do_lead>" in prompt) is tem_bloco
