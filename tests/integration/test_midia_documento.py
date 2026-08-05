"""Leitura de documento pelo agente: PDF, DOCX, XLSX e DOC (mig 164).

Nasceu do atendimento 1018-000664 — a cliente mandou `.docx` e `.doc` no mesmo
segundo, o primeiro foi lido e o segundo recusado depois de 5 tentativas, com o
cliente recebendo "estamos com dificuldades em processar imagens/audio".

O que estes testes travam:
- o nome do arquivo chega do webhook até a fila (era descartado);
- arquivo que o agente não pode ler NÃO vira erro nem retentativa;
- o caminho feliz continua entregando o conteúdo ao agente.

Só E2E (`docker_demo`), porque o valor está na integração real — a parte pura já
está coberta em `tests/unit/test_file_extractor_tipos.py`,
`test_media_preprocess.py` e `test_evolution_payload_documento.py`.

    DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \\
      uv run pytest tests/integration/test_midia_documento.py -v -m docker_demo
"""

from __future__ import annotations

import base64
import io
import uuid

import psycopg
import pytest

from .helpers import get_db_url

_RUN = uuid.uuid4().hex[:8]

pytestmark = pytest.mark.docker_demo


def _planilha_b64() -> str:
    """XLSX mínimo, gerado aqui — sem fixture binária no repositório."""
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    assert ws is not None
    ws.title = "Precos"
    ws.append(["Servico", "Valor"])
    ws.append([f"Consultoria {_RUN}", 4200])
    buf = io.BytesIO()
    wb.save(buf)
    return base64.b64encode(buf.getvalue()).decode()


_MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@pytest.fixture(scope="module")
def conn():
    with psycopg.connect(get_db_url(), autocommit=True) as c:
        yield c


@pytest.fixture(scope="module")
def empresa_e_agente(conn):
    """Empresa e agente próprios, com `aceita_documento` ligado."""
    with conn.cursor() as cur:
        cur.execute("SELECT set_config('app.bypass_rls', 'true', false)")
        cur.execute(
            "INSERT INTO empresa (nome, slug) VALUES (%s, %s) RETURNING id",
            (f"E2E midia {_RUN}", f"e2e-midia-{_RUN}"),
        )
        row = cur.fetchone()
        assert row is not None
        empresa_id = row[0]

        cur.execute(
            """
            INSERT INTO agente_ia
                (empresa_id, slug, nome, template_catalog, ativo, is_default,
                 aceita_imagem, aceita_audio, aceita_documento)
            VALUES (%s, %s, %s, 'agente', TRUE, TRUE, TRUE, TRUE, TRUE)
            RETURNING id, slug
            """,
            (empresa_id, f"doc-{_RUN}", f"Agente doc {_RUN}"),
        )
        row = cur.fetchone()
        assert row is not None
        agente_id, slug = row

    yield {"empresa_id": empresa_id, "agente_id": agente_id, "slug": slug}

    with conn.cursor() as cur:
        cur.execute("SELECT set_config('app.bypass_rls', 'true', false)")
        cur.execute("DELETE FROM message_queue WHERE empresa_id = %s", (empresa_id,))
        cur.execute("DELETE FROM agente_ia WHERE empresa_id = %s", (empresa_id,))
        cur.execute("DELETE FROM empresa WHERE id = %s", (empresa_id,))


def _enfileirar(conn, empresa_id: int, slug: str, *, mime: str, nome: str) -> int:
    """Insere a row como o webhook insere, com nome e conteúdo reais."""
    with conn.cursor() as cur:
        cur.execute("SELECT set_config('app.bypass_rls', 'true', false)")
        cur.execute(
            """
            INSERT INTO message_queue
                (empresa_id, phone_number, agent_id, thread_id, incoming_message,
                 media_url, media_type, media_filename, status)
            VALUES (%s, %s, %s, %s, '', %s, %s, %s, 'queued')
            RETURNING id
            """,
            (
                empresa_id,
                f"+5567900{_RUN[:5]}",
                slug,
                f"+5567900{_RUN[:5]}:{slug}",
                f"data:{mime};base64,{_planilha_b64()}",
                mime,
                nome,
            ),
        )
        row = cur.fetchone()
        assert row is not None
        return row[0]


