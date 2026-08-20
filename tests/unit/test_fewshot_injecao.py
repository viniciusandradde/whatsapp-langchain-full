"""Mig 163 — o comportamento que decide se o few-shot em uso funciona.

Duas coisas que não podem regredir:
1. `format_fewshot_block`: o bloco injetado tem os exemplos + a instrução de
   ADAPTAR (sem ela o agente copia resposta literal de outro cliente).
2. O gate do runtime: `AgenteRuntime.from_agente` propaga `fewshot_enabled`
   — é ele que o worker consulta antes de pagar embedding por mensagem.
"""

from __future__ import annotations


class TestFormatFewshotBlock:
    def test_vazio_devolve_string_vazia(self):
        from whatsapp_langchain.shared.fewshot import format_fewshot_block

        assert format_fewshot_block([]) == ""

    def test_bloco_tem_exemplos_e_instrucao_de_adaptar(self):
        from whatsapp_langchain.shared.fewshot import format_fewshot_block

        bloco = format_fewshot_block(
            [
                ("quanto custa?", "O plano custa R$97.", 0.9),
                ("tem boleto?", "Sim, emitimos boleto.", 0.8),
            ]
        )
        assert "Exemplo 1:" in bloco and "Exemplo 2:" in bloco
        assert "quanto custa?" in bloco
        assert "ADAPTE" in bloco  # anti-cópia-literal — parte do contrato

    def test_trunca_exemplos_gigantes(self):
        """Exemplo enorme não pode inflar o prompt sem limite."""
        from whatsapp_langchain.shared.fewshot import format_fewshot_block

        bloco = format_fewshot_block([("x" * 5000, "y" * 5000, 0.9)])
        # 200 chars da pergunta + 300 da resposta + moldura
        assert len(bloco) < 1200


class TestRuntimePropagaGate:
    def test_from_agente_propaga_fewshot_enabled(self):
        from tests.unit.test_agente import _make_agente
        from whatsapp_langchain.shared.agente import AgenteRuntime

        ligado = AgenteRuntime.from_agente(_make_agente(fewshot_enabled=True))
        desligado = AgenteRuntime.from_agente(_make_agente(fewshot_enabled=False))
        assert ligado.fewshot_enabled is True
        assert desligado.fewshot_enabled is False

    def test_default_do_runtime_e_desligado(self):
        """Runtime construído sem agente (path legacy) nunca liga sozinho."""
        from whatsapp_langchain.shared.agente import AgenteRuntime

        assert AgenteRuntime.__dataclass_fields__["fewshot_enabled"].default is False
