"""A IA precisa sair da conversa depois de transferir pro departamento.

Incidente 2026-07-27, atendimento 506:

    21:37:14  IA:      "Sua mensagem já está com o Luis Fernando..."
    21:37:25  SISTEMA: "transferido para o departamento de *Atendimento*..."
    21:38:41  IA:      "Sua mensagem já está com o Luis Fernando..."   ← voltou

O prompt já mandava parar ("PARE. Não escreva mais nada nessa conversa") e a
tool funcionava. Mas quem reinvoca o agente é o WORKER, na mensagem seguinte —
e o gate dele só reconhecia "humano assumiu" (`em_andamento` +
`assigned_to_user_id`), enquanto a transferência deixa `aguardando` +
`assigned=NULL`. Nenhum ajuste de prompt alcançava isso.
"""

from __future__ import annotations

import pytest

from whatsapp_langchain.shared.atendimento import MARKERS_REPROCESSAVEIS
from whatsapp_langchain.worker.processor import (
    FILA_DEPARTAMENTO_MARKER,
    HANDOFF_HUMANO_MARKER,
    MODO_MANUAL_MARKER,
    WHITELIST_BYPASS_MARKER,
)


def _na_fila(status: str, departamento_id: int | None, assigned: str | None) -> bool:
    """Espelha o gate de `worker/processor.py` sem subir o worker inteiro."""
    return status == "aguardando" and departamento_id is not None and not assigned


class TestGateFilaDepartamento:
    def test_transferido_e_sem_atendente_pula_a_ia(self) -> None:
        """O caso do incidente: fila vazia, ninguém puxou ainda."""
        assert _na_fila("aguardando", 999011, None) is True

    def test_atendimento_novo_continua_indo_pra_ia(self) -> None:
        """A regressão mais cara possível: `aguardando` sozinho é ambíguo.

        Atendimento novo também nasce `aguardando`. Sem exigir
        `departamento_id`, TODA conversa nova pararia de ser respondida.
        """
        assert _na_fila("aguardando", None, None) is False

    def test_atendente_puxou_nao_e_fila(self) -> None:
        """Aí o gate de handoff (que já existia) assume."""
        assert _na_fila("em_andamento", 999011, "user-123") is False

    def test_aguardando_com_depto_mas_ja_atribuido(self) -> None:
        """Claim automático do `pick_best_atendente` — não é mais fila."""
        assert _na_fila("aguardando", 999011, "user-123") is False

    def test_resolvido_nao_e_fila(self) -> None:
        assert _na_fila("resolvido", 999011, None) is False

    @pytest.mark.parametrize("assigned", ["", None])
    def test_assigned_vazio_conta_como_sem_atendente(
        self, assigned: str | None
    ) -> None:
        """String vazia no banco não pode passar por 'tem atendente'."""
        assert _na_fila("aguardando", 999011, assigned) is True


class TestInterruptorIaNaFila:
    """Mig 166 — o silêncio da fila vira opcional, por departamento.

    Medido na empresa 1018 em 12/08/2026: 465 mensagens sem resposta nenhuma em
    7 dias, porque a fila de destino não é trabalhada por ninguém (0 assumidos,
    0 mensagens de operador, 61 abandonados). O gate acima estava certo para
    fila com gente e errado para caixa de entrada de uma pessoa só.
    """

    @staticmethod
    def _cala_a_ia(
        status: str,
        departamento_id: int | None,
        assigned: str | None,
        ia_continua_na_fila: bool,
    ) -> bool:
        """Espelha o gate com o interruptor, como está no processor."""
        return _na_fila(status, departamento_id, assigned) and not ia_continua_na_fila

    def test_interruptor_desligado_mantem_o_silencio(self) -> None:
        """Default FALSE: quem já usa não sente diferença nenhuma."""
        assert self._cala_a_ia("aguardando", 999011, None, False) is True

    def test_interruptor_ligado_devolve_a_conversa_pra_ia(self) -> None:
        assert self._cala_a_ia("aguardando", 999011, None, True) is False

    def test_handoff_vence_o_interruptor(self) -> None:
        """A garantia que torna o interruptor seguro de ligar.

        Assim que um atendente assume de fato, a IA cala mesmo com o
        interruptor ligado — senão ela falaria por cima do humano.
        """
        assert self._cala_a_ia("em_andamento", 999011, "user-123", True) is False
        assert _na_fila("em_andamento", 999011, "user-123") is False

    def test_atendimento_novo_segue_indo_pra_ia_nos_dois_modos(self) -> None:
        for ligado in (True, False):
            assert self._cala_a_ia("aguardando", None, None, ligado) is False


