"""Tests das 8 tools de cliente/atendimento (M5.b.1)."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from whatsapp_langchain.agents.tools import cliente_atendimento as ct
from whatsapp_langchain.shared.models import (
    Atendimento,
    Cliente,
    ClienteAnotacao,
)

# --- helpers ---


def _runtime(empresa_id: int = 1, atendimento_id: int = 5, user_id: str = "u1"):
    """Mock do runtime LangGraph com configurable preenchido."""
    return SimpleNamespace(
        config={
            "configurable": {
                "empresa_id": empresa_id,
                "atendimento_id": atendimento_id,
                "user_id": user_id,
            }
        }
    )


def _atendimento(
    *,
    id_=5,
    empresa_id=1,
    cliente_id=10,
    status="em_andamento",
):
    now = datetime.now(UTC)
    return Atendimento(
        id=id_,
        empresa_id=empresa_id,
        cliente_id=cliente_id,
        conexao_id=1,
        agente_atual="vsa_tech",
        status=status,
        assigned_to_user_id=None,
        last_message_at=now,
        closed_at=None,
        created_at=now,
        updated_at=now,
    )


def _cliente(
    *,
    id_=10,
    nome="João",
    telefone="+5511999",
    email=None,
    doc=None,
    tags=None,
):
    now = datetime.now(UTC)
    return Cliente(
        id=id_,
        empresa_id=1,
        telefone=telefone,
        nome=nome,
        email=email,
        doc=doc,
        status="active",
        config={},
        created_at=now,
        updated_at=now,
        tags=tags or [],
    )


@pytest.fixture(autouse=True)
def _patch_pool():
    """Todas as tools chamam get_pool() — mockamos pra retornar None."""
    with patch.object(ct, "get_pool", new=AsyncMock(return_value=MagicMock())):
        yield


# --- _extract_ids ---


def test_extract_ids_from_runtime_object():
    e, a = ct._extract_ids(_runtime(empresa_id=42, atendimento_id=99))
    assert e == 42
    assert a == 99


def test_extract_ids_returns_none_when_missing():
    e, a = ct._extract_ids(SimpleNamespace(config={"configurable": {}}))
    assert e is None
    assert a is None


def test_extract_ids_handles_invalid_types():
    rt = SimpleNamespace(
        config={"configurable": {"empresa_id": "abc", "atendimento_id": None}}
    )
    e, a = ct._extract_ids(rt)
    assert e is None
    assert a is None


# --- get_cliente_profile ---


@pytest.mark.asyncio
async def test_get_cliente_profile_returns_structured_data():
    with (
        patch.object(
            ct, "get_atendimento_by_id", AsyncMock(return_value=_atendimento())
        ),
        patch.object(
            ct,
            "get_cliente_by_id",
            AsyncMock(
                return_value=_cliente(nome="João", email="x@y.com", tags=["vip"])
            ),
        ),
    ):
        out = await ct.get_cliente_profile.ainvoke({"runtime": _runtime()})
    assert "nome: João" in out
    assert "email: x@y.com" in out
    assert "tags: vip" in out


@pytest.mark.asyncio
async def test_get_cliente_profile_handles_missing_atendimento():
    with patch.object(ct, "get_atendimento_by_id", AsyncMock(return_value=None)):
        out = await ct.get_cliente_profile.ainvoke({"runtime": _runtime()})
    assert "não encontrado" in out


@pytest.mark.asyncio
async def test_get_cliente_profile_anti_cross_tenant():
    """Atendimento de outra empresa → tool não retorna dados."""
    other_atd = _atendimento(empresa_id=99)  # ≠ runtime.empresa_id=1
    with patch.object(ct, "get_atendimento_by_id", AsyncMock(return_value=other_atd)):
        out = await ct.get_cliente_profile.ainvoke({"runtime": _runtime()})
    assert "não encontrado" in out


# --- get_cliente_history ---


@pytest.mark.asyncio
async def test_get_cliente_history_lists_atendimentos():
    historico = [_atendimento(id_=10, status="resolvido")]
    with (
        patch.object(
            ct, "get_atendimento_by_id", AsyncMock(return_value=_atendimento())
        ),
        patch.object(
            ct, "list_atendimentos_by_cliente", AsyncMock(return_value=historico)
        ),
    ):
        out = await ct.get_cliente_history.ainvoke({"runtime": _runtime()})
    assert "#10 (resolvido)" in out


@pytest.mark.asyncio
async def test_get_cliente_history_empty():
    with (
        patch.object(
            ct, "get_atendimento_by_id", AsyncMock(return_value=_atendimento())
        ),
        patch.object(ct, "list_atendimentos_by_cliente", AsyncMock(return_value=[])),
    ):
        out = await ct.get_cliente_history.ainvoke({"runtime": _runtime()})
    assert "Cliente novo" in out


@pytest.mark.asyncio
async def test_get_cliente_history_caps_limit_at_10():
    with (
        patch.object(
            ct, "get_atendimento_by_id", AsyncMock(return_value=_atendimento())
        ),
        patch.object(
            ct, "list_atendimentos_by_cliente", AsyncMock(return_value=[])
        ) as mock_list,
    ):
        await ct.get_cliente_history.ainvoke({"limit": 50, "runtime": _runtime()})
    kwargs = mock_list.await_args.kwargs
    assert kwargs["limit"] == 10


# --- get_cliente_anotacoes ---


@pytest.mark.asyncio
async def test_get_cliente_anotacoes_lists_notes():
    now = datetime.now(UTC)
    anotacao = ClienteAnotacao(
        id=1, cliente_id=10, user_id="op-1", conteudo="cliente VIP", created_at=now
    )
    with (
        patch.object(
            ct, "get_atendimento_by_id", AsyncMock(return_value=_atendimento())
        ),
        patch.object(ct, "list_anotacoes", AsyncMock(return_value=[anotacao])),
    ):
        out = await ct.get_cliente_anotacoes.ainvoke({"runtime": _runtime()})
    assert "cliente VIP" in out
    assert "op-1" in out


@pytest.mark.asyncio
async def test_get_cliente_anotacoes_empty():
    with (
        patch.object(
            ct, "get_atendimento_by_id", AsyncMock(return_value=_atendimento())
        ),
        patch.object(ct, "list_anotacoes", AsyncMock(return_value=[])),
    ):
        out = await ct.get_cliente_anotacoes.ainvoke({"runtime": _runtime()})
    assert "sem anotações" in out


# --- create_cliente_anotacao ---


@pytest.mark.asyncio
async def test_create_anotacao_persists():
    now = datetime.now(UTC)
    new = ClienteAnotacao(
        id=42, cliente_id=10, user_id="agente:u1", conteudo="x", created_at=now
    )
    with (
        patch.object(
            ct, "get_atendimento_by_id", AsyncMock(return_value=_atendimento())
        ),
        patch.object(ct, "add_anotacao", AsyncMock(return_value=new)) as mock_add,
    ):
        out = await ct.create_cliente_anotacao.ainvoke(
            {"conteudo": "Cliente reclamou de atraso", "runtime": _runtime()}
        )
    assert "#42" in out
    args = mock_add.await_args.args
    assert args[1] == 10  # cliente_id
    assert args[2].startswith("agente:")  # user_id


@pytest.mark.asyncio
async def test_create_anotacao_truncates_at_1000_chars():
    now = datetime.now(UTC)
    new = ClienteAnotacao(
        id=1, cliente_id=10, user_id="agente:u1", conteudo="x", created_at=now
    )
    with (
        patch.object(
            ct, "get_atendimento_by_id", AsyncMock(return_value=_atendimento())
        ),
        patch.object(ct, "add_anotacao", AsyncMock(return_value=new)) as mock_add,
    ):
        await ct.create_cliente_anotacao.ainvoke(
            {"conteudo": "x" * 2000, "runtime": _runtime()}
        )
    persisted_text = mock_add.await_args.args[3]
    assert len(persisted_text) == 1000


@pytest.mark.asyncio
async def test_create_anotacao_empty_returns_msg():
    out = await ct.create_cliente_anotacao.ainvoke(
        {"conteudo": "  ", "runtime": _runtime()}
    )
    assert "vazio" in out


# --- add_cliente_tag ---


@pytest.mark.asyncio
async def test_add_tag_lowercases_and_trims():
    with (
        patch.object(
            ct, "get_atendimento_by_id", AsyncMock(return_value=_atendimento())
        ),
        patch.object(ct, "add_tag", AsyncMock()) as mock_tag,
    ):
        out = await ct.add_cliente_tag.ainvoke(
            {"tag": "  VIP-Cliente  ", "runtime": _runtime()}
        )
    assert "vip-cliente" in out
    persisted = mock_tag.await_args.args[2]
    assert persisted == "vip-cliente"


@pytest.mark.asyncio
async def test_add_tag_caps_at_30_chars():
    with (
        patch.object(
            ct, "get_atendimento_by_id", AsyncMock(return_value=_atendimento())
        ),
        patch.object(ct, "add_tag", AsyncMock()) as mock_tag,
    ):
        await ct.add_cliente_tag.ainvoke({"tag": "x" * 50, "runtime": _runtime()})
    assert len(mock_tag.await_args.args[2]) == 30


# --- update_cliente ---


@pytest.mark.asyncio
async def test_update_cliente_returns_fields_set():
    with (
        patch.object(
            ct, "get_atendimento_by_id", AsyncMock(return_value=_atendimento())
        ),
        patch.object(ct, "update_cliente_partial", AsyncMock(return_value=_cliente())),
    ):
        out = await ct.update_cliente.ainvoke(
            {"nome": "Maria", "email": "m@x.com", "runtime": _runtime()}
        )
    assert "nome" in out and "email" in out


@pytest.mark.asyncio
async def test_update_cliente_no_fields_returns_no_op():
    with patch.object(
        ct, "get_atendimento_by_id", AsyncMock(return_value=_atendimento())
    ):
        out = await ct.update_cliente.ainvoke({"runtime": _runtime()})
    assert "Nada pra atualizar" in out


# --- close_atendimento ---


@pytest.mark.asyncio
async def test_close_atendimento_resolves():
    with (
        patch.object(
            ct, "get_atendimento_by_id", AsyncMock(return_value=_atendimento())
        ),
        patch.object(
            ct,
            "_close_atendimento",
            AsyncMock(return_value=_atendimento(status="resolvido")),
        ) as mock_close,
    ):
        out = await ct.close_atendimento.ainvoke({"runtime": _runtime()})
    assert "resolvido" in out
    args = mock_close.await_args.args
    assert args[1] == 5  # atendimento_id
    assert args[2] == "resolvido"


@pytest.mark.asyncio
async def test_close_atendimento_rejects_already_closed():
    closed = _atendimento(status="resolvido")
    with patch.object(ct, "get_atendimento_by_id", AsyncMock(return_value=closed)):
        out = await ct.close_atendimento.ainvoke({"runtime": _runtime()})
    assert "já está em status" in out


@pytest.mark.asyncio
async def test_close_atendimento_normalizes_motivo():
    """Motivo inválido vira 'resolvido'."""
    with (
        patch.object(
            ct, "get_atendimento_by_id", AsyncMock(return_value=_atendimento())
        ),
        patch.object(
            ct,
            "_close_atendimento",
            AsyncMock(return_value=_atendimento(status="resolvido")),
        ) as mock_close,
    ):
        await ct.close_atendimento.ainvoke({"motivo": "lixo", "runtime": _runtime()})
    assert mock_close.await_args.args[2] == "resolvido"


# --- transfer_to_human ---


def _conn_cm_pool() -> MagicMock:
    """Pool MagicMock cujo `connection()` é um async CM (pra INSERT auditoria
    + SELECT name do atendente que o transfer_to_human faz inline)."""
    cur = AsyncMock()
    cur.fetchone = AsyncMock(return_value=("Atendente Fulano",))
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cur)
    conn.commit = AsyncMock()
    pool = MagicMock()
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool


def _transfer_mocks(*, departamento_default_id: int = 3, dep_ativo: bool = True):
    """Conjunto de patches do grafo de dependências do transfer_to_human
    (refeito após o tool ganhar departamento determinístico + resumo
    obrigatório + auto-claim por capacidade + outbound/hook).

    Retorna um context manager `patch.multiple`-like via lista de patchers e
    os mocks relevantes pra asserção.
    """
    agente = MagicMock()
    agente.departamento_default_id = departamento_default_id
    dep = MagicMock()
    dep.id = departamento_default_id
    dep.nome = "Suporte"
    dep.ativo = dep_ativo
    atd_updated = _atendimento(status="aguardando")
    # complete_triagem devolve Atendimento; alguns campos extras são lidos.
    atd_updated.protocolo = "ATD-001"
    atd_updated.prioridade = "alta"
    atd_updated.classificacao = None
    atd_updated.sentimento = None
    atd_updated.cliente_nome = "Cliente X"
    atd_updated.cliente_telefone = "+5511999"
    return agente, dep, atd_updated


@pytest.mark.asyncio
async def test_transfer_to_human_adds_tag_and_anotacao():
    new = ClienteAnotacao(
        id=99,
        cliente_id=10,
        user_id="agente:u1",
        conteudo="[HANDOFF → Suporte] cliente reclamando",
        created_at=datetime.now(UTC),
    )
    agente, dep, atd_updated = _transfer_mocks()
    pool = _conn_cm_pool()
    with (
        patch.object(ct, "get_pool", new=AsyncMock(return_value=pool)),
        patch.object(
            ct, "get_atendimento_by_id", AsyncMock(return_value=_atendimento())
        ),
        patch.object(ct, "get_agente_by_slug", AsyncMock(return_value=agente)),
        patch.object(ct, "get_departamento_by_id", AsyncMock(return_value=dep)),
        patch.object(ct, "complete_triagem", AsyncMock(return_value=atd_updated)),
        patch.object(ct, "pick_best_atendente", AsyncMock(return_value=None)),
        patch.object(ct, "claim_atendimento", AsyncMock()),
        patch.object(ct, "dispatch_event", AsyncMock()),
        patch(
            "whatsapp_langchain.shared.outbound.send_system_outbound",
            new=AsyncMock(),
        ),
        patch.object(ct, "add_tag", AsyncMock()) as mock_tag,
        patch.object(ct, "add_anotacao", AsyncMock(return_value=new)) as mock_anot,
    ):
        out = await ct.transfer_to_human.ainvoke(
            {
                "motivo": "cliente reclamando",
                "resumo": "- Cliente X\n- Quer suporte",
                "runtime": _runtime(),
            }
        )
    assert "transferido" in out.lower()
    assert "Suporte" in out
    assert mock_tag.await_args.args[2] == "handoff"
    # Anotação agora carrega o depto resolvido + resumo IA.
    assert "[HANDOFF → Suporte]" in mock_anot.await_args.args[3]
    assert "cliente reclamando" in mock_anot.await_args.args[3]


@pytest.mark.asyncio
async def test_transfer_to_human_handles_empty_motivo():
    new = ClienteAnotacao(
        id=1,
        cliente_id=10,
        user_id="agente:u1",
        conteudo="x",
        created_at=datetime.now(UTC),
    )
    agente, dep, atd_updated = _transfer_mocks()
    pool = _conn_cm_pool()
    with (
        patch.object(ct, "get_pool", new=AsyncMock(return_value=pool)),
        patch.object(
            ct, "get_atendimento_by_id", AsyncMock(return_value=_atendimento())
        ),
        patch.object(ct, "get_agente_by_slug", AsyncMock(return_value=agente)),
        patch.object(ct, "get_departamento_by_id", AsyncMock(return_value=dep)),
        patch.object(ct, "complete_triagem", AsyncMock(return_value=atd_updated)),
        patch.object(ct, "pick_best_atendente", AsyncMock(return_value=None)),
        patch.object(ct, "claim_atendimento", AsyncMock()),
        patch.object(ct, "dispatch_event", AsyncMock()),
        patch(
            "whatsapp_langchain.shared.outbound.send_system_outbound",
            new=AsyncMock(),
        ),
        patch.object(ct, "add_tag", AsyncMock()),
        patch.object(ct, "add_anotacao", AsyncMock(return_value=new)) as mock_anot,
    ):
        await ct.transfer_to_human.ainvoke(
            {"motivo": "", "resumo": "- resumo", "runtime": _runtime()}
        )
    # motivo vazio → "sem motivo informado" no texto da anotação.
    assert "sem motivo" in mock_anot.await_args.args[3].lower()


# --- classificar_lead (mig 201) ---


def _args(**extra):
    base = {
        "estagio": "SQL",
        "temperatura": "Quente",
        "pontuacao": 130,
        "motivo": "pediu orçamento",
        "runtime": _runtime(),
    }
    base.update(extra)
    return base


@pytest.mark.asyncio
async def test_classificar_lead_grava_como_ia_no_cliente_do_atendimento():
    classificar = AsyncMock(return_value=_cliente())
    with (
        patch.object(ct, "get_pool", AsyncMock(return_value=MagicMock())),
        patch.object(
            ct, "get_atendimento_by_id", AsyncMock(return_value=_atendimento())
        ),
        patch.object(ct, "classificar_cliente", classificar),
    ):
        out = await ct.classificar_lead.ainvoke(_args())
    assert "Sugestão registrada" in out
    kwargs = classificar.await_args.kwargs
    assert classificar.await_args.args[1:] == (1, 10)
    assert kwargs["origem"] == "ia"
    assert (kwargs["estagio"], kwargs["temperatura"], kwargs["pontuacao"]) == (
        "sql",
        "quente",
        100,
    )


@pytest.mark.asyncio
async def test_classificar_lead_respeita_classificacao_manual():
    with (
        patch.object(ct, "get_pool", AsyncMock(return_value=MagicMock())),
        patch.object(
            ct, "get_atendimento_by_id", AsyncMock(return_value=_atendimento())
        ),
        patch.object(ct, "classificar_cliente", AsyncMock(return_value=None)),
    ):
        out = await ct.classificar_lead.ainvoke(_args())
    assert "já classificou" in out


@pytest.mark.asyncio
async def test_classificar_lead_recusa_estagio_fora_do_funil():
    classificar = AsyncMock()
    with patch.object(ct, "classificar_cliente", classificar):
        out = await ct.classificar_lead.ainvoke(_args(estagio="qualified"))
    assert "Estágio inválido" in out
    classificar.assert_not_awaited()


@pytest.mark.asyncio
async def test_classificar_lead_nao_opera_em_atendimento_de_outra_empresa():
    classificar = AsyncMock()
    with (
        patch.object(ct, "get_pool", AsyncMock(return_value=MagicMock())),
        patch.object(
            ct,
            "get_atendimento_by_id",
            AsyncMock(return_value=_atendimento(empresa_id=2)),
        ),
        patch.object(ct, "classificar_cliente", classificar),
    ):
        out = await ct.classificar_lead.ainvoke(_args())
    assert "não encontrado" in out
    classificar.assert_not_awaited()
