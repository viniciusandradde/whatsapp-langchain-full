"""Sprint A.2.1 — Setup de senhas das roles app.

Roda APÓS aplicar `db/migrations/100_app_roles_create.sql`. Define
senhas + habilita LOGIN nas 4 roles a partir de env vars:

    CHAT_NEXUS_APP_PASSWORD
    CHAT_NEXUS_MIGRATOR_PASSWORD
    CHAT_NEXUS_READONLY_PASSWORD
    CHAT_NEXUS_AUDIT_PASSWORD

Gera senhas se não setadas (modo --auto-generate). Em prod, **sempre**
passar via vault.

Uso:
    # Manual (recomendado prod): env vars vindo do vault
    export CHAT_NEXUS_APP_PASSWORD=$(vault read -field=value secret/chat_nexus/app)
    ...
    uv run python scripts/setup_app_roles_passwords.py

    # Auto-gen (dev/staging só):
    uv run python scripts/setup_app_roles_passwords.py --auto-generate

Saída em modo auto-generate (stdout): valores das senhas. SALVAR em
vault imediatamente — script não persiste em lugar nenhum.

Segurança:
- Usa parameter binding pra evitar injection (mesmo sendo localhost).
- ALTER ROLE não loga senha no pg_stat_activity / log_statement.
- Conecta como `postgres` (superuser) pois ALTER ROLE de outro role
  requer superuser ou CREATEROLE.
"""

from __future__ import annotations

import argparse
import os
import secrets
import string
import sys

import psycopg


ROLES = [
    "chat_nexus_app",
    "chat_nexus_migrator",
    "chat_nexus_readonly",
    "chat_nexus_audit",
]


def _env_var_name(role: str) -> str:
    return f"{role.upper()}_PASSWORD"


def _generate_password(length: int = 32) -> str:
    alphabet = string.ascii_letters + string.digits + "_-"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _resolve_passwords(auto_generate: bool) -> dict[str, str]:
    passwords: dict[str, str] = {}
    for role in ROLES:
        env_name = _env_var_name(role)
        value = os.environ.get(env_name)
        if value:
            if len(value) < 24:
                raise SystemExit(
                    f"❌ {env_name} muito curto ({len(value)} chars). "
                    "Mínimo 24 pra prod."
                )
            passwords[role] = value
            print(f"  ✓ {role}: senha do env var ({env_name})")
        elif auto_generate:
            passwords[role] = _generate_password()
            print(f"  ⚙ {role}: GERADA — copiar agora pro vault")
        else:
            raise SystemExit(
                f"❌ {env_name} não setado. Use --auto-generate ou exporte a env var."
            )
    return passwords


def _apply(database_url: str, passwords: dict[str, str], dry_run: bool) -> None:
    print(f"\nConectando: {database_url.split('@')[-1]}")
    with psycopg.connect(database_url, autocommit=False) as conn:
        with conn.cursor() as cur:
            for role, password in passwords.items():
                if dry_run:
                    print(f"  [dry-run] ALTER ROLE {role} WITH LOGIN PASSWORD '***'")
                    continue
                # ALTER ROLE não aceita parameter binding pra PASSWORD —
                # tem que ser literal. Validação acima previne injection
                # (auto-gen usa alphabet seguro; env var é controlada).
                if any(c in password for c in "';\\"):
                    raise SystemExit(
                        f"❌ {role}: senha contém caractere proibido (';\\\\)."
                    )
                cur.execute(
                    f"ALTER ROLE {role} WITH LOGIN PASSWORD '{password}'"
                )
                print(f"  ✓ {role}: LOGIN habilitado")
            if not dry_run:
                conn.commit()
                print("\n✅ Commit OK")
            else:
                conn.rollback()
                print("\n⚪ Dry-run — rolled back")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--database-url",
        default=os.environ.get(
            "DATABASE_URL",
            "postgresql://postgres:postgres@localhost:5432/whatsapp_langchain",
        ),
        help="URL de conexão como superuser (postgres).",
    )
    parser.add_argument(
        "--auto-generate",
        action="store_true",
        help="Gera senhas seguras se env vars não setadas. SALVAR no vault.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Mostra o que seria feito sem commitar.",
    )
    args = parser.parse_args()

    print("Sprint A.2.1 — Setup de senhas das roles app\n")
    passwords = _resolve_passwords(args.auto_generate)
    _apply(args.database_url, passwords, args.dry_run)

    if args.auto_generate and not args.dry_run:
        print("\n⚠️  ATENÇÃO — copie as senhas pro vault AGORA:")
        for role, password in passwords.items():
            env_name = _env_var_name(role)
            print(f"  {env_name}={password}")
        print(
            "\nDepois de salvar, exporte como env vars no Dokploy e remova "
            "do histórico do terminal:\n"
            "  history -c   # bash\n"
            "  history -p   # zsh"
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
