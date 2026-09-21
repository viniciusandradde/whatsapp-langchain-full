"""Regras puras da vigência do plano (ADR-005 leva E) — sem banco."""

from __future__ import annotations

from datetime import UTC, date, datetime

from whatsapp_langchain.shared.plano_vigencia import (
    CARENCIA_DIAS,
    EmpresaVigencia,
    carencia_ate,
    dentro_da_janela,
    deve_rebaixar,
    dias_para_vencer,
    etapa_devida,
    etapa_ja_enviada,
    hoje_local,
    texto_aviso_cliente,
    texto_aviso_plataforma,
)


def _empresa(**kw) -> EmpresaVigencia:
    base = dict(
        id=1018,
        nome="Luis Fernando",
        plano_slug="pro",
        plano_nome="Pro",
        valido_ate=date(2026, 9, 30),
        tz="America/Campo_Grande",
        telefone="+5567999990000",
        etapa=None,
        etapa_ref=None,
    )
    base.update(kw)
    return EmpresaVigencia(**base)


def test_etapa_devida_por_dias():
    assert etapa_devida(30) is None
    assert etapa_devida(8) is None
    assert etapa_devida(7) == "d7"
    assert etapa_devida(4) == "d7"
    assert etapa_devida(3) == "d3"
    assert etapa_devida(1) == "d3"
    assert etapa_devida(0) == "d0"
    assert etapa_devida(-4) == "d0"  # na carência, ainda é "venceu"


def test_rebaixa_so_depois_da_carencia():
    assert CARENCIA_DIAS == 5
    assert not deve_rebaixar(0)
    assert not deve_rebaixar(-5)  # último dia da carência
    assert deve_rebaixar(-6)
    assert carencia_ate(date(2026, 9, 30)) == date(2026, 10, 5)


def test_dias_para_vencer_e_hoje_local():
    hoje = date(2026, 9, 23)
    assert dias_para_vencer(date(2026, 9, 30), hoje) == 7
    assert dias_para_vencer(date(2026, 9, 23), hoje) == 0
    assert dias_para_vencer(date(2026, 9, 20), hoje) == -3
    # 02:00 UTC ainda é o dia anterior em Campo Grande (UTC-4).
    assert hoje_local(
        "America/Campo_Grande", datetime(2026, 9, 24, 2, 0, tzinfo=UTC)
    ) == date(2026, 9, 23)
    # tz inválida no cadastro cai no padrão em vez de derrubar o job
    assert hoje_local(
        "Marte/Olympus", datetime(2026, 9, 24, 12, 0, tzinfo=UTC)
    ) == date(2026, 9, 24)


def test_janela_comercial_local():
    # 11:00 UTC = 07:00 em Campo Grande → fora; 12:00 UTC = 08:00 → dentro
    assert not dentro_da_janela(
        "America/Campo_Grande", datetime(2026, 9, 24, 11, 0, tzinfo=UTC)
    )
    assert dentro_da_janela(
        "America/Campo_Grande", datetime(2026, 9, 24, 12, 0, tzinfo=UTC)
    )
    # 00:00 UTC = 20:00 → fora (janela é [8, 20))
    assert not dentro_da_janela(
        "America/Campo_Grande", datetime(2026, 9, 25, 0, 0, tzinfo=UTC)
    )


def test_etapa_ja_enviada_respeita_a_data_de_referencia():
    hoje_ref = date(2026, 9, 30)
    assert not etapa_ja_enviada(None, None, hoje_ref, "d7")
    assert etapa_ja_enviada("d7", hoje_ref, hoje_ref, "d7")
    # etapa posterior cobre a anterior
    assert etapa_ja_enviada("d3", hoje_ref, hoje_ref, "d7")
    assert not etapa_ja_enviada("d7", hoje_ref, hoje_ref, "d3")
    # renovou: a etapa gravada é de OUTRA data → volta a avisar
    assert not etapa_ja_enviada("d0", date(2026, 8, 31), hoje_ref, "d7")


def test_textos_sem_termo_tecnico():
    e = _empresa()
    for etapa in ("d7", "d3", "d0", "rebaixado"):
        cliente = texto_aviso_cliente(etapa, e)
        plataforma = texto_aviso_plataforma(etapa, e)
        for txt in (cliente, plataforma):
            assert "_" not in txt, txt
            assert " pra " not in txt and " pro " not in txt, txt
        assert "30/09/2026" in cliente
        assert "Pro" in cliente and "Luis Fernando" in cliente
    assert "05/10/2026" in texto_aviso_cliente("d0", e)  # fim da carência
    assert "Free" in texto_aviso_cliente("rebaixado", e)
    assert "id 1018" in texto_aviso_plataforma("d3", e)
