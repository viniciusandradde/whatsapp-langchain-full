"""Unit tests do módulo shared/coleta — wizard de coleta por menu_item.

Foca na lógica de state machine + validadores + template render — sem
worker, sem DB. Reusa validators de workflows pra evitar duplicação.
"""

from __future__ import annotations

import pytest

from whatsapp_langchain.shared.coleta import (
    ColetaPergunta,
    avancar_resposta,
    build_coleta_render_ctx,
    is_em_andamento,
    make_estado_inicial,
    make_resumo_final,
    normalize_perguntas,
    pergunta_atual,
    render_pergunta_label,
    validar_e_processar,
)

# ---- Pydantic ColetaPergunta ----


def test_coleta_pergunta_save_as_valido():
    p = ColetaPergunta(label="CPF?", save_as="cpf_paciente", validate_with="cpf")
    assert p.save_as == "cpf_paciente"


def test_coleta_pergunta_save_as_invalido_com_numero_inicial():
    with pytest.raises(ValueError, match="save_as deve ser slug"):
        ColetaPergunta(label="x", save_as="1cpf")


def test_coleta_pergunta_save_as_reservado():
    for reservado in ("cliente", "empresa", "data", "var"):
        with pytest.raises(ValueError, match="reservado"):
            ColetaPergunta(label="x", save_as=reservado)


def test_coleta_pergunta_save_as_prefixo_reservado():
    with pytest.raises(ValueError, match="reservado"):
        ColetaPergunta(label="x", save_as="cliente_nome")


def test_coleta_pergunta_validate_with_desconhecido():
    with pytest.raises(ValueError, match="desconhecido"):
        ColetaPergunta(label="x", save_as="y", validate_with="foobar")


def test_coleta_pergunta_validate_with_min_len_ok():
    p = ColetaPergunta(label="x", save_as="y", validate_with="min_len:3")
    assert p.validate_with == "min_len:3"


# ---- normalize_perguntas ----


def test_normalize_perguntas_vazia():
    assert normalize_perguntas(None) == []
    assert normalize_perguntas([]) == []


def test_normalize_perguntas_propaga_defaults():
    out = normalize_perguntas(
        [{"label": "CPF?", "save_as": "cpf", "validate_with": "cpf"}]
    )
    assert len(out) == 1
    assert out[0]["obrigatorio"] is True
    assert out[0]["retry_message"] is None


# ---- State machine helpers ----


def _make_perguntas() -> list[dict]:
    return normalize_perguntas([
        {"label": "Qual seu CPF?", "save_as": "cpf", "validate_with": "cpf"},
        {
            "label": "Obrigado, agora telefone?",
            "save_as": "telefone",
            "validate_with": "telefone_br",
        },
    ])


def test_make_estado_inicial():
    estado = make_estado_inicial(42, _make_perguntas())
    assert estado["item_id"] == 42
    assert estado["idx"] == 0
    assert estado["respostas"] == {}
    assert len(estado["perguntas"]) == 2
    assert "started_at" in estado


def test_is_em_andamento():
    assert not is_em_andamento(None)
    assert not is_em_andamento({})
    estado = make_estado_inicial(1, _make_perguntas())
    assert is_em_andamento(estado)
    estado["idx"] = 99
    assert not is_em_andamento(estado)


def test_pergunta_atual():
    estado = make_estado_inicial(1, _make_perguntas())
    assert pergunta_atual(estado)["save_as"] == "cpf"
    estado["idx"] = 1
    assert pergunta_atual(estado)["save_as"] == "telefone"
    estado["idx"] = 2
    assert pergunta_atual(estado) is None


def test_avancar_resposta_nao_muta_input():
    estado = make_estado_inicial(1, _make_perguntas())
    novo = avancar_resposta(estado, "cpf", "12345678901")
    assert estado["idx"] == 0
    assert estado["respostas"] == {}
    assert novo["idx"] == 1
    assert novo["respostas"] == {"cpf": "12345678901"}


# ---- Fluxo de validação ----


