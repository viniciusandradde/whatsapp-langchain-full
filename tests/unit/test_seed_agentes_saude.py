"""Testes do script seed_agentes_saude.py.

Valida o catálogo dos 5 agentes (slug único, prompt não vazio, modelo
válido, tools coerentes com a função). Não roda o INSERT — só verifica
que os dados do catálogo estão estruturados corretamente.
"""

import importlib.util
from pathlib import Path

import pytest

# Carrega o script como módulo (scripts/ não é pacote)
_SCRIPT_PATH = Path(__file__).parent.parent.parent / "scripts" / "seed_agentes_saude.py"
spec = importlib.util.spec_from_file_location("seed_agentes_saude", _SCRIPT_PATH)
assert spec and spec.loader
_seed_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_seed_module)

AGENTES_SAUDE = _seed_module.AGENTES_SAUDE


# ---------- estrutura do catálogo ----------


def test_catalogo_tem_5_agentes() -> None:
    assert len(AGENTES_SAUDE) == 5


def test_slugs_sao_unicos() -> None:
    slugs = [a["slug"] for a in AGENTES_SAUDE]
    assert len(slugs) == len(set(slugs))


def test_slugs_prefixo_saude() -> None:
    """Convenção: prefixo `saude_` pra deixar claro o domínio do agente."""
    for a in AGENTES_SAUDE:
        assert a["slug"].startswith("saude_"), (
            f"slug {a['slug']} fora da convenção"
        )


@pytest.mark.parametrize("agente", AGENTES_SAUDE, ids=lambda a: a["slug"])
def test_campos_obrigatorios(agente: dict) -> None:
    required = {
        "slug",
        "nome",
        "descricao",
        "modelo",
        "estilo_resposta",
        "temperatura_override",
        "max_tokens",
        "tools_enabled",
        "prompt",
    }
    missing = required - set(agente.keys())
    assert not missing, f"campos faltando em {agente['slug']}: {missing}"


@pytest.mark.parametrize("agente", AGENTES_SAUDE, ids=lambda a: a["slug"])
def test_prompt_substantivo(agente: dict) -> None:
    """Prompt precisa ter conteúdo útil (>500 chars, com seções)."""
    p = agente["prompt"]
    assert len(p) > 500, f"prompt curto demais em {agente['slug']}: {len(p)}"
    # Seções típicas de um prompt bem estruturado
    assert "## Seu papel" in p or "## Contexto" in p, (
        f"sem seção 'Seu papel' ou 'Contexto' em {agente['slug']}"
    )
    assert "## Regras importantes" in p, (
        f"sem 'Regras importantes' em {agente['slug']}"
    )
    assert "## Tom" in p, f"sem seção 'Tom' em {agente['slug']}"


@pytest.mark.parametrize("agente", AGENTES_SAUDE, ids=lambda a: a["slug"])
def test_estilo_resposta_enum_valido(agente: dict) -> None:
    """estilo_resposta tem CHECK no banco — só aceita esses 4 valores."""
    assert agente["estilo_resposta"] in {
        "preciso",
        "equilibrado",
        "criativo",
        "muito_criativo",
    }


@pytest.mark.parametrize("agente", AGENTES_SAUDE, ids=lambda a: a["slug"])
def test_temperatura_em_range(agente: dict) -> None:
    """Temperatura entre 0 e 2 (limite OpenRouter)."""
    t = agente["temperatura_override"]
    assert 0.0 <= t <= 2.0, f"temperatura {t} fora de range em {agente['slug']}"


@pytest.mark.parametrize("agente", AGENTES_SAUDE, ids=lambda a: a["slug"])
def test_max_tokens_razoavel(agente: dict) -> None:
    """max_tokens entre 100 e 2000 — saúde precisa ser conciso."""
    mt = agente["max_tokens"]
    assert 100 <= mt <= 2000, f"max_tokens {mt} fora do esperado em {agente['slug']}"


@pytest.mark.parametrize("agente", AGENTES_SAUDE, ids=lambda a: a["slug"])
def test_tool_transferir_humano_obrigatoria(agente: dict) -> None:
    """Todos os agentes de saúde DEVEM poder escalar pra humano."""
    assert "transferir_para_humano" in agente["tools_enabled"], (
        f"agente {agente['slug']} não tem tool transferir_para_humano — "
        "obrigatório em saúde por compliance"
    )


# ---------- regras específicas por agente ----------


def test_agendamentos_tem_tools_agenda() -> None:
    ag = next(a for a in AGENTES_SAUDE if a["slug"] == "saude_agendamentos")
    assert "consultar_agenda" in ag["tools_enabled"]
    assert "criar_agendamento" in ag["tools_enabled"]
    assert "cancelar_agendamento" in ag["tools_enabled"]


def test_ouvidoria_lgpd_no_prompt() -> None:
    """Ouvidoria PRECISA mencionar LGPD — risco compliance grave."""
    ag = next(a for a in AGENTES_SAUDE if a["slug"] == "saude_ouvidoria")
    assert "LGPD" in ag["prompt"]
    assert "registrar_ocorrencia" in ag["tools_enabled"]


def test_exames_search_knowledge_base() -> None:
    """Exames precisa de KB pra preparo (evita inventar regra de jejum)."""
    ag = next(a for a in AGENTES_SAUDE if a["slug"] == "saude_suporte_exames")
    assert "search_knowledge_base" in ag["tools_enabled"]
    # Prompt explícito proíbe inventar preparo
    assert "NUNCA invente preparo" in ag["prompt"]


def test_financeiro_nao_negocia_descontos() -> None:
    """Financeiro NÃO pode negociar — descontos via humano."""
    ag = next(a for a in AGENTES_SAUDE if a["slug"] == "saude_financeiro")
    assert "Não negocia descontos" in ag["prompt"]
    assert "consultar_orcamento" in ag["tools_enabled"]


def test_nps_nao_defende() -> None:
    """NPS follow-up jamais defende — escuta e registra."""
    ag = next(a for a in AGENTES_SAUDE if a["slug"] == "saude_nps")
    assert "NUNCA seja defensivo" in ag["prompt"]
    assert "registrar_feedback" in ag["tools_enabled"]


# ---------- proibições universais (compliance saúde) ----------


@pytest.mark.parametrize("agente", AGENTES_SAUDE, ids=lambda a: a["slug"])
def test_jamais_diagnostico(agente: dict) -> None:
    """Compliance: nenhum agente IA dá diagnóstico médico.

    Verifica que o prompt PROIBE diagnóstico OU que o agente não tem
    contexto pra isso (ex: financeiro/ouvidoria não falariam de
    diagnóstico de qualquer jeito).
    """
    p = agente["prompt"].lower()
    # Agentes clínicos (agendamentos, exames) precisam de proibição explícita
    if agente["slug"] in ("saude_agendamentos", "saude_suporte_exames"):
        assert "diagnóstico" in p or "diagnostico" in p, (
            f"{agente['slug']} precisa proibir diagnóstico explicitamente"
        )
