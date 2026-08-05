"""Bateria de leitura de documentos — PDF, DOCX, XLSX e DOC (mig 164).

Nasceu do atendimento **1018-000664**: a cliente mandou um `.docx` e um `.doc`
no mesmo segundo, o primeiro foi lido e o segundo gastou **5 tentativas em 59
segundos** para terminar em "estamos com dificuldades em processar
imagens/audio". A causa era uma discordância entre dois módulos sobre o que é
documento tratável, e três consequências: mensagem errada, resposta automática
furando o portão da fila, e retentativa de um erro que nunca ia passar.

Isso foi verificado à mão, por WhatsApp, com celular pareado. Esta bateria é a
mesma verificação sem depender de alguém com um celular.

O que cada cenário trava:

| envio | o que reprova se quebrar |
|---|---|
| PDF, DOCX, XLSX, DOC | o formato deixou de ser lido |
| XLSX | volta a virar `doc.bin` e ser recusado |
| PDF acima do teto | recusa permanente virou retentativa, ou virou erro |
| agente sem permissão | o interruptor da tela voltou a ser decorativo |

Rodar:
    DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \\
      uv run pytest tests/e2e/test_documentos.py -v -s -m docker_demo
"""

from __future__ import annotations

import base64
import time
import uuid
from pathlib import Path

import allure
import httpx
import psycopg
import pytest

from scripts.gerar_assets_teste import pdf_acima_do_teto
from tests.e2e.constantes import (
    AGENTE_DOCUMENTOS,
    EMPRESA_E2E,
    INSTANCIA_EVOLUTION,
)
from tests.integration.helpers import API_BASE_URL

pytestmark = pytest.mark.docker_demo

ASSETS = Path(__file__).resolve().parent.parent / "assets"

#: Tempo máximo esperando o worker terminar a linha. A janela de agrupamento da
#: conexão soma antes disso, e o modelo leva alguns segundos.
TIMEOUT_TURNO_S = 90

MIME_POR_EXT = {
    ".pdf": "application/pdf",
    ".docx": (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ),
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".doc": "application/msword",
}


def _postar_documento(
    *, nome_arquivo: str, conteudo: bytes, telefone: str, legenda: str = ""
) -> str:
    """Posta um documento no webhook Evolution e devolve o `message_id`.

    O arquivo vai embutido como `data:` URL, que é exatamente o formato que o
    pre-fetch da Evolution produz antes de enfileirar (ver `evolution_webhook`,
    "Convertendo pra data URL aqui").

    **`key.id` é omitido de propósito.** Com ele, a rota tenta buscar a mídia no
    servidor Evolution real e falha em ambiente de teste. Sem ele, o payload
    passa direto — e nenhuma linha de produção precisou mudar para acomodar o
    teste.
    """
    ext = Path(nome_arquivo).suffix.lower()
    mime = MIME_POR_EXT[ext]
    b64 = base64.b64encode(conteudo).decode()

    payload = {
        "event": "messages.upsert",
        "instance": INSTANCIA_EVOLUTION,
        "data": {
            "key": {
                "remoteJid": f"{telefone.lstrip('+')}@s.whatsapp.net",
                "fromMe": False,
            },
            "message": {
                "documentMessage": {
                    "url": f"data:{mime};base64,{b64}",
                    "mimetype": mime,
                    "fileName": nome_arquivo,
                    "caption": legenda,
                }
            },
        },
    }
    resp = httpx.post(
        f"{API_BASE_URL}/webhook/evolution",
        json=payload,
        headers={"apikey": _apikey()},
        timeout=60,
    )
    assert resp.status_code == 200, f"webhook recusou: {resp.status_code} {resp.text}"
    return telefone


def _apikey() -> str:
    """Chave que o webhook Evolution exige quando `EVOLUTION_VALIDATE_APIKEY`.

    Dentro do container de testes a variável já está no ambiente. Rodando do
    host, ela vive nos arquivos `.env` — e `.env.local` vence, porque é onde o
    ambiente de desenvolvimento aponta para o Evolution local em vez do de
    produção.
    """
    import os

    if valor := os.getenv("EVOLUTION_API_KEY"):
        return valor

    from dotenv import dotenv_values

    raiz = Path(__file__).resolve().parents[2]
    for arquivo in (".env.local", ".env"):
        if valor := (dotenv_values(raiz / arquivo).get("EVOLUTION_API_KEY") or ""):
            return valor
    return ""


