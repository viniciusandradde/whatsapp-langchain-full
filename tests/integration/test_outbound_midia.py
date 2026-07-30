"""Smoke do envio de mídia pelo operador (mig 146).

Até aqui o operador só mandava texto: `ResponderInput` tem um campo (`conteudo`)
e a linha outbound guardava tudo em `response`. O app Android pediu gravar áudio
e anexar arquivo, o que exigiu endpoint multipart + duas colunas novas.

O que estes testes protegem:
- a rota existe e exige auth (regressão de registro);
- **a allowlist de MIME é aplicada** — o arquivo vai pro WhatsApp de um cliente
  real, e aceitar `application/x-executable` seria entregar binário a terceiro;
- mídia de operador NÃO cai nas colunas inbound. Esse é o erro silencioso da
  feature: gravar em `media_url` faria a foto do operador aparecer na timeline
  como se o CLIENTE tivesse mandado, sem nenhum erro visível.

    uv run pytest tests/integration/test_outbound_midia.py -v
"""

from __future__ import annotations

import inspect

from fastapi.testclient import TestClient


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestSmoke:
    """Rota registrada e protegida."""

    def test_responder_midia_sem_auth_401(self) -> None:
        resp = _client().post(
            "/api/atendimentos/1/responder-midia",
            files={"arquivo": ("a.ogg", b"x", "audio/ogg")},
        )
        assert resp.status_code == 401, resp.text

    def test_rota_registrada_no_app(self) -> None:
        from whatsapp_langchain.server.main import app

        rotas = {getattr(r, "path", "") for r in app.routes}
        assert "/api/atendimentos/{atendimento_id}/responder-midia" in rotas


class TestMidiaSobDemanda:
    """Mídia servida por endpoint, não embutida na lista.

    Antes disto `/mensagens` devolvia o data-URL base64 inline. Medido em
    produção: PDF de 5 MB numa linha, áudios acima de 100 kB — com `limit=50`,
    dezenas de MB numa resposta, e no 4G a conversa não abria.
    """

    def test_endpoint_de_midia_sem_auth_401(self) -> None:
        resp = _client().get("/api/atendimentos/1/mensagens/2/midia")
        assert resp.status_code == 401, resp.text

    def test_rota_de_midia_registrada(self) -> None:
        from whatsapp_langchain.server.main import app

        rotas = {getattr(r, "path", "") for r in app.routes}
        assert (
            "/api/atendimentos/{atendimento_id}/mensagens/{mensagem_id}/midia" in rotas
        )

    def test_rota_de_midia_nao_e_engolida_pelo_cursor_de_mensagens(self) -> None:
        """`/mensagens/{id}/midia` não pode colidir com `/mensagens`.

        São paths de profundidade diferente, então o FastAPI distingue — mas um
        422 aqui indicaria que o dispatch tentou casar com outra rota e falhou no
        parser de path antes de chegar na auth.
        """
        assert _client().get("/api/atendimentos/1/mensagens/2/midia").status_code != 422

    def test_lista_aceita_incluir_midia(self) -> None:
        """O parâmetro precisa existir com DEFAULT True.

        Default False quebraria o painel web e o APK já instalado, que leem o
        data-URL direto de `media_url`.
        """
        from whatsapp_langchain.server.routes.atendimento import (
            read_atendimento_mensagens,
        )

        param = inspect.signature(read_atendimento_mensagens).parameters[
            "incluir_midia"
        ]
        assert param.default.default is True


class TestAllowlistMime:
    """A allowlist é dado, não código — vale testar o conteúdo dela."""

    def test_audio_imagem_e_pdf_aceitos(self) -> None:
        from whatsapp_langchain.server.routes.atendimento import MIDIA_MIMES_ACEITOS

        for mime in ("audio/ogg", "audio/mpeg", "image/jpeg", "application/pdf"):
            assert mime.startswith(MIDIA_MIMES_ACEITOS), mime

    def test_executavel_e_html_recusados(self) -> None:
        from whatsapp_langchain.server.routes.atendimento import MIDIA_MIMES_ACEITOS

        # HTML entra na lista de recusados de propósito: anexo HTML é vetor
        # clássico de phishing, e nada num atendimento precisa mandar página.
        for mime in ("application/x-executable", "text/html", "application/zip", ""):
            assert not mime.startswith(MIDIA_MIMES_ACEITOS), mime


