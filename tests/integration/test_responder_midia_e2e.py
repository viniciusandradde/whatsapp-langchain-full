"""E2E do `POST /api/atendimentos/{id}/responder-midia` com conversão de áudio.

O painel web grava WebM (Chrome) ou MP4 (Safari); o endpoint tem que devolver
200 e gravar a bolha de saída já como OGG/Opus (`audio/ogg`) — é o que o
cliente recebeu pelo `sendWhatsAppAudio`. Anexo de imagem não é convertido e
áudio inválido é 400 legível, sem row no banco.

Roda contra a API do dev em modo mock (`EVOLUTION_OUTBOUND_MODE=mock`): o
`send_audio` devolve um id `mock-evo-audio-…` sem falar com o WhatsApp.

    DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \
    INTERNAL_SERVICE_TOKEN=dev-token-change-in-production \
    uv run pytest tests/integration/test_responder_midia_e2e.py -v
"""

from __future__ import annotations

import io
import json
import math
import struct
import uuid

import httpx
import psycopg
import pytest

from .helpers import API_BASE_URL, get_admin_api_headers, get_db_url

_RUN = uuid.uuid4().hex[:8]
_D = f"{int(_RUN, 16) % 1_000_000:06d}"
_TEL = f"+5567996{_D}"


def _webm_opus(segundos: float = 0.5) -> bytes:
    """Meio segundo de tom em WebM/Opus — o que o Chrome grava."""
    import av

    rate = 48000
    pcm = b"".join(
        struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / rate)))
        for i in range(int(rate * segundos))
    )
    buf = io.BytesIO()
    saida = av.open(buf, "w", format="webm")
    stream = saida.add_stream("libopus", rate=rate, layout="mono")
    entrada = av.open(
        io.BytesIO(pcm), "r", format="s16le", options={"ar": str(rate), "ac": "1"}
    )
    resampler = av.AudioResampler(format="s16", layout="mono", rate=rate)
    for frame in entrada.decode(audio=0):
        for f in resampler.resample(frame):
            saida.mux(stream.encode(f))  # type: ignore[arg-type]
    saida.mux(stream.encode(None))  # type: ignore[arg-type]
    saida.close()
    entrada.close()
    return buf.getvalue()


_PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000d49444154789c6360000002000154a24f5d0000000049454e44ae426082"
)


