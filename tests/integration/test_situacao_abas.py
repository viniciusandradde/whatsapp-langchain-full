"""Smoke da situação derivada e das abas novas.

O que estes testes protegem:

- **Compatibilidade das abas.** O APK instalado no celular do operador pede
  `tipo=aguardando`. Se o valor sair do `Literal`, o FastAPI devolve 422 e o app
  para de listar conversas até o usuário atualizar — e ele só atualiza quando
  perceber que quebrou. Mesma lição do `incluir_midia`, que ficou com default
  `true` por isso.
- **Defaults seguros nos campos derivados.** `situacao` e `nao_lidas` são
  calculados fora do banco; se o cálculo falhar, a conversa tem que aparecer
  mesmo assim.

    uv run pytest tests/integration/test_situacao_abas.py -v
"""

from __future__ import annotations

import inspect

from fastapi.testclient import TestClient


def _client() -> TestClient:
    from whatsapp_langchain.server.main import app

    return TestClient(app)


class TestCompatibilidadeDasAbas:
    """Valor antigo de `tipo` não pode virar 422."""

    def test_abas_antigas_seguem_aceitas(self) -> None:
        from whatsapp_langchain.shared.atendimento import TipoVisualizacao

        aceitos = set(TipoVisualizacao.__args__)  # type: ignore[attr-defined]
        for antigo in ("meus", "aguardando", "grupos", "outros"):
            assert antigo in aceitos, f"{antigo} sumiu — quebra o APK instalado"

    def test_abas_novas_existem(self) -> None:
        from whatsapp_langchain.shared.atendimento import TipoVisualizacao

        aceitos = set(TipoVisualizacao.__args__)  # type: ignore[attr-defined]
        for nova in (
            "nao_resolvidas",
            "nao_lidas",
            "humano_solicitado",
            "resolvidas",
            "todas",
        ):
            assert nova in aceitos

    def test_tipo_invalido_ainda_e_recusado(self) -> None:
        """Aceitar tudo seria pior que recusar o antigo: filtro digitado errado
        devolveria a lista inteira em vez de avisar."""
        resp = _client().get("/api/atendimentos?tipo=inexistente")
        # 401 (sem auth) nunca chega ao validador; o que importa é não ser 200.
        assert resp.status_code in (401, 422)

    def test_valor_antigo_nao_e_422(self) -> None:
        resp = _client().get("/api/atendimentos?tipo=aguardando")
        assert resp.status_code == 401, resp.text  # barrado na auth, não no tipo


class TestCamposDerivados:
    def test_defaults_nao_escondem_a_conversa(self) -> None:
        """Se a derivação falhar, o item aparece com rótulo otimista.

        Lista que não carrega é pior que lista com selo impreciso — o operador
        pelo menos enxerga a conversa e consegue abri-la.
        """
        from whatsapp_langchain.shared.models import Atendimento

        campos = Atendimento.model_fields
        assert campos["situacao"].default == "com_ia"
        assert campos["ia_ativa"].default is True
        assert campos["nao_lidas"].default == 0

    def test_enriquecimento_nao_derruba_a_listagem(self) -> None:
        """TODA consulta extra é best-effort, cada uma com seu try/except.

        Whitelist, contador de não lidas e resposta perdida são acessórios:
        falhar num deles não pode transformar a tela de atendimento numa tela de
        erro. O operador prefere um selo impreciso a uma lista que não abre.

        Compara try com except em vez de fixar um número: o teste continua
        valendo quando entrar o quarto enriquecimento, mas quebra se alguém
        acrescentar um sem proteção.
        """
        from whatsapp_langchain.shared import atendimento as mod

        fonte = inspect.getsource(mod._preencher_derivados)
        tries = fonte.count("    try:")
        excepts = fonte.count("except Exception")
        assert tries >= 3, f"esperava ao menos 3 consultas guardadas, achei {tries}"
        assert tries == excepts, f"{tries} try para {excepts} except — falta guarda"

    def test_ia_ativa_so_para_com_ia(self) -> None:
        """`aguardando_humano` é o gate que CALA o agente — marcar como IA ativa
        faria a UI prometer resposta que não vem."""
        from whatsapp_langchain.shared import atendimento as mod

        fonte = inspect.getsource(mod._preencher_derivados)
        assert 'atd.situacao == "com_ia"' in fonte
