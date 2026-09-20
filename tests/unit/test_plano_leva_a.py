"""ADR-005 leva A — lógica pura dos gates de plano (sem DB).

- `aplicar_excecoes`: grandfathering por `feature_flag` `plano.<chave>` (D3)
- `StatusAtendimentosMes`: bloqueio suave por atendimentos no mês (D5)
- `require_plano_limit("agentes")` passa a existir (mig 189)
- markers: o novo marker está nas TRÊS listas (worker, internos, reprocessáveis)
"""

from __future__ import annotations

import pytest


def _plano(**kw):
    from whatsapp_langchain.shared.plano_limits import PlanoInfo

    base = dict(
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
        features={"calendar": False},
        limite_agentes=1,
    )
    base.update(kw)
    return PlanoInfo(**base)


class TestLimiteAgentes:
    def test_limite_de_agentes_existe(self) -> None:
        p = _plano(limite_agentes=5)
        assert p.limite_de("agentes") == 5
        assert p.passou_limite("agentes", 5) is True
        assert p.passou_limite("agentes", 4) is False

    def test_default_none_e_ilimitado(self) -> None:
        # Construção posicional antiga (sem o campo novo) continua válida.
        p = _plano()
        p.limite_agentes = None
        assert p.passou_limite("agentes", 999) is False

    def test_require_plano_limit_aceita_agentes(self) -> None:
        from whatsapp_langchain.server.dependencies_plano import (
            RECURSOS_CONTAVEIS,
            require_plano_limit,
        )

        assert "agentes" in RECURSOS_CONTAVEIS
        assert callable(require_plano_limit("agentes"))
        with pytest.raises(ValueError):
            require_plano_limit("foguetes")


class TestGrandfathering:
    def test_limite_null_vira_ilimitado(self) -> None:
        from whatsapp_langchain.shared.plano_limits import aplicar_excecoes

        p = _plano(limite_agentes=1)
        aplicar_excecoes(p, {"limite_agentes": None})
        assert p.limite_agentes is None
        assert p.passou_limite("agentes", 50) is False

    def test_limite_numerico_sobrepoe(self) -> None:
        from whatsapp_langchain.shared.plano_limits import aplicar_excecoes

        p = _plano(limite_usuarios=2, limite_orcamento_ia_usd=5.0)
        aplicar_excecoes(p, {"limite_usuarios": 15, "limite_orcamento_ia_usd": "104.5"})
        assert p.limite_usuarios == 15
        assert p.limite_orcamento_ia_usd == 104.5

    def test_valor_invalido_e_ignorado(self) -> None:
        from whatsapp_langchain.shared.plano_limits import aplicar_excecoes

        p = _plano(limite_usuarios=2)
        aplicar_excecoes(p, {"limite_usuarios": "muitos", "limite_agentes": True})
        assert p.limite_usuarios == 2
        assert p.limite_agentes == 1

    def test_feature_vira_entrada_de_features(self) -> None:
        from whatsapp_langchain.shared.plano_limits import aplicar_excecoes

        p = _plano(features={"mcp": False})
        aplicar_excecoes(p, {"mcp": True, "contexto_max": "extended"})
        assert p.tem_feature("mcp") is True
        assert p.contexto_max == "extended"


class TestStatusAtendimentosMes:
    def test_atingido_e_estrito_maior(self) -> None:
        from whatsapp_langchain.shared.plano_gate import StatusAtendimentosMes

        # o atendimento desta mensagem já está no `usado`: o 100º ainda é atendido
        assert StatusAtendimentosMes(usado=100, limite=100).atingido is False
        assert StatusAtendimentosMes(usado=101, limite=100).atingido is True
        assert StatusAtendimentosMes(usado=10_000, limite=None).atingido is False

    def test_percentual_e_alerta(self) -> None:
        from whatsapp_langchain.shared.plano_gate import StatusAtendimentosMes

        st = StatusAtendimentosMes(usado=80, limite=100)
        assert st.percentual == 80.0
        assert st.em_alerta is True
        assert StatusAtendimentosMes(usado=79, limite=100).em_alerta is False
        assert StatusAtendimentosMes(usado=79, limite=None).percentual is None
        assert StatusAtendimentosMes(usado=79, limite=None).em_alerta is False

    def test_to_dict(self) -> None:
        from whatsapp_langchain.shared.plano_gate import StatusAtendimentosMes

        d = StatusAtendimentosMes(usado=5, limite=100).to_dict()
        assert d == {
            "usado": 5,
            "limite": 100,
            "percentual": 5.0,
            "atingido": False,
            "em_alerta": False,
        }

    def test_texto_do_aviso_muda_ao_atingir(self) -> None:
        from whatsapp_langchain.shared.plano_gate import (
            StatusAtendimentosMes,
            _texto_alerta,
        )

        aviso = _texto_alerta(StatusAtendimentosMes(usado=80, limite=100))
        assert "80 de 100" in aviso and "pausado" not in aviso
        pausa = _texto_alerta(StatusAtendimentosMes(usado=101, limite=100))
        assert "pausado" in pausa


class TestMarker:
    def test_marker_nas_tres_listas(self) -> None:
        from whatsapp_langchain.shared.atendimento import (
            MARKERS_INTERNOS,
            MARKERS_REPROCESSAVEIS,
        )
        from whatsapp_langchain.worker.processor import (
            _MARKERS_SISTEMA,
            LIMITE_PLANO_MARKER,
        )

        assert LIMITE_PLANO_MARKER in _MARKERS_SISTEMA
        assert any(LIMITE_PLANO_MARKER.startswith(m) for m in MARKERS_INTERNOS)
        assert any(LIMITE_PLANO_MARKER.startswith(m) for m in MARKERS_REPROCESSAVEIS)
