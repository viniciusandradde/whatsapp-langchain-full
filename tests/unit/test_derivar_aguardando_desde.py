"""Contrato do `derivar_aguardando_desde` (inbox agrupado 2026-09).

O chip "Sem resposta há X" do card só pode acender quando o CLIENTE foi o
último a falar e ninguém respondeu de verdade. Cada teste é uma dessas
fronteiras: resposta real apaga; marker interno do worker NÃO conta como
resposta; row de saída do composer não é fala do cliente; mídia conta dos
dois lados.
"""

from __future__ import annotations

from datetime import UTC, datetime

from whatsapp_langchain.shared.atendimento import (
    MARKERS_INTERNOS,
    derivar_aguardando_desde,
)

_T = datetime(2026, 9, 18, 14, 30, tzinfo=UTC)


def _desde(**kwargs):
    base = {
        "incoming_message": None,
        "tem_media": False,
        "response": None,
        "tem_response_media": False,
        "created_at": _T,
    }
    base.update(kwargs)
    return derivar_aguardando_desde(**base)


class TestPendente:
    def test_cliente_falou_e_ninguem_respondeu(self) -> None:
        assert _desde(incoming_message="preciso de ajuda") == _T

    def test_response_vazio_tambem_e_sem_resposta(self) -> None:
        assert _desde(incoming_message="oi", response="") == _T

    def test_midia_do_cliente_sem_texto_conta_como_fala(self) -> None:
        assert _desde(tem_media=True) == _T

    def test_marker_interno_nao_e_resposta(self) -> None:
        """`[modo manual …]`, `[fila do departamento …]` etc. nunca chegaram ao
        cliente — ele continua esperando desde a própria mensagem."""
        for marker in MARKERS_INTERNOS:
            assert _desde(incoming_message="oi", response=f"{marker} x]") == _T, marker


class TestRespondida:
    def test_resposta_real_apaga(self) -> None:
        assert _desde(incoming_message="oi", response="Bom dia! Como ajudo?") is None

    def test_midia_do_operador_apaga(self) -> None:
        assert _desde(incoming_message="oi", tem_response_media=True) is None

    def test_row_de_saida_do_composer_nao_e_fala_do_cliente(self) -> None:
        """O envio manual grava `incoming_message=""` + `response`."""
        assert _desde(incoming_message="", response="Segue o boleto") is None

    def test_row_vazia_vira_none(self) -> None:
        assert _desde() is None

    def test_sem_created_at_vira_none(self) -> None:
        assert _desde(incoming_message="oi", created_at=None) is None