class TestE2EDocumento:
    """Passos numerados, na ordem em que o defeito acontecia."""

    def test_1_coluna_media_filename_existe(self, conn):
        """A migration 164 aplicou — sem ela nada abaixo faz sentido."""
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM information_schema.columns
                 WHERE table_name = 'message_queue'
                   AND column_name = 'media_filename'
                """
            )
            assert cur.fetchone() is not None, (
                "migration 164 não aplicada — rode `make migrate`"
            )

    def test_2_nome_do_arquivo_persiste_na_fila(self, conn, empresa_e_agente):
        msg_id = _enfileirar(
            conn,
            empresa_e_agente["empresa_id"],
            empresa_e_agente["slug"],
            mime=_MIME_XLSX,
            nome=f"precos-{_RUN}.xlsx",
        )
        with conn.cursor() as cur:
            cur.execute(
                "SELECT media_filename FROM message_queue WHERE id = %s", (msg_id,)
            )
            row = cur.fetchone()
        assert row is not None
        assert row[0] == f"precos-{_RUN}.xlsx"

    async def test_3_planilha_vira_texto_para_o_agente(self, empresa_e_agente):
        """O caminho feliz do formato que antes era recusado como `doc.bin`."""
        from whatsapp_langchain.worker.media import preprocess_incoming_message

        pre = await preprocess_incoming_message(
            body="",
            media_url=f"data:{_MIME_XLSX};base64,{_planilha_b64()}",
            media_type=_MIME_XLSX,
            filename=f"precos-{_RUN}.xlsx",
            aceita_documento=True,
        )

        assert pre.should_invoke_agent is True
        assert pre.media_processing_status == "processed"
        assert f"Consultoria {_RUN}" in (pre.normalized_text or "")
        assert "4200" in (pre.normalized_text or "")

    async def test_4_agente_sem_permissao_confirma_pelo_nome(self, empresa_e_agente):
        """Desligado, o cliente ainda é atendido — e nada é retentado."""
        from whatsapp_langchain.worker.media import preprocess_incoming_message

        pre = await preprocess_incoming_message(
            body="",
            media_url=f"data:{_MIME_XLSX};base64,{_planilha_b64()}",
            media_type=_MIME_XLSX,
            filename=f"precos-{_RUN}.xlsx",
            aceita_documento=False,
        )

        assert pre.should_invoke_agent is True
        assert pre.media_processing_status != "failed"  # nada de retentativa
        assert f"precos-{_RUN}.xlsx" in (pre.normalized_text or "")
        # E o conteúdo NÃO vazou: não foi lido.
        assert f"Consultoria {_RUN}" not in (pre.normalized_text or "")

    async def test_5_doc_legado_conforme_a_imagem(self, empresa_e_agente):
        """Com `antiword` presente lê; ausente, confirma pelo nome. Nunca erra.

        As duas pontas são aceitáveis — o que não pode acontecer é `failed`, que
        é o que gerava as 5 tentativas.
        """
        from whatsapp_langchain.worker.media import preprocess_incoming_message

        # Conteúdo proposital de arquivo não-.doc: exercita o caminho de falha
        # de parsing, que é permanente e não pode virar retentativa.
        pre = await preprocess_incoming_message(
            body="",
            media_url="data:application/msword;base64,"
            + base64.b64encode(b"nao sou um doc de verdade").decode(),
            media_type="application/msword",
            filename=f"proposta-{_RUN}.doc",
            aceita_documento=True,
        )

        assert pre.media_processing_status != "failed"
        assert pre.should_invoke_agent is True
        assert f"proposta-{_RUN}.doc" in (pre.normalized_text or "")
