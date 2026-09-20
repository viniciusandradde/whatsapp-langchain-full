"""Trim por caracteres (ADR-004, `middleware/trim.py::max_chars`).

O corte por turnos já é coberto em `tests/integration/test_context_middleware.py`;
aqui é o teto em caracteres que o tier `agente_ia.contexto_tamanho` liga.
"""

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.graph import add_messages

from whatsapp_langchain.agents.middleware.trim import create_trim_middleware


def _turnos(n: int, chars_por_turno: int) -> list:
    """N turnos [h a], cada um com `chars_por_turno` caracteres no total."""
    metade = chars_por_turno // 2
    msgs: list = []
    for i in range(1, n + 1):
        msgs.append(HumanMessage(content="h" * metade, id=f"h{i}"))
        msgs.append(AIMessage(content="a" * (chars_por_turno - metade), id=f"a{i}"))
    return msgs


def _aplicar(mw, messages: list) -> list:
    result = mw.before_model({"messages": messages}, None)
    if result is None:
        return messages
    return add_messages(messages, result["messages"])


def _ids(messages: list) -> list[str]:
    return [m.id for m in messages]


def test_sem_max_chars_e_identico_ao_corte_por_turnos() -> None:
    msgs = _turnos(4, 100)
    com = _aplicar(create_trim_middleware(keep_turns=2, max_chars=None), msgs)
    referencia = _aplicar(create_trim_middleware(keep_turns=2), msgs)
    assert _ids(com) == _ids(referencia) == ["h3", "a3", "h4", "a4"]


def test_sem_max_chars_e_poucos_turnos_nao_mexe() -> None:
    mw = create_trim_middleware(keep_turns=5, max_chars=None)
    msgs = _turnos(3, 100)
    assert mw.before_model({"messages": msgs}, None) is None


def test_tres_turnos_de_3000_com_teto_de_6000_ficam_os_dois_ultimos() -> None:
    mw = create_trim_middleware(keep_turns=10, max_chars=6_000)
    final = _aplicar(mw, _turnos(3, 3_000))
    assert _ids(final) == ["h2", "a2", "h3", "a3"]


def test_turno_unico_maior_que_o_teto_fica_inteiro() -> None:
    mw = create_trim_middleware(keep_turns=10, max_chars=6_000)
    msgs = _turnos(1, 10_000)
    assert mw.before_model({"messages": msgs}, None) is None


def test_turno_mais_recente_entra_sempre_mesmo_estourando() -> None:
    """3 turnos, o último sozinho passa do teto: sai tudo menos ele."""
    mw = create_trim_middleware(keep_turns=10, max_chars=6_000)
    msgs = _turnos(2, 1_000) + _turnos(1, 10_000)
    msgs[-2].id, msgs[-1].id = "h3", "a3"
    final = _aplicar(mw, msgs)
    assert _ids(final) == ["h3", "a3"]


def test_menor_dos_dois_limites_vence() -> None:
    # keep_turns=1 com teto folgado → 1 turno
    mw = create_trim_middleware(keep_turns=1, max_chars=1_000_000)
    assert _ids(_aplicar(mw, _turnos(3, 100))) == ["h3", "a3"]
    # teto apertado com keep_turns folgado → o teto manda
    mw = create_trim_middleware(keep_turns=50, max_chars=250)
    assert _ids(_aplicar(mw, _turnos(3, 100))) == ["h2", "a2", "h3", "a3"]


def test_teto_conta_o_turno_inteiro_inclusive_tool_calls() -> None:
    """Turno = do HumanMessage até antes do próximo; não corta no meio."""
    from langchain_core.messages import ToolMessage

    msgs = [
        HumanMessage(content="x" * 100, id="h1"),
        AIMessage(content="y" * 100, id="a1"),
        HumanMessage(content="x" * 100, id="h2"),
        AIMessage(
            content="", id="a2", tool_calls=[{"name": "t", "args": {}, "id": "c"}]
        ),
        ToolMessage(content="z" * 2_000, tool_call_id="c", id="t2"),
        AIMessage(content="y" * 100, id="a2b"),
        HumanMessage(content="x" * 100, id="h3"),
        AIMessage(content="y" * 100, id="a3"),
    ]
    # h3+a3 = 200 cabe; turno 2 (2.200) estoura o teto de 1.000 → sai com o 1
    mw = create_trim_middleware(keep_turns=10, max_chars=1_000)
    assert _ids(_aplicar(mw, msgs)) == ["h3", "a3"]