class TestSeparacaoInboundOutbound:
    """Mídia do operador não pode ocupar as colunas do cliente."""

    def test_persist_grava_nas_colunas_response_media(self) -> None:
        """O INSERT usa `response_media_*`, nunca `media_url`/`media_type`.

        Teste de fonte porque o erro é invisível em runtime: a bolha apareceria,
        só do lado errado, e nenhum status de erro seria emitido.
        """
        from whatsapp_langchain.shared import outbound

        fonte = inspect.getsource(outbound._persist_outbound_row)

        # Só a LISTA DE COLUNAS do INSERT — não o corpo inteiro da função, senão
        # os nomes dos próprios parâmetros (`media_url=...`) casariam e o teste
        # passaria a medir outra coisa.
        inicio = fonte.index("INSERT INTO message_queue")
        colunas = {
            c.strip()
            for c in fonte[inicio : fonte.index("VALUES", inicio)]
            .partition("(")[2]
            .rpartition(")")[0]
            .replace("\n", "")
            .split(",")
        }

        assert "response_media_url" in colunas
        assert "response_media_type" in colunas
        # As colunas INBOUND não podem ser escritas por este INSERT.
        assert "media_url" not in colunas
        assert "media_type" not in colunas

    def test_insert_tem_colunas_valores_e_args_alinhados(self) -> None:
        """Colunas, placeholders e argumentos batem.

        Este INSERT é o mesmo caminho da resposta de TEXTO do painel. Acrescentar
        duas colunas e esquecer dois `%s` não quebra o envio de mídia: quebra
        TODA resposta manual, inclusive a do operador no navegador. Contar isso à
        mão é justamente o que não se deve confiar.
        """
        from whatsapp_langchain.shared import outbound

        fonte = inspect.getsource(outbound._persist_outbound_row)
        inicio = fonte.index("INSERT INTO message_queue")
        sql = fonte[inicio : fonte.index('"""', inicio)]

        colunas = [
            c.strip()
            for c in sql[sql.index("(") + 1 : sql.index(")")]
            .replace("\n", " ")
            .split(",")
            if c.strip()
        ]
        trecho_values = sql[sql.index("VALUES") :]
        placeholders = trecho_values.count("%s")
        # `'done'`, `NOW()`, `NOW()` — valores fixos, sem argumento.
        literais = trecho_values.count("NOW()") + trecho_values.count("'done'")

        assert len(colunas) == placeholders + literais, (
            f"{len(colunas)} colunas contra {placeholders} placeholders "
            f"+ {literais} literais"
        )

    def test_audio_vai_por_send_audio_e_nao_send_media(self) -> None:
        """Nota de voz tem endpoint próprio no Evolution.

        Áudio mandado por `sendMedia` chega como documento — sem player e sem
        forma de onda. É a diferença entre "nota de voz" e "arquivo anexado".
        """
        from whatsapp_langchain.shared.outbound import send_outbound_manual_midia

        fonte = inspect.getsource(send_outbound_manual_midia)
        assert 'mime.startswith("audio/")' in fonte
        assert "enviar_audio" in fonte

    def test_evolution_client_tem_endpoint_de_nota_de_voz(self) -> None:
        from whatsapp_langchain.worker.evolution_client import (
            EVOLUTION_SEND_AUDIO_PATH,
            EvolutionClient,
        )

        assert "sendWhatsAppAudio" in EVOLUTION_SEND_AUDIO_PATH
        assert hasattr(EvolutionClient, "send_audio")

    def test_lista_de_mensagens_devolve_as_colunas_novas(self) -> None:
        """Sem isto o app envia a mídia e não vê o que mandou."""
        from whatsapp_langchain.shared import atendimento

        fonte = inspect.getsource(atendimento.list_atendimento_mensagens)
        assert "response_media_url" in fonte
        assert "response_media_type" in fonte
