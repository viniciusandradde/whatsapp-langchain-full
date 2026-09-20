"""ADR-005 leva B — lógica pura (sem DB): mídia bloqueada pelo plano vira o
bloco "[Arquivo recebido …]" (recusa permanente, agente ainda responde);
áudio não tem chave de plano; `plano_libera` libera quando o plano é ilegível."""

from __future__ import annotations

from unittest.mock import patch

from whatsapp_langchain.worker.media import preprocess_incoming_message


class TestMidiaBloqueadaPeloPlano:
    async def test_documento_sem_feature_vira_bloco_sem_ler(self) -> None:
        r = await preprocess_incoming_message(
            body="Segue o orçamento",
            media_url="https://example.com/orc.pdf",
            media_type="application/pdf",
            filename="orçamento.pdf",
            plano_documento=False,
        )
        assert r.should_invoke_agent is True  # o agente explica, não uma frase fixa
        assert r.auto_response is None
        assert r.media_processing_status == "plano_bloqueado"
        texto = r.normalized_text or ""
        assert "Segue o orçamento" in texto
        assert "orçamento.pdf" in texto
        assert "não está incluída no plano" in texto

    async def test_imagem_sem_feature_vira_bloco_sem_ler(self) -> None:
        r = await preprocess_incoming_message(
            body="",
            media_url="https://example.com/i.jpg",
            media_type="image/jpeg",
            plano_imagem=False,
        )
        assert r.should_invoke_agent is True
        assert r.media_processing_status == "plano_bloqueado"
        assert "uma imagem" in (r.normalized_text or "")

    async def test_audio_ignora_chaves_de_plano(self) -> None:
        # Áudio do cliente é liberado em todo plano: as chaves de imagem e
        # documento desligadas não podem interceptar. Com `aceita_audio=False`
        # o caminho para no gate do AGENTE (status "disabled"), provando que
        # o gate de plano não pegou antes.
        r = await preprocess_incoming_message(
            body="",
            media_url="https://example.com/a.ogg",
            media_type="audio/ogg",
            aceita_audio=False,
            plano_imagem=False,
            plano_documento=False,
        )
        assert r.media_processing_status == "disabled"

    async def test_plano_vem_antes_do_gate_do_agente(self) -> None:
        # Os dois desligados: o motivo gravado é o do plano (é o que o
        # operador precisa saber para resolver — upgrade, não configuração).
        r = await preprocess_incoming_message(
            body="",
            media_url="https://example.com/i.jpg",
            media_type="image/jpeg",
            aceita_imagem=False,
            plano_imagem=False,
        )
        assert r.media_processing_status == "plano_bloqueado"


class TestPlanoLibera:
    async def test_plano_ilegivel_libera_com_log(self) -> None:
        from whatsapp_langchain.shared import plano_gate

        async def _explode(pool, empresa_id):
            raise RuntimeError("banco fora")

        with patch.object(plano_gate, "get_plano_info", _explode):
            assert await plano_gate.plano_libera(None, 1, "fewshot") is True  # type: ignore[arg-type]

    async def test_le_a_feature_do_plano(self) -> None:
        from whatsapp_langchain.shared import plano_gate
        from whatsapp_langchain.shared.plano_limits import PlanoInfo

        info = PlanoInfo(
            empresa_id=1,
            plano_id=1,
            plano_slug="free",
            plano_nome="Free",
            preco_mensal_brl=0.0,
            limite_usuarios=2,
            limite_conexoes=1,
            limite_atendimentos_mes=100,
            limite_orcamento_ia_usd=5.0,
            limite_documentos_kb=5,
            features={"fewshot": False, "documentos_cliente": True},
        )

        async def _fake(pool, empresa_id):
            return info

        with patch.object(plano_gate, "get_plano_info", _fake):
            assert await plano_gate.plano_libera(None, 1, "fewshot") is False  # type: ignore[arg-type]
            assert await plano_gate.plano_libera(None, 1, "documentos_cliente") is True  # type: ignore[arg-type]
            assert await plano_gate.plano_libera(None, 1, "chave_inexistente") is False  # type: ignore[arg-type]
