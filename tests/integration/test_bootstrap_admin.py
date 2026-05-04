"""Smoke test do bootstrap admin (frontend/src/lib/bootstrap-admin-core.ts).

Bootstrap roda no startup da aplicação Next.js: cria o user definido por
ADMIN_EMAIL/ADMIN_PASSWORD em auth."user" + auth.account, popula
empresa_membro (vínculo à empresa default) e marca is_superadmin=true.

Sem isso, novo deploy fica com admin sem acesso a /api/* (403 — get_empresa_context).

Este teste valida o ESTADO esperado do DB pós-bootstrap. Se algum
INSERT for esquecido no futuro (regressão), o teste falha e protege
contra deploys quebrados.

Pré-requisito: stack Docker rodando (`make up`) com bootstrap já executado
(acessar `/login` no frontend uma vez basta).
"""

from __future__ import annotations

import os

import psycopg
import pytest

from tests.integration.helpers import get_db_url

pytestmark = pytest.mark.docker_demo


def _admin_email() -> str:
    """Email do admin bootstrapado — bate com env ADMIN_EMAIL do frontend."""
    return os.getenv("ADMIN_EMAIL", "admin@vsanexus.com").strip()


def test_bootstrap_admin_user_exists():
    """Admin user precisa estar criado em auth.user com flags corretas."""
    with psycopg.connect(get_db_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, "emailVerified", is_superadmin
                FROM auth."user"
                WHERE email = %s
                """,
                (_admin_email(),),
            )
            row = cur.fetchone()

    assert row is not None, (
        f"Admin user {_admin_email()!r} não existe em auth.user — "
        "bootstrap não rodou (acesse /login no frontend) ou tabela foi truncada."
    )

    user_id, email_verified, is_superadmin = row
    assert email_verified is True, (
        "emailVerified deve ser TRUE pós-bootstrap pra desbloquear ações "
        "que exigem email confirmado (inclui Better Auth defaults)."
    )
    assert is_superadmin is True, (
        "is_superadmin deve ser TRUE pra admin ter acesso cross-tenant. "
        "Sem isso, get_empresa_context rejeita a sessão em empresas onde "
        "ele não é membro direto."
    )


def test_bootstrap_admin_membership():
    """Admin precisa ser membro admin da empresa default (id=1)."""
    with psycopg.connect(get_db_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT em.empresa_id, em.role, em.is_default
                FROM empresa_membro em
                JOIN auth."user" u ON u.id = em.user_id
                WHERE u.email = %s
                """,
                (_admin_email(),),
            )
            rows = cur.fetchall()

    assert rows, (
        f"Admin {_admin_email()!r} não tem nenhuma membership em empresa_membro — "
        "bootstrap não vinculou à empresa default. Resultado: 403 em todos os "
        "endpoints /api/*. Confira frontend/src/lib/bootstrap-admin-core.ts."
    )

    empresa_default = next((r for r in rows if r[0] == 1), None)
    assert empresa_default is not None, (
        f"Admin precisa ser membro da empresa id=1 (VSA Tech). Memberships: {rows}"
    )

    _, role, is_default = empresa_default
    assert role == "admin", (
        f"Role na empresa default deve ser 'admin', encontrado: {role!r}"
    )
    assert is_default is True, (
        "is_default deve ser TRUE pra empresa selecionada por padrão na sessão."
    )


def test_bootstrap_empresa_default_exists():
    """Empresa default (id=1, slug=vsa-tech) precisa existir."""
    with psycopg.connect(get_db_url()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, nome, slug, status FROM empresa WHERE id = 1"
            )
            row = cur.fetchone()

    assert row is not None, (
        "Empresa id=1 não existe — migration 007 não rodou ou foi revertida."
    )
    _, _, slug, status = row
    assert slug == "vsa-tech"
    assert status == "active"
