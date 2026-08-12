"""Desenho do relatório mensal de uso em PDF (fpdf2).

Por que desenhado à mão e não HTML→PDF: renderizar o HTML fielmente exigiria
Chromium (~300MB) ou WeasyPrint (~80MB + libs de sistema) na imagem do worker,
que hoje é `python:3.12-slim`. O fpdf2 já estava nas dependências e não pede
nada do sistema além de uma fonte. O preço é este arquivo: o layout vive aqui,
separado do HTML do painel, e as duas versões precisam ser mantidas em sintonia
à mão.

A paleta e a hierarquia são as mesmas do relatório em tela — neutros mornos,
uma série cor de barro para mensagens e uma azul-ardósia para arquivos.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import structlog
from fpdf import FPDF
from fpdf.enums import XPos, YPos

logger = structlog.get_logger()

# ---------------------------------------------------------------------------
# Paleta — espelha `frontend` / o HTML do relatório
# ---------------------------------------------------------------------------
TINTA = (28, 27, 25)
TINTA_MEDIA = (85, 81, 75)
TINTA_FRACA = (125, 120, 111)
REGUA = (222, 217, 210)
REGUA_FIRME = (189, 182, 173)
FUNDO = (236, 234, 230)
BRANCO = (255, 255, 255)
SERIE_A = (176, 69, 31)
SERIE_A_SUAVE = (232, 207, 195)
SERIE_B = (63, 107, 125)
OK = (74, 124, 89)
ALERTA = (168, 120, 28)

# Fonte com acento e travessão. As core do fpdf2 são latin-1 e comeriam o "—"
# e o "→" do texto. Instalada por `fonts-dejavu-core` nas imagens.
_DEJAVU = Path("/usr/share/fonts/truetype/dejavu")
_REGULAR = _DEJAVU / "DejaVuSans.ttf"
_NEGRITO = _DEJAVU / "DejaVuSans-Bold.ttf"

MESES_PT = (
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)


def _mes_por_extenso(competencia: str) -> str:
    """`2026-07` -> `julho de 2026`."""
    ano, _, mes = competencia.partition("-")
    try:
        return f"{MESES_PT[int(mes) - 1]} de {ano}"
    except (ValueError, IndexError):
        return competencia


def _num(valor: float | int | None, casas: int = 0) -> str:
    """Número no formato brasileiro, com travessão quando não há valor."""
    if valor is None:
        return "—"
    if casas:
        return f"{valor:,.{casas}f}".replace(",", " ").replace(".", ",")
    return f"{int(valor):,}".replace(",", ".")


class _Relatorio(FPDF):
    """A4 com rodapé numerado. O cabeçalho é desenhado só na primeira página,
    então não usa o hook `header()` — ele roda em toda página."""

    def __init__(self, nome_empresa: str, competencia: str) -> None:
        super().__init__(orientation="P", unit="mm", format="A4")
        self.nome_empresa = nome_empresa
        self.competencia = competencia
        self.tem_unicode = False
        self.set_margins(11, 13, 11)
        self.set_auto_page_break(auto=True, margin=15)

        if _REGULAR.exists() and _NEGRITO.exists():
            self.add_font("dejavu", "", str(_REGULAR))
            self.add_font("dejavu", "B", str(_NEGRITO))
            self.tem_unicode = True
        else:
            # Degrada para Helvetica em máquina sem a fonte. O texto perde os
            # travessões, mas o relatório sai — melhor que erro de renderização.
            logger.warning("relatorio_uso_fonte_ausente", caminho=str(_DEJAVU))

    @property
    def familia(self) -> str:
        return "dejavu" if self.tem_unicode else "helvetica"

    def txt(self, texto: str) -> str:
        """Troca o que a Helvetica latin-1 não desenha, quando sem DejaVu."""
        if self.tem_unicode:
            return texto
        for de, para in (("—", "-"), ("→", "->"), ("×", "x"), ("≥", ">="), ("·", "-")):
            texto = texto.replace(de, para)
        return texto

    def footer(self) -> None:
        self.set_y(-12)
        self.set_font(self.familia, "", 7)
        self.set_text_color(*TINTA_FRACA)
        self.cell(
            0,
            5,
            self.txt(f"{self.nome_empresa} · {_mes_por_extenso(self.competencia)}"),
            align="L",
        )
        self.cell(0, 5, f"{self.page_no()}", align="R")

    # -- blocos reutilizáveis ------------------------------------------------

    def largura_util(self) -> float:
        return self.w - self.l_margin - self.r_margin

    def espaco(self, mm: float) -> None:
        self.set_y(self.get_y() + mm)

    def garantir_espaco(self, mm: float) -> None:
        """Quebra a página quando o bloco não cabe inteiro — evita título órfão
        e gráfico partido no meio."""
        if self.get_y() + mm > self.h - 18:
            self.add_page()

    def titulo_secao(self, texto: str, reserva: float = 24) -> None:
        """`reserva` é a altura do bloco que vem logo abaixo.

        Sem ela o título cabe no fim da página e a tabela vai para a seguinte,
        deixando um cabeçalho de coluna órfão — que foi exatamente o que
        aconteceu com "Para onde vai cada mensagem" na primeira prova.
        """
        self.garantir_espaco(reserva)
        self.espaco(3)
        self.set_font(self.familia, "B", 13)
        self.set_text_color(*TINTA)
        self.cell(0, 7, self.txt(texto), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        y = self.get_y()
        self.set_draw_color(*REGUA_FIRME)
        self.set_line_width(0.3)
        self.line(self.l_margin, y, self.w - self.r_margin, y)
        self.espaco(2.5)

    def paragrafo(self, texto: str, tamanho: float = 9) -> None:
        self.set_font(self.familia, "", tamanho)
        self.set_text_color(*TINTA_MEDIA)
        # align="L": o justificado do fpdf2 estica os espaços e a última linha
        # de cada parágrafo fica com buracos visíveis.
        self.multi_cell(
            self.largura_util(),
            4.6,
            self.txt(texto),
            align="L",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        self.espaco(1)

    def rotulo_pequeno(self, texto: str) -> None:
        self.set_font(self.familia, "B", 6.5)
        self.set_text_color(*TINTA_FRACA)
        self.cell(0, 4, self.txt(texto.upper()), new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def montar_pdf(dados: dict[str, Any], anterior: dict[str, Any] | None = None) -> bytes:
    """Renderiza o relatório. `anterior` é o mês anterior, para a comparação —
    ausente quando é o primeiro mês do cliente."""
    empresa = dados["empresa"]["nome"]
    pdf = _Relatorio(empresa, dados["competencia"])
    pdf.add_page()

    _cabecalho(pdf, dados)
    _resumo_do_mes(pdf, dados, anterior)
    _grafico_diario(pdf, dados)
    _tabela_formatos(pdf, dados)
    _tabela_destino(pdf, dados, anterior)
    _desempenho(pdf, dados)
    _grafico_horas(pdf, dados)
    _triagem(pdf, dados)
    _como_ler(pdf, dados)

    saida = pdf.output()
    return bytes(saida)


# ---------------------------------------------------------------------------
# Seções
# ---------------------------------------------------------------------------


def _cabecalho(pdf: _Relatorio, d: dict[str, Any]) -> None:
    pdf.rotulo_pequeno(f"Relatório de uso · {d['empresa']['nome']}")
    pdf.espaco(1)
    pdf.set_font(pdf.familia, "B", 24)
    pdf.set_text_color(*TINTA)
    pdf.cell(0, 11, pdf.txt("Uso do assistente"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.espaco(1.5)
    pdf.paragrafo(
        "Volume processado pelo sistema: mensagens, arquivos lidos, tempo de "
        "resposta e disponibilidade. Nenhum conteúdo de conversa aparece aqui."
    )
    inicio = date.fromisoformat(d["inicio"]).strftime("%d/%m/%Y")
    fim = date.fromisoformat(d["fim"]).strftime("%d/%m/%Y")
    marca = " · mês em curso, dados parciais" if d["parcial"] else ""
    pdf.set_font(pdf.familia, "", 8)
    pdf.set_text_color(*TINTA_FRACA)
    pdf.cell(
        0,
        5,
        pdf.txt(f"{inicio} → {fim}{marca}"),
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    y = pdf.get_y() + 2
    pdf.set_draw_color(*TINTA)
    pdf.set_line_width(0.8)
    pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    pdf.set_y(y + 3)


def _resumo_do_mes(
    pdf: _Relatorio, d: dict[str, Any], ant: dict[str, Any] | None
) -> None:
    pdf.titulo_secao("O mês em números", reserva=70)
    t = d["totais"]

    linhas = [
        (
            "Mensagens processadas",
            _num(t["mensagens"]),
            f"{_num(t['mensagens_por_dia'], 1)}/dia",
        ),
        ("Atendimentos abertos", _num(t["atendimentos"]), ""),
        ("Pessoas atendidas", _num(t["contatos"]), ""),
        ("Arquivos recebidos", _num(t["arquivos_recebidos"]), ""),
        ("Arquivos lidos", _num(t["arquivos_lidos"]), ""),
    ]
    seg = d["desempenho"]["seg_medio"]
    linhas.append(
        ("Tempo médio de resposta", f"{_num(seg, 1)}s" if seg is not None else "—", "")
    )

    if ant:
        pdf.paragrafo(
            f"A coluna da direita é {_mes_por_extenso(ant['competencia'])}, "
            "para comparação."
        )

    largura = pdf.largura_util()
    col_rot = largura * (0.44 if ant else 0.62)
    col_val = largura * (0.30 if ant else 0.38)
    col_ant = largura - col_rot - col_val

    if ant:
        pdf.set_font(pdf.familia, "B", 6.5)
        pdf.set_text_color(*TINTA_FRACA)
        pdf.cell(col_rot, 5, "")
        pdf.cell(col_val, 5, pdf.txt(_mes_por_extenso(d["competencia"])), align="R")
        pdf.cell(
            col_ant,
            5,
            pdf.txt(_mes_por_extenso(ant["competencia"])),
            align="R",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )

    anteriores = _valores_comparaveis(ant) if ant else {}
    for i, (rotulo, valor, nota) in enumerate(linhas):
        pdf.set_fill_color(*(BRANCO if i % 2 == 0 else FUNDO))
        y0 = pdf.get_y()
        pdf.rect(pdf.l_margin, y0, largura, 7, style="F")

        pdf.set_font(pdf.familia, "", 9)
        pdf.set_text_color(*TINTA_MEDIA)
        pdf.cell(col_rot, 7, pdf.txt(f"  {rotulo}"))

        pdf.set_font(pdf.familia, "B", 10)
        pdf.set_text_color(*TINTA)
        sufixo = f"  {nota}" if nota and not ant else ""
        pdf.cell(col_val, 7, pdf.txt(f"{valor}{sufixo} "), align="R")

        if ant:
            pdf.set_font(pdf.familia, "", 9)
            pdf.set_text_color(*TINTA_FRACA)
            pdf.cell(col_ant, 7, pdf.txt(f"{anteriores.get(rotulo, '—')} "), align="R")
        pdf.ln(7)

    pdf.espaco(1)


def _valores_comparaveis(ant: dict[str, Any]) -> dict[str, str]:
    t = ant["totais"]
    seg = ant["desempenho"]["seg_medio"]
    return {
        "Mensagens processadas": _num(t["mensagens"]),
        "Atendimentos abertos": _num(t["atendimentos"]),
        "Pessoas atendidas": _num(t["contatos"]),
        "Arquivos recebidos": _num(t["arquivos_recebidos"]),
        "Arquivos lidos": _num(t["arquivos_lidos"]),
        "Tempo médio de resposta": f"{_num(seg, 1)}s" if seg is not None else "—",
    }


def _grafico_diario(pdf: _Relatorio, d: dict[str, Any]) -> None:
    diario = d["diario"]
    if not diario:
        return
    pdf.titulo_secao("Dia a dia", reserva=70)
    pdf.paragrafo(
        "Cada coluna é um dia. A base escura marca as mensagens que trouxeram "
        "arquivo; o resto é texto e áudio."
    )

    altura = 34.0
    pdf.garantir_espaco(altura + 14)
    largura = pdf.largura_util()
    n = len(diario)
    passo = largura / n
    barra = min(passo * 0.72, 6.0)
    teto = max(x["mensagens"] for x in diario) or 1

    y_base = pdf.get_y() + altura
    for i, dia in enumerate(diario):
        x = pdf.l_margin + i * passo + (passo - barra) / 2
        h_total = altura * dia["mensagens"] / teto
        h_arq = altura * dia["com_arquivo"] / teto
        pdf.set_fill_color(*SERIE_A_SUAVE)
        pdf.rect(x, y_base - h_total, barra, h_total - h_arq, style="F")
        pdf.set_fill_color(*SERIE_B)
        pdf.rect(x, y_base - h_arq, barra, h_arq, style="F")

    pdf.set_draw_color(*REGUA_FIRME)
    pdf.set_line_width(0.2)
    pdf.line(pdf.l_margin, y_base, pdf.w - pdf.r_margin, y_base)

    pdf.set_y(y_base + 0.5)
    pdf.set_font(pdf.familia, "", 5.5)
    pdf.set_text_color(*TINTA_FRACA)
    for i, dia in enumerate(diario):
        # Rótulo a cada 2 dias quando o mês é cheio: 31 números em 188mm
        # viram borrão.
        rotulo = (
            date.fromisoformat(dia["dia"]).strftime("%d")
            if (n <= 16 or i % 2 == 0)
            else ""
        )
        pdf.set_xy(pdf.l_margin + i * passo, y_base + 0.5)
        pdf.cell(passo, 3.5, rotulo, align="C")

    pdf.set_y(y_base + 5)
    _legenda(
        pdf,
        [(SERIE_A_SUAVE, "mensagens de texto e áudio"), (SERIE_B, "com arquivo")],
    )

    # Pico e vale só dizem algo quando há mais de um dia — com um só, a frase
    # vira "o pico foi 05/08 e o vale também foi 05/08".
    if len(diario) > 1:
        pico = max(diario, key=lambda x: x["mensagens"])
        vale = min(diario, key=lambda x: x["mensagens"])
        pdf.espaco(1)
        pdf.paragrafo(
            f"O pico foi {date.fromisoformat(pico['dia']).strftime('%d/%m')} com "
            f"{_num(pico['mensagens'])} mensagens; o dia mais fraco foi "
            f"{date.fromisoformat(vale['dia']).strftime('%d/%m')}, com "
            f"{_num(vale['mensagens'])}."
        )


def _legenda(pdf: _Relatorio, itens: list[tuple[tuple[int, int, int], str]]) -> None:
    pdf.set_font(pdf.familia, "", 7)
    x = pdf.l_margin
    y = pdf.get_y()
    for cor, texto in itens:
        pdf.set_fill_color(*cor)
        pdf.rect(x, y + 1, 2.6, 2.6, style="F")
        pdf.set_xy(x + 3.6, y)
        pdf.set_text_color(*TINTA_MEDIA)
        largura = pdf.get_string_width(texto) + 6
        pdf.cell(largura, 4.5, pdf.txt(texto))
        x += 3.6 + largura
    pdf.set_y(y + 5)


def _tabela_formatos(pdf: _Relatorio, d: dict[str, Any]) -> None:
    formatos = d["formatos"]
    if not formatos:
        return
    pdf.titulo_secao("Arquivos processados", reserva=60)
    t = d["totais"]
    pdf.paragrafo(
        f"{_num(t['arquivos_recebidos'])} arquivos recebidos e "
        f"{_num(t['arquivos_lidos'])} lidos. O assistente transcreve áudio, "
        "descreve imagem e lê o texto de documentos; o que não foi lido veio de "
        "contatos silenciados ou de formato ainda não suportado."
    )

    colunas = [("Formato", 0.52, "L"), ("Recebidos", 0.24, "R"), ("Lidos", 0.24, "R")]
    linhas = [
        (f["formato"], _num(f["recebidos"]), _num(f["lidos"]) if f["lidos"] else "—")
        for f in formatos
    ]
    total = ("Total", _num(t["arquivos_recebidos"]), _num(t["arquivos_lidos"]))
    _tabela(pdf, colunas, linhas, total)


def _tabela_destino(
    pdf: _Relatorio, d: dict[str, Any], ant: dict[str, Any] | None
) -> None:
    pdf.titulo_secao("Para onde vai cada mensagem", reserva=68)
    pdf.paragrafo(
        "Nem toda mensagem recebida gera resposta automática — e isso é "
        "configuração, não falha."
    )
    dst = d["destino"]
    dst_ant = ant["destino"] if ant else {}

    nomes = [
        ("respondida", "Respondida pelo assistente"),
        ("encaminhada", "Já encaminhada ao responsável"),
        ("silenciada", "Contato silenciado"),
        ("manual", "Assistente desligado na conexão"),
        ("superada", "Resposta superada"),
    ]
    if ant:
        colunas = [
            ("Destino", 0.52, "L"),
            (_mes_por_extenso(d["competencia"]).split(" de ")[0], 0.24, "R"),
            (_mes_por_extenso(ant["competencia"]).split(" de ")[0], 0.24, "R"),
        ]
        linhas = [
            (rot, _num(dst.get(k, 0)), _num(dst_ant.get(k, 0))) for k, rot in nomes
        ]
    else:
        colunas = [("Destino", 0.70, "L"), ("Mensagens", 0.30, "R")]
        linhas = [(rot, _num(dst.get(k, 0))) for k, rot in nomes]
    _tabela(pdf, colunas, linhas, None)


def _tabela(
    pdf: _Relatorio,
    colunas: list[tuple[str, float, str]],
    linhas: list[tuple[str, ...]],
    total: tuple[str, ...] | None,
) -> None:
    largura = pdf.largura_util()
    pdf.garantir_espaco(8 + 6.5 * (len(linhas) + 2))

    pdf.set_font(pdf.familia, "B", 6.5)
    pdf.set_text_color(*TINTA_FRACA)
    pdf.set_fill_color(*FUNDO)
    y0 = pdf.get_y()
    pdf.rect(pdf.l_margin, y0, largura, 6, style="F")
    for nome, fracao, align in colunas:
        pad = "  " if align == "L" else ""
        sufixo = "" if align == "L" else "  "
        pdf.cell(
            largura * fracao, 6, pdf.txt(f"{pad}{nome.upper()}{sufixo}"), align=align
        )
    pdf.ln(6)

    for i, linha in enumerate(linhas):
        pdf.set_fill_color(*(BRANCO if i % 2 == 0 else FUNDO))
        y = pdf.get_y()
        pdf.rect(pdf.l_margin, y, largura, 6.5, style="F")
        for valor, (_, fracao, align) in zip(linha, colunas, strict=True):
            pdf.set_font(pdf.familia, "", 8.5)
            pdf.set_text_color(*(TINTA_MEDIA if align == "L" else TINTA))
            pad = "  " if align == "L" else ""
            sufixo = "" if align == "L" else "  "
            pdf.cell(
                largura * fracao, 6.5, pdf.txt(f"{pad}{valor}{sufixo}"), align=align
            )
        pdf.ln(6.5)

    if total:
        pdf.set_fill_color(*FUNDO)
        y = pdf.get_y()
        pdf.rect(pdf.l_margin, y, largura, 7, style="F")
        pdf.set_draw_color(*REGUA_FIRME)
        pdf.line(pdf.l_margin, y, pdf.l_margin + largura, y)
        for valor, (_, fracao, align) in zip(total, colunas, strict=True):
            pdf.set_font(pdf.familia, "B", 8.5)
            pdf.set_text_color(*TINTA)
            pad = "  " if align == "L" else ""
            sufixo = "" if align == "L" else "  "
            pdf.cell(largura * fracao, 7, pdf.txt(f"{pad}{valor}{sufixo}"), align=align)
        pdf.ln(7)
    pdf.espaco(1)


def _desempenho(pdf: _Relatorio, d: dict[str, Any]) -> None:
    pdf.titulo_secao("Desempenho e disponibilidade", reserva=46)
    p = d["desempenho"]
    cartoes = [
        (
            "Resposta média",
            f"{_num(p['seg_medio'], 1)}s" if p["seg_medio"] else "—",
            "",
        ),
        (
            "95% respondidas em",
            f"{_num(p['seg_p95'], 1)}s" if p["seg_p95"] else "—",
            "inclui transcrever áudio e ler documento",
        ),
        ("Falhas", _num(p["falhas"]), f"em {_num(p['processadas'])} mensagens"),
        (
            "Taxa de sucesso",
            f"{_num(p['taxa_sucesso'], 2)}%" if p["taxa_sucesso"] else "—",
            "",
        ),
    ]
    _cartoes(pdf, cartoes)


def _cartoes(pdf: _Relatorio, itens: list[tuple[str, str, str]]) -> None:
    pdf.garantir_espaco(24)
    largura = pdf.largura_util() / len(itens)
    y0 = pdf.get_y()
    altura = 20.0
    for i, (rotulo, valor, nota) in enumerate(itens):
        x = pdf.l_margin + i * largura
        pdf.set_fill_color(*BRANCO)
        pdf.set_draw_color(*REGUA)
        pdf.set_line_width(0.2)
        pdf.rect(x, y0, largura, altura, style="DF")

        pdf.set_xy(x + 2.5, y0 + 2)
        pdf.set_font(pdf.familia, "B", 6)
        pdf.set_text_color(*TINTA_FRACA)
        pdf.cell(largura - 5, 3.5, pdf.txt(rotulo.upper()))

        pdf.set_xy(x + 2.5, y0 + 6)
        pdf.set_font(pdf.familia, "B", 14)
        pdf.set_text_color(*TINTA)
        pdf.cell(largura - 5, 7, pdf.txt(valor))

        if nota:
            pdf.set_xy(x + 2.5, y0 + 13.5)
            pdf.set_font(pdf.familia, "", 5.8)
            pdf.set_text_color(*TINTA_FRACA)
            pdf.multi_cell(largura - 5, 2.9, pdf.txt(nota), align="L")
    pdf.set_y(y0 + altura + 2)


def _grafico_horas(pdf: _Relatorio, d: dict[str, Any]) -> None:
    horas = d["horas"]
    if not horas:
        return
    pdf.titulo_secao("Quando as pessoas escrevem", reserva=62)
    pdf.paragrafo(f"Distribuição por hora do dia, no fuso {d['tz']}.")

    altura = 24.0
    pdf.garantir_espaco(altura + 12)
    por_hora = {h["hora"]: h["mensagens"] for h in horas}
    teto = max(por_hora.values()) or 1
    largura = pdf.largura_util()
    passo = largura / 24
    barra = passo * 0.7
    y_base = pdf.get_y() + altura

    for hora in range(24):
        qtd = por_hora.get(hora, 0)
        if not qtd:
            continue
        x = pdf.l_margin + hora * passo + (passo - barra) / 2
        h = altura * qtd / teto
        pdf.set_fill_color(*(SERIE_A if qtd == teto else SERIE_B))
        pdf.rect(x, y_base - h, barra, h, style="F")

    pdf.set_draw_color(*REGUA_FIRME)
    pdf.set_line_width(0.2)
    pdf.line(pdf.l_margin, y_base, pdf.w - pdf.r_margin, y_base)

    pdf.set_y(y_base + 0.5)
    pdf.set_font(pdf.familia, "", 5.5)
    pdf.set_text_color(*TINTA_FRACA)
    for hora in range(24):
        pdf.set_xy(pdf.l_margin + hora * passo, y_base + 0.5)
        pdf.cell(passo, 3.5, f"{hora}", align="C")
    pdf.set_y(y_base + 5)

    pico = max(por_hora.items(), key=lambda kv: kv[1])
    fora = sum(q for h, q in por_hora.items() if h >= 19 or h < 7)
    pdf.paragrafo(
        f"O pico é às {pico[0]}h, com {_num(pico[1])} mensagens. "
        f"{_num(fora)} chegaram fora do horário comercial (antes das 7h ou "
        "depois das 19h) — a fatia que só existe porque o assistente atende "
        "a qualquer hora."
    )


def _triagem(pdf: _Relatorio, d: dict[str, Any]) -> None:
    t = d["triagem"]
    if not t["atendimentos"]:
        return
    pdf.titulo_secao("Triagem automática", reserva=52)
    pdf.paragrafo(
        "A cada conversa, o assistente classifica assunto, urgência e tom antes "
        "de encaminhar. É o que permite abrir primeiro o que é urgente."
    )
    por_atd = (
        round(d["totais"]["mensagens"] / t["atendimentos"], 1)
        if t["atendimentos"]
        else None
    )
    _cartoes(
        pdf,
        [
            (
                "Atendimentos triados",
                f"{t['cobertura_pct']}%" if t["cobertura_pct"] is not None else "—",
                f"{_num(t['com_triagem'])} de {_num(t['atendimentos'])}",
            ),
            ("Marcados urgente", _num(t["urgentes"]), ""),
            ("Prioridade alta", _num(t["alta"]), ""),
            ("Mensagens por atendimento", _num(por_atd, 1), ""),
        ],
    )


def _como_ler(pdf: _Relatorio, d: dict[str, Any]) -> None:
    pdf.titulo_secao("Como ler este relatório", reserva=56)
    itens = [
        "Nenhum conteúdo de conversa aparece aqui. Todos os números são de "
        "volume e desempenho: quantas mensagens, de que tipo, em quanto tempo.",
        '"Arquivos lidos" não é meta de 100%. A diferença vem de contatos '
        "silenciados, que por configuração não passam pelo assistente, e de "
        "formatos ainda não suportados.",
        "O tempo de resposta inclui o trabalho pesado — transcrever a nota de "
        "voz ou ler o PDF antes de formular a resposta, não só o tempo de digitar.",
    ]
    if d["parcial"]:
        itens.insert(
            0,
            "Este mês ainda está em curso: os números vão até a data de "
            "apuração e não representam o mês fechado.",
        )

    largura = pdf.largura_util()
    y0 = pdf.get_y()

    # Só a régua à esquerda, sem fundo: desenhar o retângulo exigiria medir o
    # texto antes de escrevê-lo, e a régua sozinha já separa o bloco.
    pdf.set_xy(pdf.l_margin + 4, y0 + 2.5)
    for item in itens:
        pdf.set_x(pdf.l_margin + 4)
        pdf.set_font(pdf.familia, "", 8)
        pdf.set_text_color(*TINTA_MEDIA)
        pdf.multi_cell(
            largura - 8,
            4.2,
            pdf.txt(f"• {item}"),
            align="L",
            new_x=XPos.LMARGIN,
            new_y=YPos.NEXT,
        )
        pdf.espaco(1.5)

    altura = pdf.get_y() - y0 + 1
    pdf.set_draw_color(*SERIE_B)
    pdf.set_line_width(0.8)
    pdf.line(pdf.l_margin, y0, pdf.l_margin, y0 + altura)
    pdf.espaco(2)

    pdf.set_font(pdf.familia, "", 7)
    pdf.set_text_color(*TINTA_FRACA)
    apurado = date.today().strftime("%d/%m/%Y")
    pdf.multi_cell(
        largura,
        4,
        pdf.txt(f"Apurado em {apurado} · empresa {d['empresa']['id']}"),
        align="L",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
