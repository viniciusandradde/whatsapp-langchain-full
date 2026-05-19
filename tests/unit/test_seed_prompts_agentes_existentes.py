"""Testes do catálogo PROMPTS_POR_SLUG (script seed_prompts_agentes_existentes).

Valida os 8 prompts dos agentes pós-paridade ZigChat (IDs 1-8) que vivem
em rows criadas por workflow import e ficavam sem prompt_override.
"""

import importlib.util
from pathlib import Path

import pytest

_SCRIPT_PATH = (
    Path(__file__).parent.parent.parent
    / "scripts"
    / "seed_prompts_agentes_existentes.py"
)
spec = importlib.util.spec_from_file_location(
    "seed_prompts_agentes_existentes", _SCRIPT_PATH
)
assert spec and spec.loader
_seed_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_seed_module)

PROMPTS_POR_SLUG: dict[str, dict] = _seed_module.PROMPTS_POR_SLUG


EXPECTED_SLUGS = {
    "atendimento",
    "atendimento-cliente",
    "agendamentos",
    "exames",
    "orcamento",
    "ouvidoria",
    "tesouraria",
    "rh-recrutamento-selecao",
    "agente-entrevista-ti",
}


def test_catalogo_tem_9_slugs() -> None:
    assert set(PROMPTS_POR_SLUG.keys()) == EXPECTED_SLUGS


@pytest.mark.parametrize("slug", sorted(EXPECTED_SLUGS))
def test_campos_obrigatorios(slug: str) -> None:
    cfg = PROMPTS_POR_SLUG[slug]
    required = {
        "estilo_resposta",
        "temperatura_override",
        "max_tokens",
        "tools_enabled",
        "prompt",
    }
    assert required.issubset(cfg.keys()), f"campos faltando em {slug}"


@pytest.mark.parametrize("slug", sorted(EXPECTED_SLUGS))
def test_prompt_substantivo(slug: str) -> None:
    """Prompt útil = >800 chars com seções típicas."""
    p = PROMPTS_POR_SLUG[slug]["prompt"]
    assert len(p) > 800, f"prompt curto em {slug}: {len(p)}"
    assert "## Seu papel" in p, f"sem '## Seu papel' em {slug}"
    assert "## Regras importantes" in p, f"sem '## Regras importantes' em {slug}"
    assert "## Tom" in p, f"sem '## Tom' em {slug}"
    assert "## NÃO faça" in p, f"sem '## NÃO faça' em {slug}"


@pytest.mark.parametrize("slug", sorted(EXPECTED_SLUGS))
def test_estilo_resposta_valido(slug: str) -> None:
    assert PROMPTS_POR_SLUG[slug]["estilo_resposta"] in {
        "preciso",
        "equilibrado",
        "criativo",
        "muito_criativo",
    }


@pytest.mark.parametrize("slug", sorted(EXPECTED_SLUGS))
def test_temperatura_em_range(slug: str) -> None:
    t = PROMPTS_POR_SLUG[slug]["temperatura_override"]
    assert 0.0 <= t <= 2.0, f"temperatura {t} fora de range em {slug}"


@pytest.mark.parametrize("slug", sorted(EXPECTED_SLUGS))
def test_tool_transferir_humano_obrigatoria(slug: str) -> None:
    """Compliance: TODOS os agentes precisam poder escalar pra humano."""
    tools = PROMPTS_POR_SLUG[slug]["tools_enabled"]
    assert "transferir_para_humano" in tools, (
        f"agente {slug} não tem transferir_para_humano"
    )


# ---------- regras específicas por agente ----------


def test_atendimento_eh_triagem_so() -> None:
    """Atendimento genérico NÃO resolve — só triagem e transfere."""
    p = PROMPTS_POR_SLUG["atendimento"]["prompt"]
    assert "NÃO TENTA RESOLVER" in p
    assert "transferir_para_departamento" in PROMPTS_POR_SLUG[
        "atendimento"
    ]["tools_enabled"]


def test_agendamentos_inclui_urgencias_clinicas() -> None:
    """Casos especiais (gestante, urgência, criança<3) sempre transferem."""
    p = PROMPTS_POR_SLUG["agendamentos"]["prompt"]
    assert "gestante" in p.lower()
    assert "urgência" in p.lower()


def test_ouvidoria_lgpd_explicita() -> None:
    p = PROMPTS_POR_SLUG["ouvidoria"]["prompt"]
    assert "LGPD" in p
    assert "registrar_ocorrencia" in PROMPTS_POR_SLUG["ouvidoria"]["tools_enabled"]


def test_orcamento_nao_negocia() -> None:
    p = PROMPTS_POR_SLUG["orcamento"]["prompt"]
    assert "Não negocia" in p or "NUNCA invente preço" in p


def test_tesouraria_nunca_pede_senha() -> None:
    """Antifraude: jamais pede CVV/senha."""
    p = PROMPTS_POR_SLUG["tesouraria"]["prompt"]
    assert "NUNCA pede senha" in p or "NUNCA pede senha, CVV" in p


def test_tesouraria_nao_cancela_boleto() -> None:
    p = PROMPTS_POR_SLUG["tesouraria"]["prompt"]
    assert "NUNCA cancela" in p or "Não cancela boleto" in p


def test_rh_lgpd_dados_so_pra_selecao() -> None:
    p = PROMPTS_POR_SLUG["rh-recrutamento-selecao"]["prompt"]
    assert "LGPD" in p
    assert "listar_vagas_abertas" in PROMPTS_POR_SLUG[
        "rh-recrutamento-selecao"
    ]["tools_enabled"]


def test_exames_nao_interpreta_resultado() -> None:
    p = PROMPTS_POR_SLUG["exames"]["prompt"]
    assert "NUNCA invente preparo" in p
    assert "search_knowledge_base" in PROMPTS_POR_SLUG["exames"]["tools_enabled"]


# ---------- proibições universais ----------


@pytest.mark.parametrize("slug", sorted(EXPECTED_SLUGS))
def test_jamais_promete_diagnostico_em_clinicos(slug: str) -> None:
    """Agentes que tocam contexto clínico explicitam: sem diagnóstico."""
    if slug not in ("agendamentos", "exames", "atendimento", "atendimento-cliente"):
        return  # outros não cabe
    p = PROMPTS_POR_SLUG[slug]["prompt"].lower()
    # Cada um pode usar variações: "diagnóstico", "diagnostico", "interpreta"
    # Aceitamos qualquer um
    assert (
        "diagnóstico" in p
        or "diagnostico" in p
        or "interpreta sintoma" in p
        or "info clínica" in p
    ), f"{slug} deve proibir diagnóstico explicitamente"
