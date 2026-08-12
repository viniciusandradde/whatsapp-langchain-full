"""Partes puras do relatório de uso: competência, rótulos e agendamento.

As consultas em si são exercitadas no E2E (precisam de banco). Aqui fica o que
dá pra provar sem infraestrutura — e é onde moram os erros de calendário, que
só aparecem uma vez por ano se ninguém testar.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time

import pytest

from whatsapp_langchain.shared.relatorio_uso import (
    AgendaUso,
    Competencia,
    deve_enviar_mensal,
    rotulo_de_formato,
)


class TestCompetencia:
    def test_rotulo_vira_mes(self):
        c = Competencia.de_rotulo("2026-07")
        assert (c.ano, c.mes) == (2026, 7)
        assert c.rotulo == "2026-07"

    def test_primeiro_e_ultimo_dia(self):
        c = Competencia(2026, 7)
        assert c.inicio == date(2026, 7, 1)
        assert c.fim == date(2026, 7, 31)

    def test_fevereiro_bissexto_tem_29(self):
        """2028 é bissexto. Um `fim = dia 28` fixo perderia um dia de dados."""
        assert Competencia(2028, 2).fim == date(2028, 2, 29)
        assert Competencia(2026, 2).fim == date(2026, 2, 28)

    @pytest.mark.parametrize("ruim", ["2026-13", "2026-00", "1999-05", "abacaxi-07"])
    def test_rotulo_invalido_e_recusado(self, ruim):
        with pytest.raises(ValueError):
            Competencia.de_rotulo(ruim)

    def test_mes_anterior_no_meio_do_ano(self):
        assert Competencia.mes_anterior(date(2026, 8, 12)).rotulo == "2026-07"

    def test_mes_anterior_em_janeiro_volta_o_ano(self):
        """O envio do dia 1º de janeiro manda DEZEMBRO do ano passado."""
        assert Competencia.mes_anterior(date(2027, 1, 1)).rotulo == "2026-12"

    def test_mes_corrente_e_parcial(self):
        c = Competencia(2026, 8)
        assert c.parcial_em(date(2026, 8, 12)) is True
        assert c.parcial_em(date(2026, 9, 1)) is False

    def test_mes_fechado_nunca_e_parcial(self):
        assert Competencia(2026, 7).parcial_em(date(2026, 8, 12)) is False


class TestRotuloDeFormato:
    @pytest.mark.parametrize(
        ("mime", "esperado"),
        [
            ("audio/ogg; codecs=opus", "Áudio — nota de voz"),
            ("image/jpeg", "Imagem — foto"),
            ("application/pdf", "PDF"),
            ("video/mp4", "Vídeo"),
            (
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                "Word",
            ),
            ("application/msword", "Word"),
            (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "Planilha Excel",
            ),
        ],
    )
    def test_mimes_reais_de_producao(self, mime, esperado):
        assert rotulo_de_formato(mime) == esperado

    def test_doc_e_docx_caem_na_mesma_linha(self):
        """São mimes diferentes do mesmo formato para quem lê o relatório."""
        assert rotulo_de_formato("application/msword") == rotulo_de_formato(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )

    def test_desconhecido_vira_outro_em_vez_de_sumir(self):
        assert rotulo_de_formato("application/x-coisa-nova") == "Outro"
        assert rotulo_de_formato(None) == "Outro"


class TestDeveEnviarMensal:
    def _agenda(self, **kw) -> AgendaUso:
        base = {
            "empresa_id": 1,
            "telefone": "+5567999068963",
            "dia": 1,
            "horario": time(9, 0),
            "tz": "America/Campo_Grande",
            "last_sent": None,
        }
        return AgendaUso(**{**base, **kw})

    def test_no_dia_e_depois_da_hora_envia(self):
        # 01/08 12:00 UTC = 08:00 local... ainda não. 14:00 UTC = 10:00 local.
        agora = datetime(2026, 8, 1, 14, 0, tzinfo=UTC)
        assert deve_enviar_mensal(self._agenda(), agora) is True

    def test_no_dia_antes_da_hora_espera(self):
        agora = datetime(2026, 8, 1, 11, 0, tzinfo=UTC)  # 07:00 local
        assert deve_enviar_mensal(self._agenda(), agora) is False

    def test_antes_do_dia_marcado_espera(self):
        agora = datetime(2026, 8, 3, 14, 0, tzinfo=UTC)
        assert deve_enviar_mensal(self._agenda(dia=5), agora) is False

    def test_depois_do_dia_marcado_ainda_envia(self):
        """Worker parado no dia 1 não pode fazer a competência ser perdida."""
        agora = datetime(2026, 8, 9, 14, 0, tzinfo=UTC)
        assert deve_enviar_mensal(self._agenda(), agora) is True

    def test_competencia_ja_enviada_nao_repete(self):
        agora = datetime(2026, 8, 9, 14, 0, tzinfo=UTC)
        agenda = self._agenda(last_sent=date(2026, 7, 1))  # julho já foi
        assert deve_enviar_mensal(agenda, agora) is False

    def test_competencia_antiga_nao_bloqueia_a_nova(self):
        """Junho enviado não impede julho."""
        agora = datetime(2026, 8, 9, 14, 0, tzinfo=UTC)
        agenda = self._agenda(last_sent=date(2026, 6, 1))
        assert deve_enviar_mensal(agenda, agora) is True

    def test_tz_invalida_nao_trava_o_laco(self):
        """Fuso digitado errado no cadastro cai no padrão em vez de explodir."""
        agora = datetime(2026, 8, 1, 14, 0, tzinfo=UTC)
        assert deve_enviar_mensal(self._agenda(tz="Marte/Olympus"), agora) is True
