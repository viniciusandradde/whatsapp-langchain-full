"""Guarda robô × robô (`shared/conversa_automatica.py`) — regras puras.

Caso real que motivou (empresa 1018, 14/09/2026 15:31–15:33): a URA do
Santander (+55 11 4004-3535) respondendo em segundos ao agente do Luis.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from whatsapp_langchain.shared.conversa_automatica import (
    CONVERSA_AUTOMATICA_MARKER,
    IMEDIATA_S,
    LONGA_MIN_CHARS,
    MIN_SINAIS,
    Recebida,
    avaliar,
    numero_corporativo,
    parece_menu_automatico,
    sinal_da_mensagem,
)

T0 = datetime(2026, 9, 14, 18, 31, 46, tzinfo=UTC)


def _r(texto: str, seg: float, resposta_ha: float | None = 5.0) -> Recebida:
    """Recebida `seg` s depois de T0, com a nossa resposta `resposta_ha` s antes."""
    em = T0 + timedelta(seconds=seg)
    return Recebida(
        texto=texto,
        recebida_em=em,
        resposta_anterior_em=(
            em - timedelta(seconds=resposta_ha) if resposta_ha is not None else None
        ),
    )


# --- vocabulário de URA -----------------------------------------------------


def test_parece_menu_pega_as_frases_do_santander():
    assert parece_menu_automatico(
        "Por segurança, este *telefone ainda não está habilitado* aqui no Whatsapp Santander."
    )
    assert parece_menu_automatico(
        "Você não escolheu uma das opções disponíveis. Vamos tentar de novo?"
    )
    assert parece_menu_automatico(
        "Não é possível continuar, a quantidade máxima de tentativas foram atingidas."
    )
    assert parece_menu_automatico("Olá! Sou a assistente virtual da Vivo.")
    assert parece_menu_automatico("Digite 1 para boletos\n2 - Cartões")
    assert parece_menu_automatico("1 - Boletos\n2 - Cartões\n3 - Atendente")


def test_parece_menu_ignora_fala_humana():
    for t in (
        "Bom dia professor Beleza",
        "preciso o nome completo de quem fará a fala no evento de quinta feira",
        "para continuar o tratamento preciso da receita",
        "Se precisar estarei aqui. Até a próxima.😀",
        "oiee",
        "",
    ):
        assert not parece_menu_automatico(t), t


def test_numero_corporativo():
    assert numero_corporativo("+551140043535")  # Santander
    assert numero_corporativo("+551130031234")
    assert numero_corporativo("+558001234567")  # 0800 em E.164
    assert not numero_corporativo("+5567999641878")
    assert not numero_corporativo("+5511300312345")  # 9 dígitos após o DDD
    assert not numero_corporativo("")


# --- sinais por mensagem ----------------------------------------------------


def test_menu_so_conta_se_imediato_ou_corporativo():
    menu = "Você não escolheu uma das opções disponíveis."
    assert (
        sinal_da_mensagem(_r(menu, 0, resposta_ha=5), set(), corporativo=False)
        == "menu"
    )
    # humano encaminhando print do banco 2 min depois da resposta: não conta
    assert (
        sinal_da_mensagem(_r(menu, 0, resposta_ha=120), set(), corporativo=False)
        is None
    )
    # ...mas de número corporativo conta sem olhar o relógio
    assert (
        sinal_da_mensagem(_r(menu, 0, resposta_ha=120), set(), corporativo=True)
        == "menu"
    )
    # sem resposta nossa antes (primeira mensagem da conversa): só corporativo
    assert (
        sinal_da_mensagem(_r(menu, 0, resposta_ha=None), set(), corporativo=False)
        is None
    )


def test_tempo_sem_padrao_nunca_conta():
    # Larissa manda "ok" 3 s depois da resposta dez vezes por dia
    assert (
        sinal_da_mensagem(_r("ok", 0, resposta_ha=3), set(), corporativo=False) is None
    )
    assert (
        sinal_da_mensagem(_r("oiee", 0, resposta_ha=1), {"oiee"}, corporativo=False)
        is None
    )


def test_texto_repetido_longo_e_imediato():
    menu = "Bem-vindo ao atendimento. Escolha o produto desejado abaixo."
    vistos = {menu.lower()}
    assert (
        sinal_da_mensagem(_r(menu, 0, resposta_ha=4), vistos, corporativo=False)
        == "repetida"
    )
    # mesmo texto, mas 2 min depois: humano reenviando
    assert (
        sinal_da_mensagem(_r(menu, 0, resposta_ha=120), vistos, corporativo=False)
        is None
    )


def test_longa_e_imediata_pega_ia_x_ia():
    longa = "x" * LONGA_MIN_CHARS
    assert (
        sinal_da_mensagem(_r(longa, 0, resposta_ha=6), set(), corporativo=False)
        == "longa_imediata"
    )
    assert (
        sinal_da_mensagem(
            _r(longa, 0, resposta_ha=IMEDIATA_S), set(), corporativo=False
        )
        is None
    )
    assert (
        sinal_da_mensagem(_r("x" * 80, 0, resposta_ha=2), set(), corporativo=False)
        is None
    )


# --- veredito da conversa ----------------------------------------------------


def test_caso_santander_suspende_na_terceira_mensagem():
    hist = [
        _r(
            "Cartão online bloqueado! Você precisa gerar um novo Cartão Online.",
            0,
            resposta_ha=None,
        ),
        _r(
            "Por segurança, este *telefone ainda não está habilitado* aqui no Whatsapp Santander.",
            17,
            resposta_ha=8,
        ),
    ]
    atual = _r(
        "Você não escolheu uma das opções disponíveis. Vamos tentar de novo?",
        32,
        resposta_ha=9,
    )
    v = avaliar(hist, atual, corporativo=True)
    assert v.suspender and v.sinais == ("menu", "menu")
    # sem o número corporativo, o mesmo relógio (≤ 20 s) decide igual
    assert avaliar(hist, atual, corporativo=False).suspender


def test_um_sinal_so_nao_suspende():
    atual = _r(
        "Olá! Sou a assistente virtual da Vivo. Como posso ajudar?", 0, resposta_ha=3
    )
    v = avaliar([], atual, corporativo=False)
    assert not v.suspender and v.sinais == ("menu",)
    assert MIN_SINAIS == 2


def test_conversa_humana_rapida_nao_suspende():
    hist = [
        _r("oiee", 0, resposta_ha=2),
        _r("tudo bem?", 5, resposta_ha=2),
        _r("oiee", 9, resposta_ha=1),
    ]
    v = avaliar(hist, _r("me passa o valor", 12, resposta_ha=1), corporativo=False)
    assert not v.suspender and v.sinais == ()


def test_marcador_sem_termo_tecnico():
    assert CONVERSA_AUTOMATICA_MARKER.startswith("[conversa automática")
    assert "_" not in CONVERSA_AUTOMATICA_MARKER
    assert (
        " pra " not in CONVERSA_AUTOMATICA_MARKER
        and " pro " not in CONVERSA_AUTOMATICA_MARKER
    )
