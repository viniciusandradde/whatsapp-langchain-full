"""Regra de quem pode editar/apagar mensagem já entregue (mig 172).

Função pura, então roda no CI sem banco e sem rede — e é onde mora o miolo
da feature. Cada teste aqui corresponde a um jeito de o operador ficar sem a
opção no menu, e a um 400 na rota.
"""

from __future__ import annotations

from whatsapp_langchain.shared.atendimento import (
    JANELA_APAGAR_SEG,
    JANELA_EDICAO_SEG,
    avaliar_alteracao_resposta,
)

#: Mensagem que o operador acabou de mandar por uma conexão Evolution — o
#: único caso em que tudo é permitido. Os testes variam UM campo por vez.
BASE = dict(
    message_id="3EB0C767D097C4A1B2",
    normalized_input="manual:user-123",
    provider="evolution",
    interna=False,
    tem_midia=False,
    apagada=False,
    idade_seg=10.0,
)


def _avaliar(**mudancas):
    return avaliar_alteracao_resposta(**{**BASE, **mudancas})


def test_mensagem_recem_enviada_permite_tudo() -> None:
    assert _avaliar() == (True, True)


def test_sem_chave_do_provedor_nao_permite_nada() -> None:
    # É o caso das respostas da IA: o worker descarta o retorno do envio, então
    # não há o que endereçar no WhatsApp.
    assert _avaliar(message_id=None) == (False, False)


def test_chave_de_mock_nao_permite_nada() -> None:
    # Ambiente sem envio real. Oferecer a ação prometeria algo que falha.
    assert _avaliar(message_id="mock-evo-abc123") == (False, False)


def test_mensagem_do_agente_nao_permite_nada() -> None:
    assert _avaliar(normalized_input="agente") == (False, False)
    assert _avaliar(normalized_input=None) == (False, False)


def test_mensagem_do_sistema_nao_permite_nada() -> None:
    # `manual:system:` é aviso montado pelo sistema (transferência etc.):
    # ninguém "errou de digitar" isso.
    assert _avaliar(normalized_input="manual:system:transfer") == (False, False)


def test_waba_nao_permite_nada() -> None:
    # Verificado no binário da Evolution v2.3.7: o canal oficial da Meta recusa
    # as duas operações com "Method not available on WhatsApp Business API".
    assert _avaliar(provider="waba") == (False, False)
    assert _avaliar(provider=None) == (False, False)


def test_nota_interna_nao_permite_nada() -> None:
    # Nunca foi ao cliente — não há mensagem no WhatsApp pra alterar.
    assert _avaliar(interna=True) == (False, False)


def test_midia_nao_permite_nada() -> None:
    assert _avaliar(tem_midia=True) == (False, False)


def test_ja_apagada_nao_permite_nada() -> None:
    assert _avaliar(apagada=True) == (False, False)


def test_passados_15_minutos_so_permite_apagar() -> None:
    # O caso que motivou incluir "apagar": passou a janela de edição do
    # WhatsApp, mas ainda dá pra remover.
    assert _avaliar(idade_seg=JANELA_EDICAO_SEG + 1) == (False, True)


def test_borda_da_janela_de_edicao() -> None:
    assert _avaliar(idade_seg=JANELA_EDICAO_SEG - 1)[0] is True
    assert _avaliar(idade_seg=float(JANELA_EDICAO_SEG))[0] is False


def test_passadas_48_horas_nao_permite_nada() -> None:
    assert _avaliar(idade_seg=JANELA_APAGAR_SEG + 1) == (False, False)


def test_sem_idade_nao_permite_nada() -> None:
    # Linha sem `created_at` não deveria existir, mas se existir a resposta
    # segura é "não dá" — não "dá pra sempre".
    assert _avaliar(idade_seg=None) == (False, False)