def test_validar_e_processar_resposta_valida():
    estado = make_estado_inicial(1, _make_perguntas())
    ok, erro, novo = validar_e_processar(estado, "529.982.247-25")  # CPF válido
    assert ok
    assert erro is None
    assert novo["idx"] == 1
    assert novo["respostas"]["cpf"] == "529.982.247-25"


def test_validar_e_processar_resposta_invalida_cpf():
    estado = make_estado_inicial(1, _make_perguntas())
    ok, erro, novo = validar_e_processar(estado, "123")
    assert not ok
    assert "CPF" in erro
    # Estado original NÃO muda em caso de falha
    assert novo["idx"] == 0
    assert novo["respostas"] == {}


def test_validar_e_processar_vazio_obrigatorio():
    estado = make_estado_inicial(1, _make_perguntas())
    ok, erro, novo = validar_e_processar(estado, "")
    assert not ok
    assert erro
    assert novo["idx"] == 0


def test_validar_e_processar_retry_message_customizado():
    perguntas = normalize_perguntas([
        {
            "label": "CPF",
            "save_as": "cpf",
            "validate_with": "cpf",
            "retry_message": "Por favor digite o CPF correto, sem letras.",
        },
    ])
    estado = make_estado_inicial(1, perguntas)
    ok, erro, _ = validar_e_processar(estado, "abc")
    assert not ok
    assert "letras" in erro


def test_validar_e_processar_nao_obrigatorio_aceita_vazio():
    perguntas = normalize_perguntas([
        {"label": "Comentário?", "save_as": "comentario", "obrigatorio": False},
    ])
    estado = make_estado_inicial(1, perguntas)
    ok, erro, novo = validar_e_processar(estado, "")
    assert ok
    assert erro is None
    assert novo["respostas"]["comentario"] == ""


# ---- Templates ----


def test_render_pergunta_label_com_coleta_anterior():
    estado = make_estado_inicial(1, _make_perguntas())
    novo = avancar_resposta(estado, "cpf", "12345678901")
    # ctx é flat: chave "namespace.key" → string
    ctx = build_coleta_render_ctx({"cliente.nome": "João"}, novo["respostas"])
    label = render_pergunta_label(
        "Olá {{cliente.nome}}, seu CPF {{coleta.cpf}} foi recebido.", ctx
    )
    assert "João" in label
    assert "12345678901" in label


def test_render_pergunta_label_sem_template_passa_direto():
    label = render_pergunta_label("Pergunta sem var", {})
    assert label == "Pergunta sem var"


# ---- Resumo final ----


def test_make_resumo_final_estrutura():
    estado = make_estado_inicial(7, _make_perguntas())
    estado = avancar_resposta(estado, "cpf", "12345678901")
    estado = avancar_resposta(estado, "telefone", "67999998888")
    resumo = make_resumo_final(estado, item_label="Agendamento")
    assert resumo["item_id"] == 7
    assert resumo["item_label"] == "Agendamento"
    assert resumo["respostas"]["cpf"]["valor"] == "12345678901"
    assert resumo["respostas"]["cpf"]["label"] == "Qual seu CPF?"
    assert resumo["respostas"]["telefone"]["valor"] == "67999998888"
    assert "completed_at" in resumo


# ---- Fluxo end-to-end (sem worker, sem DB) ----


def test_fluxo_completo_2_perguntas():
    perguntas = _make_perguntas()
    estado = make_estado_inicial(99, perguntas)

    # P1
    p = pergunta_atual(estado)
    assert p["save_as"] == "cpf"
    ok, _err, estado = validar_e_processar(estado, "529.982.247-25")
    assert ok

    # P2
    p = pergunta_atual(estado)
    assert p["save_as"] == "telefone"
    ok, _err, estado = validar_e_processar(estado, "67999998888")
    assert ok

    # Fim do wizard
    assert pergunta_atual(estado) is None
    resumo = make_resumo_final(estado, item_label="Item Teste")
    assert len(resumo["respostas"]) == 2
