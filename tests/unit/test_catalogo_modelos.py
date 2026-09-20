"""Campos derivados do catálogo completo (ADR-004, `shared/catalogo_modelos.py`)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from whatsapp_langchain.shared.catalogo_modelos import montar_item, nome_do_provedor

_AGORA = datetime(2026, 9, 20, tzinfo=UTC)


def _row(**o):
    base = dict(
        slug="google/gemini-2.5-flash",
        nome="Gemini 2.5 Flash",
        descricao="d",
        context_length=1_048_576,
        visao=True,
        pensamento=True,
        tools=True,
        preco_prompt=3e-7,
        preco_completion=2.5e-6,
        criado_no_or=_AGORA - timedelta(days=200),
        curado=True,
    )
    base.update(o)
    return tuple(base.values())


def test_provedor_e_nome_de_exibicao() -> None:
    item = montar_item(_row(), tendencia=set(), agora=_AGORA)
    assert item["provedor"] == "google"
    assert item["provedor_nome"] == "Google"
    assert nome_do_provedor("moonshotai") == "Moonshot AI"
    assert nome_do_provedor("fabricante-x") == "Fabricante-x"


def test_tem_exatamente_as_15_chaves_do_contrato() -> None:
    item = montar_item(_row(), tendencia=set(), agora=_AGORA)
    assert len(item) == 15  # as 15 chaves de `ModeloCatalogo` (ADR-004 §4.8)
    assert item["curado"] is True and item["visao"] is True


def test_novo_e_menos_de_30_dias() -> None:
    recente = montar_item(
        _row(criado_no_or=_AGORA - timedelta(days=5)), tendencia=set(), agora=_AGORA
    )
    antigo = montar_item(
        _row(criado_no_or=_AGORA - timedelta(days=31)), tendencia=set(), agora=_AGORA
    )
    sem_data = montar_item(_row(criado_no_or=None), tendencia=set(), agora=_AGORA)
    assert recente["novo"] is True
    assert antigo["novo"] is False
    assert sem_data["novo"] is False


def test_promo_por_sufixo_free_ou_preco_zero() -> None:
    free = montar_item(_row(slug="x/y:free"), tendencia=set(), agora=_AGORA)
    zero = montar_item(_row(preco_prompt=0.0), tendencia=set(), agora=_AGORA)
    pago = montar_item(_row(), tendencia=set(), agora=_AGORA)
    assert free["promo"] and zero["promo"] and not pago["promo"]


def test_tendencia_e_pertencer_ao_top_do_ranking() -> None:
    em_alta = montar_item(_row(), tendencia={"google/gemini-2.5-flash"}, agora=_AGORA)
    fora = montar_item(_row(), tendencia={"openai/gpt-5"}, agora=_AGORA)
    assert em_alta["tendencia"] is True
    assert fora["tendencia"] is False


def test_preco_desconhecido_fica_none() -> None:
    item = montar_item(
        _row(preco_prompt=None, preco_completion=None), tendencia=set(), agora=_AGORA
    )
    assert item["preco_prompt"] is None
    assert item["promo"] is False
