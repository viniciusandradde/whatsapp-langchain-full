"""Tests pra shared/agente — helpers puros (Sub-fase A.5).

Cobre:
- ESTILO_PRESETS (4 níveis: preciso/equilibrado/criativo/muito_criativo)
- resolve_temperatura_top_p (preset + override fino)

Tests com DB ficam na pasta integration (precisa pool real).
"""

from __future__ import annotations

import pytest

from whatsapp_langchain.shared.agente import (
    ESTILO_PRESETS,
    resolve_temperatura_top_p,
)


class TestEstiloPresets:
    def test_4_estilos_definidos(self):
        """Deve ter exatamente os 4 estilos do CHECK constraint da migration."""
        assert set(ESTILO_PRESETS.keys()) == {
            "preciso",
            "equilibrado",
            "criativo",
            "muito_criativo",
        }

    def test_temperatura_crescente_por_estilo(self):
        """Quanto mais "criativo", maior temperatura."""
        temps = [ESTILO_PRESETS[k][0] for k in [
            "preciso", "equilibrado", "criativo", "muito_criativo"
        ]]
        assert temps == sorted(temps), "temperatura deve subir do mais preciso pro mais criativo"

    def test_top_p_crescente_por_estilo(self):
        """top_p também sobe (mais sampling permissivo em estilos criativos)."""
        top_ps = [ESTILO_PRESETS[k][1] for k in [
            "preciso", "equilibrado", "criativo", "muito_criativo"
        ]]
        assert top_ps == sorted(top_ps)

    def test_valores_dentro_dos_limites_validos(self):
        """temperatura ∈ [0, 2], top_p ∈ [0, 1] — bate com CHECK constraints DB."""
        for estilo, (temp, top_p) in ESTILO_PRESETS.items():
            assert 0 <= temp <= 2, f"{estilo}: temperatura {temp} fora [0,2]"
            assert 0 <= top_p <= 1, f"{estilo}: top_p {top_p} fora [0,1]"


class TestResolveTemperaturaTopP:
    def test_preset_preciso_sem_override(self):
        temp, top_p = resolve_temperatura_top_p("preciso", None, None)
        assert temp == 0.1
        assert top_p == 0.6

    def test_preset_equilibrado_eh_default(self):
        temp, top_p = resolve_temperatura_top_p("equilibrado", None, None)
        assert temp == 0.5
        assert top_p == 0.85

    def test_preset_criativo(self):
        temp, top_p = resolve_temperatura_top_p("criativo", None, None)
        assert temp == 0.9
        assert top_p == 0.95

    def test_preset_muito_criativo(self):
        temp, top_p = resolve_temperatura_top_p("muito_criativo", None, None)
        assert temp == 1.3
        assert top_p == 0.99

    def test_override_temperatura_sobrescreve_preset(self):
        """Admin pode forçar temperatura específica ignorando preset."""
        temp, top_p = resolve_temperatura_top_p("preciso", 1.5, None)
        assert temp == 1.5  # override aplicado
        assert top_p == 0.6  # top_p do preset preservado

    def test_override_top_p_sobrescreve_preset(self):
        temp, top_p = resolve_temperatura_top_p("criativo", None, 0.5)
        assert temp == 0.9  # temp do preset
        assert top_p == 0.5  # override

    def test_override_ambos(self):
        """Override completo ignora preset inteiro."""
        temp, top_p = resolve_temperatura_top_p("preciso", 0.7, 0.8)
        assert temp == 0.7
        assert top_p == 0.8

    def test_estilo_invalido_cai_pra_default_equilibrado(self):
        """Defesa em profundidade — se vier estilo errado do DB, não crasha."""
        temp, top_p = resolve_temperatura_top_p("inexistente", None, None)
        # Cai pra (0.5, 0.85) que é o equilibrado
        assert temp == 0.5
        assert top_p == 0.85

    def test_override_zero_eh_respeitado(self):
        """Override == 0.0 é VÁLIDO (mais determinístico ainda) — não cair pra preset."""
        temp, _ = resolve_temperatura_top_p("equilibrado", 0.0, None)
        assert temp == 0.0

    @pytest.mark.parametrize(
        "estilo,esperado_temp,esperado_top_p",
        [
            ("preciso", 0.1, 0.6),
            ("equilibrado", 0.5, 0.85),
            ("criativo", 0.9, 0.95),
            ("muito_criativo", 1.3, 0.99),
        ],
    )
    def test_parametrizado_todos_estilos(self, estilo, esperado_temp, esperado_top_p):
        temp, top_p = resolve_temperatura_top_p(estilo, None, None)
        assert temp == esperado_temp
        assert top_p == esperado_top_p


