"""Script standalone de migração do banco de dados.

Lê arquivos SQL de db/migrations/ e aplica os pendentes em ordem.
Controla quais migrações já foram aplicadas via tabela _migrations.

Uso:
    python db/migrate.py

Requer a variável DATABASE_URL configurada (via .env ou env var).
"""

import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

load_dotenv()

# Diretório de migrações relativo a este script
MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def run_migrations(database_url: str) -> None:
    """Aplica migrações SQL pendentes ao banco de dados.

    Cria a tabela _migrations se não existir, depois aplica cada arquivo
    SQL que ainda não foi registrado, em ordem alfabética.

    Args:
        database_url: Connection string do PostgreSQL.
    """
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            # Garante que a tabela de controle existe
            cur.execute("""
                CREATE TABLE IF NOT EXISTS _migrations (
                    id          SERIAL PRIMARY KEY,
                    name        TEXT NOT NULL UNIQUE,
                    applied_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            conn.commit()

            # Busca migrações já aplicadas
            cur.execute("SELECT name FROM _migrations ORDER BY name")
            applied = {row[0] for row in cur.fetchall()}

            # Lê e aplica migrações pendentes em ordem
            sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))

            for sql_file in sql_files:
                if sql_file.name in applied:
                    print(f"  [ok] {sql_file.name} (já aplicada)")
                    continue

                print(f"  [>>] Aplicando {sql_file.name}...")
                sql = sql_file.read_text(encoding="utf-8")
                cur.execute(sql)

                # Registra a migração como aplicada
                cur.execute(
                    "INSERT INTO _migrations (name) VALUES (%s)",
                    (sql_file.name,),
                )
                conn.commit()
                print(f"  [ok] {sql_file.name} aplicada com sucesso")


def main() -> None:
    """Entry point do script de migração."""
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("Erro: DATABASE_URL não configurada.")
        print("Configure via .env ou variável de ambiente.")
        sys.exit(1)

    print("Conectando ao banco de dados...")
    try:
        run_migrations(database_url)
        print("Migrações concluídas.")
    except psycopg.Error as e:
        print(f"Erro ao aplicar migrações: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
