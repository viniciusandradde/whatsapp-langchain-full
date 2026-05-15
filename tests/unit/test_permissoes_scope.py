"""Unit tests do `effective_scope` (mig 083 record-level).

Cobre matriz: (perfil, perm, scope) → 'all' | 'own' | None
"""

from __future__ import annotations

from whatsapp_langchain.shared.permissoes import (
    PERFIS_SYSTEM,
    effective_scope,
)


# ---- effective_scope ----


def test_scope_all_quando_tem_perm_all():
    assert effective_scope({"cliente.read.all"}, "cliente.read") == "all"


def test_scope_own_quando_tem_perm_own():
    assert effective_scope({"cliente.read.own"}, "cliente.read") == "own"


def test_scope_all_quando_tem_legacy_sem_sufixo():
    """Legacy (sem .own/.all) é tratado como .all pra compat."""
    assert effective_scope({"cliente.read"}, "cliente.read") == "all"


def test_scope_none_quando_nao_tem_nenhuma():
    assert effective_scope(set(), "cliente.read") is None
    assert effective_scope({"agente.config"}, "cliente.read") is None


def test_scope_all_ganha_quando_tem_ambas_all_e_own():
    """Mais permissivo (.all) ganha sobre .own."""
    perms = {"cliente.read.all", "cliente.read.own"}
    assert effective_scope(perms, "cliente.read") == "all"


def test_scope_independente_por_modulo():
    """Ter cliente.read.all não dá scope em atendimento.read."""
    perms = {"cliente.read.all"}
    assert effective_scope(perms, "cliente.read") == "all"
    assert effective_scope(perms, "atendimento.read") is None


def test_scope_aplica_em_diferentes_acoes():
    """write é independente de read."""
    perms = {"cliente.read.own"}
    assert effective_scope(perms, "cliente.read") == "own"
    assert effective_scope(perms, "cliente.write") is None


# ---- Perfis system depois da mig 083 ----


def test_perfis_system_existem_4():
    nomes = {p[0] for p in PERFIS_SYSTEM}
    assert nomes == {"Admin", "Gestor", "Operador", "Leitura"}


def test_gestor_tem_all_em_cliente_atendimento():
    """Gestor (operação completa) deve ter scope .all."""
    gestor = next(p for p in PERFIS_SYSTEM if p[0] == "Gestor")
    perms = set(gestor[2]) if isinstance(gestor[2], list) else set()
    assert effective_scope(perms, "cliente.read") == "all"
    assert effective_scope(perms, "cliente.write") == "all"
    assert effective_scope(perms, "atendimento.read") == "all"
    assert effective_scope(perms, "atendimento.write") == "all"
    assert effective_scope(perms, "atendimento.transfer") == "all"
    assert effective_scope(perms, "atendimento.close") == "all"


def test_operador_tem_own_em_cliente_atendimento():
    """Operador (escopo restrito) deve ter scope .own — só seu(s) depto(s)."""
    op = next(p for p in PERFIS_SYSTEM if p[0] == "Operador")
    perms = set(op[2]) if isinstance(op[2], list) else set()
    assert effective_scope(perms, "cliente.read") == "own"
    assert effective_scope(perms, "cliente.write") == "own"
    assert effective_scope(perms, "atendimento.read") == "own"
    assert effective_scope(perms, "atendimento.write") == "own"


def test_leitura_tem_all_apenas_pra_read():
    """Leitura é read-only mas vê tudo da empresa."""
    leitura = next(p for p in PERFIS_SYSTEM if p[0] == "Leitura")
    perms = set(leitura[2]) if isinstance(leitura[2], list) else set()
    assert effective_scope(perms, "cliente.read") == "all"
    assert effective_scope(perms, "atendimento.read") == "all"
    # Não tem write
    assert effective_scope(perms, "cliente.write") is None
    assert effective_scope(perms, "atendimento.write") is None
