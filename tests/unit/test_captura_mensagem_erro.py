"""A captura tem que dizer POR QUE falhou — inclusive quando a exceção não diz.

Regressão do lote 4 em produção (2026-08-25): a captura de grupos do Luis
terminou com status `erro` e o campo `erro` VAZIO, porque `str(httpx.ReadTimeout())`
é string vazia. O operador via "falhou" sem uma linha explicando nada.
"""

from __future__ import annotations

import httpx

from whatsapp_langchain.shared.captura import _descrever_excecao


class TestDescreverExcecao:
    def test_excecao_sem_mensagem_ganha_o_tipo(self):
        """O caso exato de produção: timeout do httpx tem str() vazio."""
        assert str(httpx.ReadTimeout("")) == ""
        assert (
            _descrever_excecao(httpx.ReadTimeout("")) == "ReadTimeout: <sem mensagem>"
        )

    def test_excecao_com_mensagem_e_preservada(self):
        msg = "Evolution API error 401: unauthorized"
        assert _descrever_excecao(RuntimeError(msg)) == msg

    def test_nunca_devolve_vazio(self):
        """Contrato: o que vai pro campo `erro` do lote sempre tem conteúdo."""
        for exc in (
            httpx.ConnectTimeout(""),
            httpx.ReadTimeout(""),
            ValueError(),
            KeyError(),
            RuntimeError(""),
        ):
            assert _descrever_excecao(exc).strip()
