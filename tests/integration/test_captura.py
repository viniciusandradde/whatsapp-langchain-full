"""E2E do schema de captura (Task 3) e, adiante, dos endpoints (Task 5).

Estes testes exigem a stack/DB com a migração 119 aplicada (marcador
docker_demo). Validam a modelagem de staging: identidade por wa_jid, membro
só-LID com telefone NULL, dedup idempotente e cascata de deletes.

    DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \
    uv run pytest tests/integration/test_captura.py -v -s
"""

from __future__ import annotations

import uuid

import psycopg
import pytest

from .helpers import get_db_url

_RUN = uuid.uuid4().hex[:8]


@pytest.mark.docker_demo
class TestCapturaSchema:
    """Schema de staging: wa_jid como identidade, dedup e cascade."""

    @pytest.fixture(scope="class")
    def empresa(self):
        db = get_db_url()
        with psycopg.connect(db, autocommit=True) as conn:
            row = conn.execute(
                "INSERT INTO empresa (nome) VALUES (%s) RETURNING id",
                (f"capt-{_RUN}",),
            ).fetchone()
            assert row is not None
            eid = row[0]
        yield eid
        with psycopg.connect(db, autocommit=True) as conn:
            conn.execute("DELETE FROM empresa WHERE id = %s", (eid,))

    def test_01_dedup_por_wa_jid(self, empresa) -> None:
        jid = f"5511{_RUN[:7]}@s.whatsapp.net"
        with psycopg.connect(get_db_url(), autocommit=True) as conn:
            conn.execute(
                "INSERT INTO contato_capturado (empresa_id, wa_jid, telefone, push_name)"
                " VALUES (%s, %s, %s, %s)",
                (empresa, jid, "+5511" + _RUN[:7], "Fulano"),
            )
            # Segundo insert do mesmo (empresa, wa_jid) deve violar UNIQUE.
            with pytest.raises(psycopg.errors.UniqueViolation):
                conn.execute(
                    "INSERT INTO contato_capturado (empresa_id, wa_jid) VALUES (%s, %s)",
                    (empresa, jid),
                )

    def test_02_membro_so_lid_telefone_null(self, empresa) -> None:
        with psycopg.connect(get_db_url(), autocommit=True) as conn:
            grow = conn.execute(
                "INSERT INTO grupo (empresa_id, wa_group_id, nome)"
                " VALUES (%s, %s, %s) RETURNING id",
                (empresa, f"12036{_RUN}@g.us", "Grupo Teste"),
            ).fetchone()
            assert grow is not None
            grupo_id = grow[0]
            # Membro multi-device: só wa_lid, telefone NULL — deve ser aceito.
            conn.execute(
                "INSERT INTO grupo_membro (grupo_id, empresa_id, wa_jid, telefone)"
                " VALUES (%s, %s, %s, NULL)",
                (grupo_id, empresa, f"{_RUN}9988@lid"),
            )
            cnt = conn.execute(
                "SELECT COUNT(*) FROM grupo_membro"
                " WHERE grupo_id = %s AND telefone IS NULL",
                (grupo_id,),
            ).fetchone()
            assert cnt is not None and cnt[0] == 1

    def test_03_cascade_grupo_remove_membros(self, empresa) -> None:
        with psycopg.connect(get_db_url(), autocommit=True) as conn:
            grow = conn.execute(
                "INSERT INTO grupo (empresa_id, wa_group_id) VALUES (%s, %s) RETURNING id",
                (empresa, f"casc{_RUN}@g.us"),
            ).fetchone()
            assert grow is not None
            grupo_id = grow[0]
            conn.execute(
                "INSERT INTO grupo_membro (grupo_id, empresa_id, wa_jid)"
                " VALUES (%s, %s, %s)",
                (grupo_id, empresa, f"casc{_RUN}@s.whatsapp.net"),
            )
            conn.execute("DELETE FROM grupo WHERE id = %s", (grupo_id,))
            cnt = conn.execute(
                "SELECT COUNT(*) FROM grupo_membro WHERE grupo_id = %s",
                (grupo_id,),
            ).fetchone()
            assert cnt is not None and cnt[0] == 0  # cascateou

    def test_04_lote_auditoria_contadores(self, empresa) -> None:
        with psycopg.connect(get_db_url(), autocommit=True) as conn:
            row = conn.execute(
                "INSERT INTO captura_lote (empresa_id, origem, tipo, total_recebidos,"
                " total_novos, status) VALUES (%s, 'evolution_server', 'contatos',"
                " 10, 7, 'concluido') RETURNING id, total_novos",
                (empresa,),
            ).fetchone()
            assert row is not None
            assert row[1] == 7
