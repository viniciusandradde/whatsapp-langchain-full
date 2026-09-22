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
        temps = [
            ESTILO_PRESETS[k][0]
            for k in ["preciso", "equilibrado", "criativo", "muito_criativo"]
        ]
        assert temps == sorted(temps), (
            "temperatura deve subir do mais preciso pro mais criativo"
        )

    def test_top_p_crescente_por_estilo(self):
        """top_p também sobe (mais sampling permissivo em estilos criativos)."""
        top_ps = [
            ESTILO_PRESETS[k][1]
            for k in ["preciso", "equilibrado", "criativo", "muito_criativo"]
        ]
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
        # mig 143 — default do banco é TRUE (anuncia o departamento ao cliente)
        "anuncia_transferencia": True,
        # mig 163 — default do banco é FALSE (few-shot é opt-in por agente)
        "fewshot_enabled": False,
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


class TestModeloEfetivo:
    """`resolver_modelo_efetivo` é a regra ÚNICA de "qual modelo o agente usa".

    Até 22/09/2026 a lista de agentes lia `agente_ia.modelo` (legada, parada
    desde 22/08) enquanto editor e worker liam `modelo_provedor/modelo_nome`:
    o card da VSA dizia gemini-2.5-flash-lite e nenhum turno usava isso.
    """

    def test_provedor_e_nome_vencem_a_legada(self):
        from whatsapp_langchain.shared.agente import resolver_modelo_efetivo

        assert (
            resolver_modelo_efetivo("deepseek", "deepseek-v4.1-flash", "google/x")
            == "deepseek/deepseek-v4.1-flash"
        )

    def test_sem_par_completo_cai_na_legada(self):
        from whatsapp_langchain.shared.agente import resolver_modelo_efetivo

        assert (
            resolver_modelo_efetivo("google", None, "google/legado") == "google/legado"
        )
        assert resolver_modelo_efetivo(None, "nome", "google/legado") == "google/legado"
        assert resolver_modelo_efetivo("", "", "google/legado") == "google/legado"

    def test_nada_preenchido_e_none(self):
        from whatsapp_langchain.shared.agente import resolver_modelo_efetivo

        assert resolver_modelo_efetivo(None, None, None) is None
        assert resolver_modelo_efetivo(None, None, "") is None

    def test_to_dict_e_runtime_concordam(self):
        from whatsapp_langchain.shared.agente import AgenteRuntime

        agente = _make_agente(
            modelo="google/gemini-2.5-flash-lite",
            modelo_provedor="deepseek",
            modelo_nome="deepseek-v4.1-flash",
        )
        assert agente.modelo_efetivo == "deepseek/deepseek-v4.1-flash"
        assert agente.to_dict()["modelo_efetivo"] == "deepseek/deepseek-v4.1-flash"
        # A legada continua exposta crua — quem quiser ver o fóssil, vê.
        assert agente.to_dict()["modelo"] == "google/gemini-2.5-flash-lite"
        assert (
            AgenteRuntime.from_agente(agente).modelo == "deepseek/deepseek-v4.1-flash"
        )

    def test_sql_da_regra_nao_tem_porcento(self):
        # `%` em SQL literal quebra o psycopg (gotcha do repo).
        from whatsapp_langchain.shared.agente import SQL_MODELO_EFETIVO

        assert "%" not in SQL_MODELO_EFETIVO
        assert "modelo_provedor || '/' || modelo_nome" in SQL_MODELO_EFETIVO


def _pool_update_capturando():
    """Pool falso: captura o UPDATE do `update_agente` sem banco."""
    from unittest.mock import AsyncMock, MagicMock

    cur = AsyncMock()
    cur.fetchone = AsyncMock(return_value=None)
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cur)
    conn.transaction.return_value.__aenter__ = AsyncMock(return_value=None)
    conn.transaction.return_value.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


class TestUpdateAgenteSincronizaModeloLegado:
    """O PUT com provedor/nome também grava a coluna legada `modelo`."""

    async def test_provedor_e_nome_no_patch_entram_como_parametro(self):
        from whatsapp_langchain.shared.agente import update_agente

        pool, conn = _pool_update_capturando()
        await update_agente(
            pool, 1, "vendas", modelo_provedor="deepseek", modelo_nome="deepseek-v3.2"
        )
        sql, params = conn.execute.call_args.args
        sql = str(sql)
        assert (
            "modelo = CASE WHEN COALESCE(%s, '') <> '' AND COALESCE(%s, '') <> ''"
            in sql
        )
        assert "THEN %s || '/' || %s ELSE modelo END" in sql
        # provedor, nome (SET normais) + prov, nome, prov, nome (CASE) + empresa, slug
        assert list(params) == [
            "deepseek",
            "deepseek-v3.2",
            "deepseek",
            "deepseek-v3.2",
            "deepseek",
            "deepseek-v3.2",
            1,
            "vendas",
        ]

    async def test_so_o_nome_no_patch_usa_o_provedor_gravado(self):
        from whatsapp_langchain.shared.agente import update_agente

        pool, conn = _pool_update_capturando()
        await update_agente(pool, 1, "vendas", modelo_nome="gemini-2.5-flash")
        sql, params = conn.execute.call_args.args
        sql = str(sql)
        # O valor ANTIGO da coluna é o que o SET enxerga sem parâmetro.
        assert "COALESCE(modelo_provedor, '') <> '' AND COALESCE(%s, '') <> ''" in sql
        assert "THEN modelo_provedor || '/' || %s ELSE modelo END" in sql
        assert list(params) == [
            "gemini-2.5-flash",
            "gemini-2.5-flash",
            "gemini-2.5-flash",
            1,
            "vendas",
        ]

    async def test_patch_com_modelo_legado_explicito_nao_duplica_o_set(self):
        from whatsapp_langchain.shared.agente import update_agente

        pool, conn = _pool_update_capturando()
        await update_agente(
            pool, 1, "vendas", modelo="google/gemini-2.5-flash-lite", modelo_nome="x"
        )
        sql = str(conn.execute.call_args.args[0])
        assert sql.count("modelo = ") == 1
        assert "CASE WHEN" not in sql

    async def test_patch_sem_modelo_nao_mexe_na_legada(self):
        from whatsapp_langchain.shared.agente import update_agente

        pool, conn = _pool_update_capturando()
        await update_agente(pool, 1, "vendas", nome="Vendas SP")
        sql = str(conn.execute.call_args.args[0])
        assert "modelo" not in sql.split("WHERE")[0].replace("modelo_", "")
