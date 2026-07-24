"""Testes dos helpers de indicadores do A/B de modelo (custo + vazamento)."""

from whatsapp_langchain.server.routes.agente import (
    _VAZAMENTO_RE,
    _custo_usd,
)

CAT = {"gemini-2.5-flash": (0.075, 0.30), "gpt-4o-mini": (0.15, 0.60)}


class TestCusto:
    def test_custo_basico(self):
        # 1M input + 1M output no flash = 0.075 + 0.30
        assert _custo_usd("google/gemini-2.5-flash", 1_000_000, 1_000_000, CAT) == 0.375

    def test_slug_com_provedor(self):
        assert _custo_usd("gpt-4o-mini", 2_000_000, 0, CAT) == 0.30

    def test_modelo_fora_do_catalogo(self):
        assert _custo_usd("modelo/desconhecido", 1000, 1000, CAT) is None

    def test_modelo_none(self):
        assert _custo_usd(None, 1000, 1000, CAT) is None


class TestVazamento:
    def test_tag_xml(self):
        assert _VAZAMENTO_RE.search("<raciocinio_interno>x</raciocinio_interno>")

    def test_decisao_prefixo(self):
        assert _VAZAMENTO_RE.search("Análise da pessoa.\nDecisão: responder curto")

    def test_resposta_limpa_nao_dispara(self):
        assert not _VAZAMENTO_RE.search(
            "Olá, tudo bem? A rematrícula é paga em julho. Obrigado."
        )

    def test_comparacao_matematica_nao_dispara(self):
        assert not _VAZAMENTO_RE.search("Se a nota for menor que 6, fica em DP.")
