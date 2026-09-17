"""Etapa 3 do ADR-002 — `is_admin_of` deriva de permissão, não de `role` cru.

Testado com `is_superadmin`/`get_user_permissions` mockados (ambos já têm
cobertura própria — aqui o assunto é só a composição: bypass de superadmin
primeiro, depois checar `empresa.update` com a mesma regra de escopo do
`require_permission`).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from whatsapp_langchain.shared.empresa import PERM_ADMIN, is_admin_of


@pytest.mark.parametrize(
    ("superadmin", "perms", "esperado"),
    [
        # Superadmin passa mesmo com permissão vazia — bypass ANTES do resto,
        # igual antes (ordem preservada, achado que corrigiu o raio-X).
        (True, set(), True),
        # Tem o código-base exato.
        (False, {"empresa.update"}, True),
        # Perfil custom com `.all` — mesma regra de escopo do require_permission.
        (False, {"empresa.update.all"}, True),
        # Tem outras permissões, mas não `empresa.update`.
        (False, {"cliente.read", "atendimento.write.own"}, False),
        # Sem nenhum perfil resolvido (fallback caiu no buraco do seed).
        (False, set(), False),
    ],
)
async def test_is_admin_of_deriva_de_permissao(
    superadmin: bool, perms: set[str], esperado: bool
):
    with (
        patch(
            "whatsapp_langchain.shared.empresa.is_superadmin",
            new=AsyncMock(return_value=superadmin),
        ),
        patch(
            "whatsapp_langchain.shared.empresa.get_user_permissions",
            new=AsyncMock(return_value=perms),
        ) as mock_perms,
    ):
        out = await is_admin_of(pool=object(), empresa_id=1, user_id="u")

    assert out is esperado
    if superadmin:
        # Bypass antes de resolver perfil — não precisa nem chamar.
        mock_perms.assert_not_called()


async def test_is_admin_of_nao_confunde_write_com_update():
    """`empresa.update` é o único código que conta — não `empresa.write` nem
    variantes de outro módulo que por acaso apareçam no set."""
    with (
        patch(
            "whatsapp_langchain.shared.empresa.is_superadmin",
            new=AsyncMock(return_value=False),
        ),
        patch(
            "whatsapp_langchain.shared.empresa.get_user_permissions",
            new=AsyncMock(return_value={"empresa.member.role", "empresa.member.add"}),
        ),
    ):
        assert not await is_admin_of(pool=object(), empresa_id=1, user_id="u")


def test_perm_admin_e_empresa_update():
    """Trava o código contra o script de migração divergir do runtime —
    os dois têm que exigir a MESMA permissão (`scripts/migrar_role_para_perfil.py`
    usa `PERM_ADMIN` pra simular o critério de pronto da Etapa 0)."""
    assert PERM_ADMIN == "empresa.update"
