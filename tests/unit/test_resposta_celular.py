"""ADR-008 (mig 205): resposta do dono pelo celular pausa a IA — regras puras."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from whatsapp_langchain.shared.resposta_celular import (
    IDADE_MAXIMA_REPROCESSO,
    MAX_CHARS_POR_RESPOSTA,
    MAX_RESPOSTAS_NO_CONTEXTO,
    OPCOES_RETORNO_MINUTOS,
    RespostaHumana,
    bloco_respostas_humanas,
    canal_da_resposta,
    destino_ignorado,
    deve_retornar,
    texto_da_resposta,
)


class TestDestino:
    def test_conversa_individual_conta(self):
        assert destino_ignorado("5567999990000@s.whatsapp.net") is False
        assert destino_ignorado("123456789@lid") is False

    def test_grupo_lista_canal_status_e_vazio_ficam_de_fora(self):
        for jid in ("1203630@g.us", "status@broadcast", "123@newsletter", "", None):
            assert destino_ignorado(jid) is True


class TestTexto:
    def test_texto_simples_e_estendido(self):
        assert (
            texto_da_resposta({"conversation": " Oi, já te respondo "})
            == "Oi, já te respondo"
        )
        assert (
            texto_da_resposta({"extendedTextMessage": {"text": "link aqui"}})
            == "link aqui"
        )

    def test_midia_vira_indicativo_com_legenda(self):
        assert (
            texto_da_resposta({"imageMessage": {"caption": "segue"}})
            == "[foto enviada pelo celular] segue"
        )
        assert texto_da_resposta({"audioMessage": {}}) == "[áudio enviado pelo celular]"
        assert (
            texto_da_resposta({"documentMessage": {"fileName": "proposta.pdf"}})
            == "[documento enviado pelo celular: proposta.pdf]"
        )

    def test_reacao_enquete_protocolo_nao_viram_bolha(self):
        assert texto_da_resposta({"reactionMessage": {"text": "👍"}}) is None
        assert texto_da_resposta({"protocolMessage": {}}) is None
        assert texto_da_resposta({"conversation": "   "}) is None
        assert texto_da_resposta(None) is None


class TestCanal:
    def test_canais(self):
        assert canal_da_resposta("manual:app:whatsapp") == "celular"
        assert canal_da_resposta("manual:app:whatsapp_business") == "celular"
        assert canal_da_resposta("manual:6cbff6ec-14d6") == "painel"

    def test_avisos_do_sistema_e_ia_nao_contam(self):
        assert canal_da_resposta("manual:system:transferencia") is None
        assert canal_da_resposta("Olá, quero saber o horário") is None
        assert canal_da_resposta(None) is None


class TestBloco:
    def test_vazio(self):
        assert bloco_respostas_humanas([]) == ""

    def test_formato_e_origem(self):
        b = bloco_respostas_humanas(
            [
                RespostaHumana("Pode vir às 15h", "celular"),
                RespostaHumana("Confirmado", "painel"),
            ]
        )
        assert b.startswith("[A EQUIPE JÁ RESPONDEU ESTE CLIENTE")
        assert "(pelo celular) Pode vir às 15h | (pelo painel) Confirmado" in b
        assert b.endswith("]")

    def test_corta_quantidade_e_tamanho(self):
        itens = [RespostaHumana(f"msg {i} " + "x" * 900, "celular") for i in range(8)]
        b = bloco_respostas_humanas(itens)
        assert b.count("(pelo celular)") == MAX_RESPOSTAS_NO_CONTEXTO
        assert "msg 7" in b and "msg 2" not in b, "ficam as mais recentes"
        trechos = [
            t.split(" | ")[0].rstrip("]") for t in b.split("(pelo celular) ")[1:]
        ]
        assert all(len(t) <= MAX_CHARS_POR_RESPOSTA for t in trechos), [
            len(t) for t in trechos
        ]
        assert all(t.endswith("…") for t in trechos), (
            "texto longo é cortado com reticências"
        )


class TestRetornoPorTempo:
    """PR B: a IA volta sozinha depois do prazo da conexão."""

    AGORA = datetime(2026, 9, 26, 15, 0, tzinfo=UTC)

    def _decide(self, *, cel_min_atras, cli_min_atras, minutos=30):
        cel = (
            None
            if cel_min_atras is None
            else self.AGORA - timedelta(minutes=cel_min_atras)
        )
        cli = (
            None
            if cli_min_atras is None
            else self.AGORA - timedelta(minutes=cli_min_atras)
        )
        return deve_retornar(
            ultima_celular_em=cel,
            ultima_cliente_em=cli,
            minutos=minutos,
            agora=self.AGORA,
        )

    def test_prazo_vencido_e_cliente_escreveu_depois_volta(self):
        assert self._decide(cel_min_atras=45, cli_min_atras=40) is True

    def test_sem_prazo_na_conexao_nunca_volta(self):
        assert self._decide(cel_min_atras=600, cli_min_atras=10, minutos=None) is False
        assert self._decide(cel_min_atras=600, cli_min_atras=10, minutos=0) is False

    def test_dentro_do_prazo_espera(self):
        assert self._decide(cel_min_atras=20, cli_min_atras=10) is False

    def test_cliente_nao_escreveu_depois_do_dono_espera(self):
        assert self._decide(cel_min_atras=45, cli_min_atras=50) is False
        assert self._decide(cel_min_atras=45, cli_min_atras=45) is False
        assert self._decide(cel_min_atras=45, cli_min_atras=None) is False

    def test_sem_resposta_do_celular_nao_decide(self):
        assert self._decide(cel_min_atras=None, cli_min_atras=10) is False

    def test_mensagem_com_mais_de_um_dia_nao_e_respondida(self):
        limite = int(IDADE_MAXIMA_REPROCESSO.total_seconds() // 60)
        assert self._decide(cel_min_atras=limite + 60, cli_min_atras=limite) is True
        assert (
            self._decide(cel_min_atras=limite + 60, cli_min_atras=limite + 1) is False
        )

    def test_opcoes_do_painel_cabem_no_check_da_mig_205(self):
        assert all(5 <= m <= 10080 for m in OPCOES_RETORNO_MINUTOS)