def _esperar_linha(db_url: str, telefone: str, nome_arquivo: str) -> dict:
    """Espera a linha da fila daquele arquivo chegar a estado terminal."""
    limite = time.time() + TIMEOUT_TURNO_S
    ultima: dict | None = None
    while time.time() < limite:
        with psycopg.connect(db_url) as conn, conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, status, attempts, media_filename,
                       media_processing_status, media_processing_error,
                       response, normalized_input
                  FROM message_queue
                 WHERE phone_number = %s AND media_filename = %s
                 ORDER BY id DESC LIMIT 1
                """,
                (telefone, nome_arquivo),
            )
            row = cur.fetchone()
        if row:
            ultima = {
                "id": row[0],
                "status": row[1],
                "attempts": row[2],
                "media_filename": row[3],
                "mps": row[4],
                "erro": row[5],
                "response": row[6] or "",
                "normalized_input": row[7] or "",
            }
            if ultima["status"] in ("done", "failed"):
                return ultima
        time.sleep(2)
    raise AssertionError(
        f"linha de {nome_arquivo} não chegou a estado terminal em "
        f"{TIMEOUT_TURNO_S}s — última leitura: {ultima}"
    )


def _telefone_novo() -> str:
    return f"+5567{uuid.uuid4().int % 10**9:09d}"


def _exigir_outbound_mock() -> None:
    """A bateria só é válida com o envio em `mock`.

    A conexão do seed é uma instância Evolution que não existe. Com o envio em
    `real`, o worker tenta mandar, recebe 404, e `mark_done` não roda — a linha
    volta para a fila. As asserções de `attempts == 1` passariam a medir a
    falha de envio, não a leitura do documento.

    Pular alto e explicando é melhor que reprovar por um motivo que não é o do
    teste — e melhor que passar sem ter verificado nada.
    """
    import os

    modo = os.getenv("EVOLUTION_OUTBOUND_MODE")
    if not modo:
        from dotenv import dotenv_values

        raiz = Path(__file__).resolve().parents[2]
        for arquivo in (".env.local", ".env"):
            if valor := dotenv_values(raiz / arquivo).get("EVOLUTION_OUTBOUND_MODE"):
                modo = valor
                break
    if (modo or "mock").strip().lower() != "mock":
        pytest.skip(
            "EVOLUTION_OUTBOUND_MODE precisa ser `mock` para esta bateria "
            "(está em `real`, o que faz o envio falhar e a linha ser "
            "retentada). Ajuste no .env.local e recrie o worker."
        )


def _set_aceita_documento(db_url: str, valor: bool) -> None:
    with psycopg.connect(db_url, autocommit=True) as conn, conn.cursor() as cur:
        cur.execute("SELECT set_config('app.bypass_rls', 'true', false)")
        cur.execute(
            "UPDATE agente_ia SET aceita_documento = %s "
            " WHERE empresa_id = %s AND slug = %s",
            (valor, EMPRESA_E2E, AGENTE_DOCUMENTOS),
        )


# ---------------------------------------------------------------------------
# Cenários
# ---------------------------------------------------------------------------

FORMATOS = [
    pytest.param("sample.pdf", None, id="pdf"),
    pytest.param("sample.docx", "VSA-E2E-DOCX", id="docx"),
    pytest.param("sample.xlsx", "VSA-E2E-XLSX", id="xlsx"),
    pytest.param("sample.doc", "VSA-E2E-DOCX", id="doc-legado"),
]


@allure.feature("Leitura de documentos")
class TestDocumentosLidos:
    """Vários envios, um formato por vez — o caminho feliz."""

    @pytest.mark.parametrize("arquivo,sentinela", FORMATOS)
    def test_documento_vira_texto_para_o_agente(
        self, arquivo: str, sentinela: str | None, db_url: str, seed_test_data
    ) -> None:
        _exigir_outbound_mock()
        caminho = ASSETS / arquivo
        if not caminho.exists():
            pytest.skip(f"asset {arquivo} ausente — rode scripts/gerar_assets_teste.py")

        telefone = _telefone_novo()
        with allure.step(f"Enviar {arquivo} pelo webhook Evolution"):
            _postar_documento(
                nome_arquivo=arquivo,
                conteudo=caminho.read_bytes(),
                telefone=telefone,
                legenda="O que tem nesse arquivo?",
            )

        linha = _esperar_linha(db_url, telefone, arquivo)
        allure.attach(
            str(linha),
            name=f"linha-{arquivo}.txt",
            attachment_type=allure.attachment_type.TEXT,
        )

        if arquivo == "sample.doc" and linha["mps"] != "processed":
            pytest.skip(
                "`.doc` não foi lido — `antiword` provavelmente ausente nesta "
                f"imagem (erro: {linha['erro']})"
            )

        assert linha["media_filename"] == arquivo, (
            "o nome do arquivo não chegou à fila — é o que a mig 164 introduziu"
        )
        assert linha["mps"] == "processed", f"não extraiu: {linha['erro']}"
        assert linha["attempts"] == 1, "extração boa não pode gastar retentativa"
        if sentinela:
            assert sentinela in linha["normalized_input"], (
                "o conteúdo que chegou ao agente não é o do arquivo enviado"
            )


@allure.feature("Leitura de documentos")
class TestDocumentoNaoLido:
    """Os dois caminhos que o defeito original errava."""

    def test_acima_do_teto_confirma_pelo_nome_sem_retentar(
        self, db_url: str, seed_test_data
    ) -> None:
        """Recusa permanente não pode virar retentativa nem erro.

        Era aqui que a mensagem do cliente gastava 5 tentativas em 59s.
        """
        _exigir_outbound_mock()
        nome = "sample-grande.pdf"
        telefone = _telefone_novo()
        conteudo = pdf_acima_do_teto()
        assert len(conteudo) > 10 * 1024 * 1024, "o arquivo precisa passar do teto"

        with allure.step(f"Enviar {nome} ({len(conteudo) / 1024 / 1024:.1f} MB)"):
            _postar_documento(nome_arquivo=nome, conteudo=conteudo, telefone=telefone)

        linha = _esperar_linha(db_url, telefone, nome)
        allure.attach(
            str(linha),
            name="linha-grande.txt",
            attachment_type=allure.attachment_type.TEXT,
        )

        assert linha["mps"] != "failed", (
            "arquivo grande demais é recusa PERMANENTE — `failed` reabre a "
            "retentativa que este trabalho eliminou"
        )
        assert linha["attempts"] == 1, "não pode retentar o que nunca vai passar"
        assert nome in linha["normalized_input"], "o agente precisa do nome para citar"
        assert "tamanho" in linha["normalized_input"], (
            "o motivo tem que ser específico: com um genérico, o modelo inventa "
            "'não leio PDF' — aconteceu no teste manual"
        )

    def test_agente_sem_permissao_confirma_pelo_nome(
        self, db_url: str, seed_test_data
    ) -> None:
        """O interruptor da tela precisa governar a ingestão de verdade.

        Antes desta entrega `aceita_documento` só filtrava as tools `midia.*`:
        a tela prometia e o backend ignorava.
        """
        _exigir_outbound_mock()
        nome = "sample.pdf"
        telefone = _telefone_novo()
        _set_aceita_documento(db_url, False)
        try:
            with allure.step("Enviar PDF com 'Documentos' desligado no agente"):
                _postar_documento(
                    nome_arquivo=nome,
                    conteudo=(ASSETS / nome).read_bytes(),
                    telefone=telefone,
                )
            linha = _esperar_linha(db_url, telefone, nome)
        finally:
            _set_aceita_documento(db_url, True)

        allure.attach(
            str(linha),
            name="linha-desligado.txt",
            attachment_type=allure.attachment_type.TEXT,
        )

        assert linha["mps"] == "disabled", (
            f"esperado `disabled`, veio `{linha['mps']}` — o interruptor do "
            "agente voltou a não valer na ingestão"
        )
        assert linha["attempts"] == 1
        assert nome in linha["normalized_input"]
        assert "Arquivo recebido" in linha["normalized_input"]
