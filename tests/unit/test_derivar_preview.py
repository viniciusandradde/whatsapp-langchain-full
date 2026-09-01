"""Contrato do `derivar_preview` (leva fila 2026-08).

O que está em jogo: o card da fila NUNCA pode vazar conteúdo que o cliente
não recebeu (markers internos do worker) nem afirmar entrega de mensagem
apagada. Cada teste aqui é uma dessas garantias, não cobertura decorativa.
"""

from __future__ import annotations

from whatsapp_langchain.shared.atendimento import (
    MARKERS_INTERNOS,
    derivar_preview,
)


def _preview(**kwargs):
    base = {
        "incoming_message": None,
        "response": None,
        "response_apagada": False,
        "tem_media": False,
        "media_type": None,
        "tem_response_media": False,
        "response_media_type": None,
    }
    base.update(kwargs)
    return derivar_preview(**base)


class TestConteudo:
    def test_resposta_vence_o_inbound(self) -> None:
        assert (
            _preview(incoming_message="oi", response="Bom dia! Como ajudo?")
            == "Bom dia! Como ajudo?"
        )

    def test_sem_resposta_mostra_inbound(self) -> None:
        assert _preview(incoming_message="preciso de ajuda") == "preciso de ajuda"

    def test_vazio_vira_none(self) -> None:
        assert _preview() is None

    def test_trunca_e_compacta_whitespace(self) -> None:
        longa = "linha um\n\nlinha dois   " + "x" * 200
        out = _preview(incoming_message=longa)
        assert out is not None
        assert len(out) <= 120
        assert "\n" not in out
        assert out.endswith("…")


class TestMarkersInternos:
    def test_nenhum_marker_vaza(self) -> None:
        """Marker no response não é resposta — cai pro texto do cliente."""
        for marker in MARKERS_INTERNOS:
            out = _preview(
                incoming_message="mensagem do cliente",
                response=f"{marker} — detalhe interno]",
            )
            assert out == "mensagem do cliente", marker

    def test_marker_sem_inbound_vira_none(self) -> None:
        assert _preview(response="[modo manual — IA desligada]") is None


class TestApagada:
    def test_apagada_nao_afirma_entrega(self) -> None:
        assert (
            _preview(response="segredo enviado errado", response_apagada=True)
            == "Mensagem apagada"
        )

    def test_apagada_de_midia(self) -> None:
        assert (
            _preview(tem_response_media=True, response_apagada=True)
            == "Mensagem apagada"
        )


class TestMidia:
    def test_midia_inbound_vira_rotulo(self) -> None:
        assert _preview(tem_media=True, media_type="audio/ogg") == "📎 áudio"

    def test_midia_com_legenda(self) -> None:
        assert (
            _preview(
                tem_media=True, media_type="image/jpeg", incoming_message="olha isso"
            )
            == "📎 imagem — olha isso"
        )

    def test_midia_do_operador(self) -> None:
        assert (
            _preview(tem_response_media=True, response_media_type="application/pdf")
            == "📎 documento"
        )

    def test_tipo_desconhecido_vira_anexo(self) -> None:
        assert _preview(tem_media=True, media_type="application/zip") == "📎 anexo"
