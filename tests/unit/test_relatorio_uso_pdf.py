"""Renderização do PDF do relatório de uso.

Teste de fumaça caro de escrever e barato de rodar: o fpdf2 falha em runtime,
não na importação — `multi_cell` sem `new_x`/`new_y`, célula mais larga que a
página, fonte sem o glifo. Nada disso o ruff ou o pyright pegam, e cada um
deles quebraria o envio ao cliente.
"""

from __future__ import annotations

import re

import pytest

from whatsapp_langchain.shared.relatorio_uso_pdf import montar_pdf


def _dados(**over):
    """Um mês realista, no formato que `montar_dados` devolve."""
    base = {
        "empresa": {"id": 1018, "nome": "Luis Fernando Macorini"},
        "competencia": "2026-07",
        "inicio": "2026-07-01",
        "fim": "2026-07-31",
        "parcial": False,
        "tz": "America/Campo_Grande",
        "totais": {
            "mensagens": 2103,
            "com_arquivo": 306,
            "dias_com_movimento": 10,
            "mensagens_por_dia": 210.3,
            "contatos": 145,
            "atendimentos": 222,
            "arquivos_recebidos": 306,
            "arquivos_lidos": 134,
        },
        "diario": [
            {
                "dia": f"2026-07-{22 + i:02d}",
                "mensagens": m,
                "com_arquivo": a,
                "contatos": 30,
                "atendimentos": 40,
            }
            for i, (m, a) in enumerate(
                [
                    (53, 0),
                    (261, 0),
                    (192, 36),
                    (38, 17),
                    (35, 9),
                    (260, 41),
                    (310, 42),
                    (405, 48),
                    (326, 63),
                    (223, 50),
                ]
            )
        ],
        "formatos": [
            {"formato": "Áudio — nota de voz", "recebidos": 145, "lidos": 83},
            {"formato": "Imagem — foto", "recebidos": 94, "lidos": 32},
            {"formato": "PDF", "recebidos": 45, "lidos": 19},
            {"formato": "Vídeo", "recebidos": 8, "lidos": 0},
            {"formato": "Word", "recebidos": 14, "lidos": 0},
        ],
        "destino": {
            "respondida": 658,
            "encaminhada": 194,
            "silenciada": 775,
            "manual": 432,
            "superada": 25,
        },
        "desempenho": {
            "processadas": 2103,
            "seg_medio": 16.8,
            "seg_p95": 22.8,
            "falhas": 21,
            "taxa_sucesso": 99.0,
        },
        "horas": [{"hora": h, "mensagens": 50 + h * 7} for h in range(6, 22)],
        "triagem": {
            "atendimentos": 222,
            "com_triagem": 50,
            "urgentes": 20,
            "alta": 19,
            "pessoas": 145,
            "cobertura_pct": 23,
        },
    }
    base.update(over)
    return base


def _paginas(pdf: bytes) -> int:
    return len(re.findall(rb"/Type\s*/Page[^s]", pdf))


class TestMontarPdf:
    def test_gera_pdf_valido(self):
        saida = montar_pdf(_dados())
        assert saida.startswith(b"%PDF"), "não é um PDF"
        assert len(saida) > 5_000, "PDF pequeno demais para ter conteúdo"
        assert _paginas(saida) >= 2

    def test_cabe_no_limite_de_envio(self):
        """16 MB é o teto de `outbound.MIDIA_MAX_BYTES`. Um relatório que
        estoure isso não chega ao cliente."""
        assert len(montar_pdf(_dados())) < 16 * 1024 * 1024

    def test_comparacao_com_mes_anterior_nao_quebra(self):
        anterior = _dados(competencia="2026-06", inicio="2026-06-01", fim="2026-06-30")
        saida = montar_pdf(_dados(), anterior)
        assert saida.startswith(b"%PDF")

    def test_mes_sem_movimento_ainda_gera_documento(self):
        """Cliente novo, ou mês em que ninguém escreveu. Zero não é erro."""
        vazio = _dados(
            diario=[],
            formatos=[],
            horas=[],
            destino=dict.fromkeys(
                ["respondida", "encaminhada", "silenciada", "manual", "superada"], 0
            ),
            totais={
                "mensagens": 0,
                "com_arquivo": 0,
                "dias_com_movimento": 0,
                "mensagens_por_dia": 0,
                "contatos": 0,
                "atendimentos": 0,
                "arquivos_recebidos": 0,
                "arquivos_lidos": 0,
            },
            desempenho={
                "processadas": 0,
                "seg_medio": None,
                "seg_p95": None,
                "falhas": 0,
                "taxa_sucesso": None,
            },
            triagem={
                "atendimentos": 0,
                "com_triagem": 0,
                "urgentes": 0,
                "alta": 0,
                "pessoas": 0,
                "cobertura_pct": None,
            },
        )
        saida = montar_pdf(vazio)
        assert saida.startswith(b"%PDF")

    def test_mes_cheio_de_31_dias_nao_estoura_a_largura(self):
        """31 colunas em 188mm é o caso mais apertado do gráfico diário."""
        diario = [
            {
                "dia": f"2026-08-{d:02d}",
                "mensagens": 100 + d,
                "com_arquivo": d,
                "contatos": 10,
                "atendimentos": 12,
            }
            for d in range(1, 32)
        ]
        saida = montar_pdf(_dados(competencia="2026-08", diario=diario))
        assert saida.startswith(b"%PDF")

    def test_mes_parcial_avisa_no_texto(self):
        """O aviso entra na lista de "como ler" — sem ele o cliente compara
        um mês pela metade com um mês inteiro."""
        completo = montar_pdf(_dados(parcial=False))
        parcial = montar_pdf(_dados(parcial=True))
        assert len(parcial) > len(completo)

    @pytest.mark.parametrize("acentuado", ["Açaí & Cia", "Ótica Visão", "Hospital São"])
    def test_nome_com_acento_nao_quebra(self, acentuado):
        saida = montar_pdf(_dados(empresa={"id": 7, "nome": acentuado}))
        assert saida.startswith(b"%PDF")
