"""Etapa 1 do ADR-002 — o portão aceita as variantes de escopo.

Por que isto existe: o catálogo tem o código-base E as variantes
(`cliente.read`, `cliente.read.own`, `cliente.read.all`), mas os perfis
system de `PERFIS_SYSTEM` concedem **só as variantes**. Com igualdade
exata de string, toda rota gateada no código-base virava Admin-only na
prática — e o `hasPerm` do painel, que já aceita variantes, mostrava o
botão para quem tomaria 403.
"""

from __future__ import annotations

import pytest

from whatsapp_langchain.server.dependencies_rbac import tem_permissao
from whatsapp_langchain.shared.permissoes import PERFIS_SYSTEM


def _perms(nome: str) -> set[str]:
    for n, _desc, perms in PERFIS_SYSTEM:
        if n == nome:
            assert perms != "all", "Admin recebe o catálogo inteiro, não serve aqui"
            return set(perms)
    raise AssertionError(f"perfil {nome} não existe em PERFIS_SYSTEM")


def test_codigo_exato_passa():
    assert tem_permissao({"variavel.read"}, "variavel.read")


@pytest.mark.parametrize("variante", ["own", "all"])
def test_variante_de_escopo_satisfaz_o_codigo_base(variante: str):
    assert tem_permissao({f"cliente.read.{variante}"}, "cliente.read")


def test_nao_vale_o_caminho_inverso():
    """Ter o código-base NÃO satisfaz quem exige escopo explícito.

    Rota que pede `.all` está pedindo alcance de empresa inteira; o
    código-base não promete isso. Mesma regra do `hasPerm` do painel.
    """
    assert not tem_permissao({"atendimento.close"}, "atendimento.close.all")


def test_prefixo_parecido_nao_passa():
    """`cliente.read` não pode ser satisfeito por `cliente.readonly`."""
    assert not tem_permissao({"cliente.readonly"}, "cliente.read")


def test_set_vazio_nega():
    assert not tem_permissao(set(), "cliente.read")


@pytest.mark.parametrize(
    ("perfil", "codigo"),
    [
        ("Operador", "atendimento.write"),
        ("Operador", "atendimento.read"),
        ("Operador", "cliente.read"),
        ("Operador", "cliente.write"),
        ("Gestor", "atendimento.write"),
        ("Gestor", "cliente.write"),
        ("Leitura", "cliente.read"),
    ],
)
def test_perfis_system_passam_nas_rotas_gateadas_no_codigo_base(
    perfil: str, codigo: str
):
    """O caso que motivou a mudança.

    Nenhum destes perfis tem o código-base no conjunto — só as variantes.
    Se este teste voltar a falhar, as rotas de `atendimento.py` e
    `cliente.py` viraram Admin-only de novo.
    """
    perms = _perms(perfil)
    assert codigo not in perms, "premissa do teste: o perfil só tem a variante"
    assert tem_permissao(perms, codigo)


def test_leitura_nao_ganha_escrita_pela_regra_de_escopo():
    """A regra alarga escopo, não alarga ação."""
    assert not tem_permissao(_perms("Leitura"), "cliente.write")
    assert not tem_permissao(_perms("Leitura"), "atendimento.write")
