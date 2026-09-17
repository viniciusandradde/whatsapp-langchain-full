"""Etapa 2 do ADR-002 — as 2 permissões novas + a checagem por escopo/módulo.

O que quebra sem isto: um perfil que "parece" cobrir o módulo mas não tem o
código específico passa despercebido até alguém notar em produção que o
Operador está vendo o painel de aprovação HITL, ou que o Gestor não consegue
abrir o dashboard de NPS que ele sempre usou.
"""

from __future__ import annotations

from whatsapp_langchain.shared.permissoes import CATALOGO, PERFIS_SYSTEM


def _perfil(nome: str) -> list[str] | str:
    for n, _desc, perms in PERFIS_SYSTEM:
        if n == nome:
            return perms
    raise AssertionError(f"perfil {nome} não existe em PERFIS_SYSTEM")


def test_catalogo_tem_as_duas_permissoes_novas():
    codigos = {c for c, _d, _m in CATALOGO}
    assert "atendimento.hitl.approve" in codigos
    assert "relatorio.nps.read" in codigos


def test_hitl_approve_e_supervisao_nao_operacao_de_linha():
    """Gestor e Admin aprovam; Operador não — HITL é revisão do que o
    agente tentou fazer, não atendimento comum."""
    assert "atendimento.hitl.approve" in _perfil("Gestor")
    assert "atendimento.hitl.approve" not in _perfil("Operador")
    assert "atendimento.hitl.approve" not in _perfil("Leitura")


def test_relatorio_nps_e_leitura_de_acompanhamento():
    """Leitura tem (é o propósito do perfil); Operador não (linha de
    frente não usa dashboard de qualidade)."""
    assert "relatorio.nps.read" in _perfil("Gestor")
    assert "relatorio.nps.read" in _perfil("Leitura")
    assert "relatorio.nps.read" not in _perfil("Operador")


def test_modulo_relatorio_tem_descricao_de_leitura():
    """Guarda contra a permissão nascer sem `modulo` preenchido — é o que
    a UI usa pra agrupar a tela de perfil em árvore (Etapa 5)."""
    achou = [(c, d, m) for c, d, m in CATALOGO if c == "relatorio.nps.read"]
    assert len(achou) == 1
    _cod, desc, modulo = achou[0]
    assert modulo == "relatorio"
    assert desc
