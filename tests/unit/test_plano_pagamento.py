"""Regras puras da cobrança por planos hospedados (ADR-005 leva F) — sem banco."""

from __future__ import annotations

from datetime import date

import pytest

from whatsapp_langchain.shared.plano_pagamento import (
    PagamentoInvalidoError,
    proximo_periodo,
    somar_um_mes,
    texto_confirmacao_pagamento,
    validar_link,
)


def test_somar_um_mes_trava_no_ultimo_dia():
    assert somar_um_mes(date(2026, 1, 31)) == date(2026, 2, 28)
    assert somar_um_mes(date(2026, 3, 15)) == date(2026, 4, 15)
    assert somar_um_mes(date(2026, 12, 5)) == date(2027, 1, 5)
    assert somar_um_mes(date(2028, 1, 31)) == date(2028, 2, 29)  # bissexto


def test_proximo_periodo_emenda_na_vigencia_ou_comeca_hoje():
    hoje = date(2026, 9, 21)
    # sem vigência: começa hoje, um mês, fim inclusive
    assert proximo_periodo(None, hoje) == (date(2026, 9, 21), date(2026, 10, 20))
    # vigente até 30/09: o próximo começa em 01/10
    assert proximo_periodo(date(2026, 9, 30), hoje) == (
        date(2026, 10, 1),
        date(2026, 10, 31),
    )
    # vencida: não "devolve" os dias perdidos — começa hoje
    assert proximo_periodo(date(2026, 9, 10), hoje) == (
        date(2026, 9, 21),
        date(2026, 10, 20),
    )


def test_validar_link_exige_https_e_dominio_do_gateway():
    assert validar_link("infinitepay", None) is None
    assert validar_link("infinitepay", "   ") is None
    assert (
        validar_link("infinitepay", " https://pay.infinitepay.io/vsa/plano-pro ")
        == "https://pay.infinitepay.io/vsa/plano-pro"
    )
    assert (
        validar_link(
            "mercadopago", "https://www.mercadopago.com.br/subscriptions/checkout?x=1"
        )
        == "https://www.mercadopago.com.br/subscriptions/checkout?x=1"
    )
    assert validar_link("mercadopago", "https://mpago.la/abc") == "https://mpago.la/abc"
    for ruim in (
        "http://pay.infinitepay.io/x",  # sem TLS
        "https://infinitepay.io.golpe.com/x",  # sufixo falso
        "javascript:alert(1)",
        "https://mercadopago.com.br/x",  # link do MP no campo da InfinitePay
    ):
        with pytest.raises(PagamentoInvalidoError):
            validar_link("infinitepay", ruim)


def test_texto_de_confirmacao_sem_termo_tecnico():
    t = texto_confirmacao_pagamento("Luis Fernando", "Pro", date(2026, 10, 31))
    assert "31/10/2026" in t and "Pro" in t and "Luis Fernando" in t
    assert "_" not in t and " pra " not in t
