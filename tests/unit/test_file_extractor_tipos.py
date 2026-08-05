"""Formatos que o extrator aprendeu em 2026-08-05: XLSX e DOC legado.

O gatilho foi o atendimento 1018-000664 — a cliente mandou um `.doc` junto com
um `.docx`, o `.docx` foi lido e o `.doc` recusado. A causa não era o formato
em si: `_media_kind` dizia que era documento tratável, o mime virava o nome
`doc.doc`, e `SUPPORTED_EXTENSIONS` não tinha `.doc`. Planilha caía igual, por
outro caminho: `doc.bin`.
"""

import io
import shutil
from unittest.mock import patch

import pytest

from whatsapp_langchain.shared.file_extractor import (
    UnsupportedFileTypeError,
    detect_kind,
    extract_text,
    filename_for_media_type,
)

# --- detect_kind: os dois formatos novos ---


def test_detect_kind_xlsx():
    assert detect_kind("planilha.xlsx") == "xlsx"
    assert detect_kind("PLANILHA.XLSX") == "xlsx"


def test_detect_kind_doc_legado():
    assert detect_kind("proposta.doc") == "doc"
    # `.doc` e `.docx` são parsers diferentes — confundi-los é o defeito.
    assert detect_kind("proposta.docx") == "docx"


def test_detect_kind_recusa_o_que_nao_tem_parser():
    with pytest.raises(UnsupportedFileTypeError):
        detect_kind("apresentacao.pptx")


# --- filename_for_media_type: a tabela que estava duplicada e divergiu ---


@pytest.mark.parametrize(
    ("mime", "esperado"),
    [
        ("application/pdf", "doc.pdf"),
        (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "doc.docx",
        ),
        # Este é o caso do defeito: caía em `doc.bin` nas duas cópias antigas.
        (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "doc.xlsx",
        ),
        ("application/msword", "doc.doc"),
        ("text/plain", "doc.txt"),
        ("image/png", "doc.png"),
    ],
)
def test_filename_for_media_type_cobre_os_mimes_de_producao(mime, esperado):
    assert filename_for_media_type(mime) == esperado


def test_filename_for_media_type_sem_mime_usa_fallback():
    assert filename_for_media_type(None, fallback="x.pdf") == "x.pdf"
    assert filename_for_media_type("", fallback="x.pdf") == "x.pdf"


def test_nome_inferido_de_planilha_e_aceito_pelo_detect_kind():
    """A prova de que as duas pontas voltaram a concordar.

    Era exatamente aqui que o sistema se contradizia: uma função inventava um
    nome que a outra recusava, e o cliente levava a culpa.
    """
    mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert detect_kind(filename_for_media_type(mime)) == "xlsx"


# --- XLSX ---


def _planilha_de_teste() -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Orçamento"
    ws.append(["Item", "Valor"])
    ws.append(["Consultoria", 1500])
    ws.append([None, None])  # linha vazia: não deve aparecer no texto
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


async def test_xlsx_extrai_conteudo_e_nome_da_aba():
    texto = await extract_text("orcamento.xlsx", _planilha_de_teste())

    assert "Orçamento" in texto  # nome da aba, para o agente saber o contexto
    assert "Consultoria" in texto
    assert "1500" in texto


async def test_xlsx_ignora_linha_vazia():
    texto = await extract_text("orcamento.xlsx", _planilha_de_teste())
    # 1 cabeçalho da aba + 2 linhas com dado; a linha vazia não entra.
    assert len([ln for ln in texto.splitlines() if ln.strip()]) == 3


# --- DOC legado ---


async def test_doc_sem_antiword_degrada_em_vez_de_estourar():
    """Sem o binário, é `UnsupportedFileTypeError` — e não uma falha genérica.

    A distinção é o que impede a retentativa inútil: o chamador trata isso como
    "não sei ler", responde citando o nome do arquivo, e não repete cinco vezes.
    """
    with patch.object(shutil, "which", return_value=None):
        with pytest.raises(UnsupportedFileTypeError):
            await extract_text("proposta.doc", b"\xd0\xcf\x11\xe0qualquer-coisa")


@pytest.mark.skipif(
    shutil.which("antiword") is None,
    reason="antiword não instalado nesta máquina (está nas imagens Docker)",
)
async def test_doc_com_antiword_le_o_arquivo():
    """Caminho feliz do `.doc`, quando o binário existe.

    Roda na imagem de testes e no CI de container; pulado na máquina de quem
    não tem o apt instalado — por isso o teste acima, da degradação, é o que
    nunca pode faltar.
    """
    from pathlib import Path

    amostra = Path(__file__).parent / "fixtures" / "amostra.doc"
    if not amostra.exists():
        pytest.skip("fixture amostra.doc ausente")
    texto = await extract_text("amostra.doc", amostra.read_bytes())
    assert texto.strip()