class TestColunaIaNaFila:
    def test_campo_existe_no_modelo(self) -> None:
        from whatsapp_langchain.shared.models import Departamento, DepartamentoInput

        assert "ia_continua_na_fila" in Departamento.model_fields
        assert "ia_continua_na_fila" in DepartamentoInput.model_fields

    def test_default_e_desligado(self) -> None:
        """Ligar é decisão de quem opera a fila, nunca padrão do sistema."""
        from whatsapp_langchain.shared.models import DepartamentoInput

        assert DepartamentoInput(nome="Suporte").ia_continua_na_fila is False

    def test_indice_da_coluna_bate_com_o_select(self) -> None:
        """`_row_to_departamento` lê por ÍNDICE — coluna nova no meio do
        `_SELECT_COLS` faria a flag ler o valor do vizinho, calada."""
        from datetime import UTC, datetime

        from whatsapp_langchain.shared import departamento as m

        colunas = [c.strip() for c in m._SELECT_COLS.split(",")]
        assert colunas.index("ia_continua_na_fila") == 9

        agora = datetime.now(UTC)
        row = (7, 1018, "Atendimento", None, True, None, agora, agora, None, True)
        assert len(row) == len(colunas)
        assert m._row_to_departamento(row).ia_continua_na_fila is True

    def test_row_curta_nao_quebra(self) -> None:
        """Chamadas antigas passam tupla sem a coluna — não podem estourar."""
        from datetime import UTC, datetime

        from whatsapp_langchain.shared import departamento as m

        agora = datetime.now(UTC)
        curta = (7, 1018, "Atendimento", None, True, None, agora, agora)
        assert m._row_to_departamento(curta).ia_continua_na_fila is False


class TestGuardaReencaminhamento:
    """Com a IA ativa na fila, transferir vira operação repetível — e cara.

    Cada chamada de `transfer_to_human` grava linha em
    `atendimento_transferencia`, anota no cliente, manda aviso oficial no
    WhatsApp e dispara hook. Sem guarda, isso se repetiria a cada mensagem.
    """

    @staticmethod
    def _ja_encaminhado(
        depto_do_atendimento: int | None,
        depto_destino: int,
        status: str,
        assigned: str | None,
    ) -> bool:
        return (
            depto_do_atendimento == depto_destino
            and status == "aguardando"
            and not assigned
        )

    def test_mesma_fila_nao_reencaminha(self) -> None:
        assert self._ja_encaminhado(999011, 999011, "aguardando", None) is True

    def test_primeira_transferencia_passa(self) -> None:
        assert self._ja_encaminhado(None, 999011, "aguardando", None) is False

    def test_outro_departamento_passa(self) -> None:
        """Triagem pode corrigir o destino — isso não é reencaminhar."""
        assert self._ja_encaminhado(999012, 999011, "aguardando", None) is False

    def test_atendente_assumiu_nao_e_fila(self) -> None:
        assert self._ja_encaminhado(999011, 999011, "em_andamento", "user-1") is False


class TestMarker:
    def test_marker_e_distinto_dos_outros(self) -> None:
        outros = {MODO_MANUAL_MARKER, WHITELIST_BYPASS_MARKER, HANDOFF_HUMANO_MARKER}

        assert FILA_DEPARTAMENTO_MARKER not in outros

    def test_marker_segue_o_padrao_de_colchete(self) -> None:
        """O drawer filtra por prefixo `[` — fora do padrão vira bolha."""
        assert FILA_DEPARTAMENTO_MARKER.startswith("[")

    def test_fila_nao_e_reprocessavel(self) -> None:
        """Ficar na fila é intencional, não falha.

        Se entrasse em MARKERS_REPROCESSAVEIS (mig 142), o botão de
        reprocessar traria a IA de volta por cima da espera pelo humano.
        """
        assert not any(
            FILA_DEPARTAMENTO_MARKER.startswith(m) for m in MARKERS_REPROCESSAVEIS
        )


class TestFlagAnuncioTransferencia:
    """Agente pessoal não fala 'departamento de Atendimento' com o cliente."""

    def test_campo_existe_no_dataclass(self) -> None:
        import dataclasses

        from whatsapp_langchain.shared.agente import AgenteIA

        nomes = {f.name for f in dataclasses.fields(AgenteIA)}
        assert "anuncia_transferencia" in nomes

    def test_select_alinha_com_o_dataclass(self) -> None:
        """`_row_to_agente` faz `AgenteIA(*row)` — mapeamento POSICIONAL.

        Coluna inserida no `_COLS` sem o campo correspondente na mesma
        posição do dataclass atribui valores trocados em silêncio. Este teste
        é a única coisa entre isso e produção.
        """
        import dataclasses

        from whatsapp_langchain.shared import agente as m

        colunas = [c.strip() for c in m._COLS.split(",") if c.strip()]
        campos = [f.name for f in dataclasses.fields(m.AgenteIA)]

        assert colunas == campos, (
            "ordem de _COLS divergiu do dataclass AgenteIA — "
            "AgenteIA(*row) atribuiria campos trocados"
        )