@pytest.mark.docker_demo
class TestE2E:
    @pytest.fixture(scope="class")
    def dados(self):
        conn = psycopg.connect(get_db_url(), autocommit=True)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO empresa (nome, slug, plano, status) "
            "VALUES (%s, %s, 'free', 'active') RETURNING id",
            (f"E2E Midia {_RUN}", f"e2e-midia-{_RUN}"),
        )
        empresa_id = cur.fetchone()[0]
        # Conexão Evolution com instance_name no payload: `_build_client` exige
        # a identidade da conexão; api_url/api_key vêm do env do dev e o modo
        # mock não fala com a Evolution.
        cur.execute(
            "INSERT INTO conexao (empresa_id, provider, from_number, status, payload_json) "
            "VALUES (%s, 'evolution', %s, 'active', %s::jsonb) RETURNING id",
            (empresa_id, _TEL, json.dumps({"instance_name": f"e2e-mock-{_RUN}"})),
        )
        conexao_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO cliente (empresa_id, telefone, nome) "
            "VALUES (%s, %s, %s) RETURNING id",
            (empresa_id, _TEL, f"Cliente Midia {_RUN}"),
        )
        cliente_id = cur.fetchone()[0]
        user_id = f"test-midia-{_RUN}"
        cur.execute(
            """
            INSERT INTO auth."user" (id, name, email, "emailVerified",
                                      "createdAt", "updatedAt", status,
                                      is_superadmin)
            VALUES (%s, 'Test Midia', %s, TRUE, NOW(), NOW(), 'active', TRUE)
            """,
            (user_id, f"{user_id}@e2e.test"),
        )
        cur.execute(
            """
            INSERT INTO atendimento
                (empresa_id, cliente_id, conexao_id, agente_atual, status,
                 assigned_to_user_id)
            VALUES (%s, %s, %s, 'agente', 'em_andamento', %s) RETURNING id
            """,
            (empresa_id, cliente_id, conexao_id, user_id),
        )
        atd_id = cur.fetchone()[0]
        yield {"empresa_id": empresa_id, "atd_id": atd_id, "user_id": user_id}
        cur.execute("DELETE FROM message_queue WHERE empresa_id = %s", (empresa_id,))
        cur.execute("DELETE FROM atendimento WHERE empresa_id = %s", (empresa_id,))
        cur.execute("DELETE FROM cliente WHERE empresa_id = %s", (empresa_id,))
        cur.execute("DELETE FROM conexao WHERE empresa_id = %s", (empresa_id,))
        cur.execute("DELETE FROM empresa WHERE id = %s", (empresa_id,))
        cur.execute('DELETE FROM auth."user" WHERE id = %s', (user_id,))
        conn.close()

    def _h(self, dados: dict) -> dict:
        h = get_admin_api_headers()
        h["X-User-Id"] = dados["user_id"]
        h["X-Empresa-Id"] = str(dados["empresa_id"])
        return h

    def _post(
        self, dados: dict, nome: str, conteudo: bytes, mime: str, legenda: str = ""
    ):
        return httpx.post(
            f"{API_BASE_URL}/api/atendimentos/{dados['atd_id']}/responder-midia",
            headers=self._h(dados),
            files={"arquivo": (nome, conteudo, mime)},
            data={"legenda": legenda},
            timeout=60,
        )

    def _rows(self, dados: dict) -> list[tuple]:
        conn = psycopg.connect(get_db_url(), autocommit=True)
        cur = conn.execute(
            """
            SELECT response_media_type, left(response_media_url, 22), incoming_message,
                   response, message_id, response_media_filename
              FROM message_queue
             WHERE atendimento_id = %s
             ORDER BY id
            """,
            (dados["atd_id"],),
        )
        rows = cur.fetchall()
        conn.close()
        return rows

    def test_1_webm_do_chrome_vira_nota_de_voz_ogg(self, dados) -> None:
        r = self._post(dados, "gravacao.webm", _webm_opus(), "audio/webm")
        assert r.status_code == 200, r.text
        msg = r.json()["mensagem"]
        assert msg["response_media_type"] == "audio/ogg"
        # Nota de voz não guarda nome: "gravacao.webm" nem é mais o formato.
        assert msg["response_media_filename"] is None
        rows = self._rows(dados)
        assert len(rows) == 1
        tipo, prefixo, incoming, response, message_id, nome = rows[0]
        assert tipo == "audio/ogg"
        assert prefixo == "data:audio/ogg;base64,"
        assert incoming == ""  # row de saída, não fala do cliente
        assert message_id.startswith("mock-evo-audio-")
        assert nome is None

    def test_2_imagem_com_legenda_nao_e_convertida(self, dados) -> None:
        r = self._post(
            dados, "foto.png", _PNG_1PX, "image/png", legenda="Olá {{cliente.nome}}"
        )
        assert r.status_code == 200, r.text
        # Nome real do arquivo (mig 186) na resposta E na listagem — é o que a
        # bolha mostra no lugar de "image/png".
        assert r.json()["mensagem"]["response_media_filename"] == "foto.png"
        rows = self._rows(dados)
        assert len(rows) == 2
        tipo, prefixo, _, response, _, nome = rows[1]
        assert tipo == "image/png"
        assert prefixo.startswith("data:image/png;base64")
        assert nome == "foto.png"
        # legenda renderizada com o nome do cliente
        assert response == f"Olá Cliente Midia {_RUN}"
        lista = httpx.get(
            f"{API_BASE_URL}/api/atendimentos/{dados['atd_id']}/mensagens",
            headers=self._h(dados),
            params={"incluir_midia": "false"},
            timeout=30,
        )
        assert lista.status_code == 200, lista.text
        ultima = lista.json()["mensagens"][-1]
        assert ultima["response_media_filename"] == "foto.png"
        assert ultima["media_filename"] is None
        # E o download leva o nome no Content-Disposition (abrir/baixar salva
        # "foto.png", não o id da mensagem).
        midia = httpx.get(
            f"{API_BASE_URL}/api/atendimentos/{dados['atd_id']}/mensagens/{ultima['id']}/midia",
            headers=self._h(dados),
            params={"lado": "out"},
            timeout=30,
        )
        assert midia.status_code == 200, midia.text
        assert "foto.png" in midia.headers.get("content-disposition", "")

    def test_3_audio_invalido_e_400_sem_row(self, dados) -> None:
        r = self._post(dados, "lixo.webm", b"isto nao e audio" * 200, "audio/webm")
        assert r.status_code == 400, r.text
        assert "áudio" in r.json()["detail"].lower()
        assert len(self._rows(dados)) == 2

    def test_4_tipo_recusado_e_400(self, dados) -> None:
        r = self._post(dados, "x.exe", b"MZ", "application/x-msdownload")
        assert r.status_code == 400, r.text