# ---- A.6: AgenteRuntime.from_agente ----


def _make_agente(**overrides):
    """Builder de AgenteIA pra testes — usa defaults sensatos pros campos
    obrigatórios e permite sobrescrever só o que importa pro teste."""
    from whatsapp_langchain.shared.agente import AgenteIA

    base = {
        "id": 1,
        "empresa_id": 1,
        "slug": "vendas-sp",
        "nome": "Vendas SP",
        "descricao": None,
        "template_catalog": "vsa_tech",
        "prompt_override": None,
        "modelo": None,
        "estilo_resposta": "equilibrado",
        "temperatura_override": None,
        "max_tokens": None,
        "top_p_override": None,
        "tools_enabled": [],
        "tools_config": {},
        "aceita_imagem": True,
        "aceita_audio": True,
        "aceita_documento": True,
        "base_conhecimento_ids": [],
        "variavel_ids": [],
        "mcp_server_ids": [],
        "limite_custo_acao": "permitir",
        "ativo": True,
        "is_default": False,
        "created_by_user_id": None,
        "created_at": None,
        "updated_at": None,
    }
    base.update(overrides)
    return AgenteIA(**base)


class TestAgenteRuntimeFromAgente:
    def test_extrai_template_e_slug(self):
        from whatsapp_langchain.shared.agente import AgenteRuntime

        agente = _make_agente(slug="vendas-sp", template_catalog="vsa_tech")
        rt = AgenteRuntime.from_agente(agente)
        assert rt.slug == "vendas-sp"
        assert rt.template_catalog == "vsa_tech"

    def test_aplica_preset_estilo_quando_sem_override(self):
        from whatsapp_langchain.shared.agente import AgenteRuntime

        agente = _make_agente(estilo_resposta="preciso")
        rt = AgenteRuntime.from_agente(agente)
        assert rt.temperatura == 0.1
        assert rt.top_p == 0.6

    def test_override_fino_vence_preset(self):
        from whatsapp_langchain.shared.agente import AgenteRuntime

        agente = _make_agente(
            estilo_resposta="preciso",
            temperatura_override=1.5,
            top_p_override=0.99,
        )
        rt = AgenteRuntime.from_agente(agente)
        assert rt.temperatura == 1.5
        assert rt.top_p == 0.99

    def test_propaga_modelo_e_max_tokens(self):
        from whatsapp_langchain.shared.agente import AgenteRuntime

        agente = _make_agente(modelo="google/gemini-2.5-flash", max_tokens=2048)
        rt = AgenteRuntime.from_agente(agente)
        assert rt.modelo == "google/gemini-2.5-flash"
        assert rt.max_tokens == 2048

    def test_listas_sao_copiadas_nao_compartilhadas(self):
        """Mutar runtime.tools_enabled não deve afetar agente.tools_enabled."""
        from whatsapp_langchain.shared.agente import AgenteRuntime

        agente = _make_agente(tools_enabled=["a", "b"], base_conhecimento_ids=[1, 2])
        rt = AgenteRuntime.from_agente(agente)
        rt.tools_enabled.append("c")
        rt.base_conhecimento_ids.append(99)
        assert agente.tools_enabled == ["a", "b"]
        assert agente.base_conhecimento_ids == [1, 2]
