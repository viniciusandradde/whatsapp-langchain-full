"""Etapa 0 do ADR-002 — helpers puros de `scripts/migrar_role_para_perfil.py`.

O que está sob teste é a parte que pode **mentir no relatório**: a simulação da
precedência do `perfil.get_user_permissions`. Se ela divergir da função real, o
dry-run mostra um delta errado e a decisão de aplicar é tomada em cima de número
falso — que é justamente o risco que o dry-run existe para eliminar.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent.parent
_spec = importlib.util.spec_from_file_location(
    "migrar_role_para_perfil", RAIZ / "scripts" / "migrar_role_para_perfil.py"
)
assert _spec and _spec.loader
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def _estado(**over) -> dict:
    base = {
        "catalogo": {"a.read", "a.write", "empresa.update"},
        "sys_por_nome": {(1, "Admin"): 10, (1, "Operador"): 11},
        "perfil_perms": {10: {"a.read", "a.write", "empresa.update"}, 11: {"a.read"}},
        "atribuicoes": {},
        "nomes_ocupados_custom": set(),
    }
    base.update(over)
    return base


def test_superadmin_recebe_catalogo_inteiro():
    """Espelha o passo 1 de get_user_permissions: superadmin ignora perfil."""
    e = _estado()
    perms = mod._perms_efetivas(e, 1, "u", "viewer", True, sys_existe=set())
    assert perms == e["catalogo"]


def test_perfil_explicito_tem_precedencia_sobre_role():
    """Passo 2: quem tem perfil NÃO cai no fallback do role, nem para somar."""
    e = _estado(atribuicoes={(1, "u"): {11}})
    perms = mod._perms_efetivas(
        e, 1, "u", "admin", False, sys_existe={(1, "Admin"), (1, "Operador")}
    )
    assert perms == {"a.read"}  # do perfil Operador, NÃO do role admin


def test_fallback_legado_usa_perfil_system_pelo_nome():
    e = _estado()
    perms = mod._perms_efetivas(e, 1, "u", "admin", False, sys_existe={(1, "Admin")})
    assert perms == {"a.read", "a.write", "empresa.update"}


def test_fallback_vazio_quando_perfil_system_nao_existe():
    """O buraco do seed: sem o perfil na empresa, o fallback devolve VAZIO.

    É por isso que criar o perfil já alarga o efetivo, antes de qualquer
    atribuição — o alerta que o dry-run precisa mostrar.
    """
    e = _estado(sys_por_nome={})
    perms = mod._perms_efetivas(e, 7, "u", "admin", False, sys_existe=set())
    assert perms == set()


def test_role_desconhecido_nao_concede_nada():
    e = _estado()
    perms = mod._perms_efetivas(
        e, 1, "u", "papel-inventado", False, sys_existe={(1, "Admin")}
    )
    assert perms == set()


def test_perfil_existente_vale_o_banco_nao_a_definicao_do_codigo():
    """Perfil system editado à mão diverge do código DE PROPÓSITO.

    O seed usa ON CONFLICT DO NOTHING, então não sobrescreve. Calcular o
    "depois" pela definição do código reportaria ganho/perda que não acontece —
    foi o bug que o primeiro dry-run expôs (23→17 com "+0").
    """
    e = _estado(perfil_perms={10: {"so.isso"}})
    assert mod._perms_perfil_alvo(e, 1, "Admin") == {"so.isso"}


def test_perfil_ausente_cai_na_definicao_do_codigo():
    e = _estado(sys_por_nome={})
    alvo = mod._perms_perfil_alvo(e, 9, "Admin")
    assert alvo == e["catalogo"]  # PERFIS_SYSTEM define Admin como "all"


def test_precedencia_bate_com_a_funcao_real():
    """Guarda contra deriva: a ordem documentada em get_user_permissions é
    superadmin → perfis explícitos → fallback por role. Se alguém reordenar lá,
    este teste não pega sozinho — mas o docstring de lá é a fonte, e aqui fica
    registrado que a simulação COPIA aquela ordem."""
    from whatsapp_langchain.shared.perfil import get_user_permissions

    doc = get_user_permissions.__doc__ or ""
    assert "superadmin" in doc.lower()
    assert "usuario_perfil" in doc
    assert "empresa_membro.role" in doc
