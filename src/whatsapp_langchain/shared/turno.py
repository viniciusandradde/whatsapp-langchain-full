"""Sprint U (Fase 2) — turnos / jornada de trabalho.

CRUD de turnos (cabeçalho + janelas de horário por dia) e atribuição
usuário↔turno. Paridade ZigChat `Turno`/`TurnoHorario`.

Tabelas (mig 112): `turno`, `turno_horario`, `usuario_turno`. As de
empresa_id têm RLS; o contexto de empresa vem do middleware da request
(`install_rls_context`) — segue o padrão de `shared/departamento.py`
(pool.connection() + empresa_id no WHERE).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.horario import _resolve_timezone

logger = structlog.get_logger()


@dataclass
class TurnoInfo:
    id: int
    empresa_id: int
    nome: str
    ativo: bool
    horarios: list[dict] = field(
        default_factory=list
    )  # [{dia_semana, hora_inicio, hora_fim}]
    users_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "empresa_id": self.empresa_id,
            "nome": self.nome,
            "ativo": self.ativo,
            "horarios": self.horarios,
            "users_count": self.users_count,
        }


def _norm_horarios(horarios: list[dict] | None) -> list[tuple[int, str, str]]:
    """Valida + normaliza janelas: (dia_semana 0-6, hora_inicio, hora_fim)."""
    out: list[tuple[int, str, str]] = []
    for h in horarios or []:
        dia = int(h["dia_semana"])
        if not 0 <= dia <= 6:
            raise ValueError(f"dia_semana inválido: {dia}")
        ini = str(h["hora_inicio"])
        fim = str(h["hora_fim"])
        if fim <= ini:
            raise ValueError(
                f"hora_fim ({fim}) deve ser maior que hora_inicio ({ini})."
            )
        out.append((dia, ini, fim))
    return out


async def _load_horarios(conn: Any, turno_id: int) -> list[dict]:
    cur = await conn.execute(
        "SELECT dia_semana, to_char(hora_inicio, 'HH24:MI') , "
        "to_char(hora_fim, 'HH24:MI') FROM turno_horario "
        "WHERE turno_id = %s ORDER BY dia_semana, hora_inicio",
        (turno_id,),
    )
    return [
        {"dia_semana": r[0], "hora_inicio": r[1], "hora_fim": r[2]}
        for r in await cur.fetchall()
    ]


async def list_turnos(pool: AsyncConnectionPool, empresa_id: int) -> list[TurnoInfo]:
    """Lista turnos da empresa com horários + contagem de usuários."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT t.id, t.empresa_id, t.nome, t.ativo,
                   (SELECT COUNT(*) FROM usuario_turno ut
                     WHERE ut.turno_id = t.id) AS users_count
              FROM turno t
             WHERE t.empresa_id = %s
             ORDER BY t.nome ASC
            """,
            (empresa_id,),
        )
        rows = await cur.fetchall()
        turnos = [
            TurnoInfo(
                id=r[0],
                empresa_id=r[1],
                nome=r[2],
                ativo=bool(r[3]),
                users_count=int(r[4]),
            )
            for r in rows
        ]
        for t in turnos:
            t.horarios = await _load_horarios(conn, t.id)
    return turnos


async def get_turno(
    pool: AsyncConnectionPool, empresa_id: int, turno_id: int
) -> TurnoInfo | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT id, empresa_id, nome, ativo FROM turno "
            "WHERE id = %s AND empresa_id = %s",
            (turno_id, empresa_id),
        )
        row = await cur.fetchone()
        if row is None:
            return None
        t = TurnoInfo(id=row[0], empresa_id=row[1], nome=row[2], ativo=bool(row[3]))
        t.horarios = await _load_horarios(conn, t.id)
    return t


async def create_turno(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    nome: str,
    ativo: bool = True,
    horarios: list[dict] | None = None,
) -> TurnoInfo:
    janelas = _norm_horarios(horarios)
    async with pool.connection() as conn:
        async with conn.transaction():
            cur = await conn.execute(
                "INSERT INTO turno (empresa_id, nome, ativo) "
                "VALUES (%s, %s, %s) RETURNING id",
                (empresa_id, nome, ativo),
            )
            row = await cur.fetchone()
            assert row is not None
            turno_id = int(row[0])
            for dia, ini, fim in janelas:
                await conn.execute(
                    "INSERT INTO turno_horario "
                    "(turno_id, dia_semana, hora_inicio, hora_fim) "
                    "VALUES (%s, %s, %s, %s)",
                    (turno_id, dia, ini, fim),
                )
    logger.info("turno_criado", empresa_id=empresa_id, turno_id=turno_id)
    result = await get_turno(pool, empresa_id, turno_id)
    assert result is not None
    return result


async def update_turno(
    pool: AsyncConnectionPool,
    empresa_id: int,
    turno_id: int,
    *,
    nome: str | None = None,
    ativo: bool | None = None,
    horarios: list[dict] | None = None,
) -> TurnoInfo | None:
    janelas = _norm_horarios(horarios) if horarios is not None else None
    async with pool.connection() as conn:
        async with conn.transaction():
            cur = await conn.execute(
                "SELECT 1 FROM turno WHERE id = %s AND empresa_id = %s",
                (turno_id, empresa_id),
            )
            if await cur.fetchone() is None:
                return None
            fields, params = [], []
            if nome is not None:
                fields.append("nome = %s")
                params.append(nome)
            if ativo is not None:
                fields.append("ativo = %s")
                params.append(ativo)
            if fields:
                fields.append("updated_at = NOW()")
                params.extend([turno_id, empresa_id])
                await conn.execute(
                    f"UPDATE turno SET {', '.join(fields)} "
                    "WHERE id = %s AND empresa_id = %s",
                    tuple(params),
                )
            if janelas is not None:
                await conn.execute(
                    "DELETE FROM turno_horario WHERE turno_id = %s", (turno_id,)
                )
                for dia, ini, fim in janelas:
                    await conn.execute(
                        "INSERT INTO turno_horario "
                        "(turno_id, dia_semana, hora_inicio, hora_fim) "
                        "VALUES (%s, %s, %s, %s)",
                        (turno_id, dia, ini, fim),
                    )
    return await get_turno(pool, empresa_id, turno_id)


async def delete_turno(
    pool: AsyncConnectionPool, empresa_id: int, turno_id: int
) -> bool:
    async with pool.connection() as conn:
        cur = await conn.execute(
            "DELETE FROM turno WHERE id = %s AND empresa_id = %s",
            (turno_id, empresa_id),
        )
        await conn.commit()
    return (cur.rowcount or 0) > 0


async def list_users_in_turno(
    pool: AsyncConnectionPool, empresa_id: int, turno_id: int
) -> list[dict]:
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT u.id, u.name, u.email
              FROM usuario_turno ut
              JOIN auth."user" u ON u.id = ut.user_id
             WHERE ut.turno_id = %s AND ut.empresa_id = %s
             ORDER BY u.name
            """,
            (turno_id, empresa_id),
        )
        return [{"id": r[0], "nome": r[1], "email": r[2]} for r in await cur.fetchall()]


async def set_users_in_turno(
    pool: AsyncConnectionPool,
    empresa_id: int,
    turno_id: int,
    user_ids: list[str],
) -> bool:
    """Sync (replace) dos usuários atribuídos a um turno."""
    async with pool.connection() as conn:
        async with conn.transaction():
            cur = await conn.execute(
                "SELECT 1 FROM turno WHERE id = %s AND empresa_id = %s",
                (turno_id, empresa_id),
            )
            if await cur.fetchone() is None:
                return False
            await conn.execute(
                "DELETE FROM usuario_turno WHERE turno_id = %s AND empresa_id = %s",
                (turno_id, empresa_id),
            )
            for uid in user_ids:
                await conn.execute(
                    "INSERT INTO usuario_turno (user_id, turno_id, empresa_id) "
                    "VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                    (uid, turno_id, empresa_id),
                )
    return True


# ---------------------------------------------------------------------
# Gate de distribuição — atendente só recebe auto-atribuição se estiver
# dentro de um turno ativo AGORA. Semântica: **sem turno ativo atribuído =
# irrestrito** (compat retroativa — quem não usa turno nunca é bloqueado).
# ---------------------------------------------------------------------


async def turno_now(
    pool: AsyncConnectionPool, empresa_id: int, now: datetime | None = None
) -> tuple[int, str]:
    """`(dia_semana 0=Dom..6=Sáb, 'HH:MM:SS')` no fuso da empresa.

    Reusa a resolução de timezone de `horario.py` (default America/Sao_Paulo)
    e a mesma convenção de dia_semana do `is_business_hours`.
    """
    tzname = await _resolve_timezone(pool, empresa_id)
    tz = ZoneInfo(tzname)
    if now is None:
        now = datetime.now(tz)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=tz)
    local = now.astimezone(tz)
    dia_semana = (local.weekday() + 1) % 7  # Python 0=Seg → 0=Dom
    return dia_semana, local.strftime("%H:%M:%S")


def turno_gate_sql(alias: str = "u") -> str:
    """Fragmento SQL pra WHERE: `{alias}` está elegível p/ distribuição agora.

    Verdadeiro quando o usuário **não tem turno ativo atribuído** (irrestrito)
    OU está **dentro de alguma janela** de um turno ativo. `alias` é o alias da
    tabela `auth."user"` na query do caller.

    Ordem dos params: `(empresa_id, empresa_id, dia_semana, hora, hora)`.
    `alias` vem de lista hardcoded do caller — não é input (sem injeção).
    """
    return f"""(
        NOT EXISTS (
            SELECT 1 FROM usuario_turno utg
              JOIN turno tg ON tg.id = utg.turno_id
             WHERE utg.user_id = {alias}.id AND utg.empresa_id = %s AND tg.ativo
        )
        OR EXISTS (
            SELECT 1 FROM usuario_turno utw
              JOIN turno tw ON tw.id = utw.turno_id
              JOIN turno_horario thw ON thw.turno_id = tw.id
             WHERE utw.user_id = {alias}.id AND utw.empresa_id = %s AND tw.ativo
               AND thw.dia_semana = %s
               AND thw.hora_inicio <= %s::time AND thw.hora_fim > %s::time
        )
    )"""


async def usuario_em_turno_agora(
    pool: AsyncConnectionPool,
    empresa_id: int,
    user_id: str,
    now: datetime | None = None,
) -> bool:
    """Checagem standalone do gate pra um único usuário (claim/API/testes)."""
    dia_semana, hora = await turno_now(pool, empresa_id, now)
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT EXISTS (SELECT 1 FROM usuario_turno ut "
            "JOIN turno t ON t.id = ut.turno_id "
            "WHERE ut.user_id = %s AND ut.empresa_id = %s AND t.ativo)",
            (user_id, empresa_id),
        )
        row = await cur.fetchone()
        if not (row and row[0]):
            return True  # sem turno ativo atribuído → irrestrito
        cur = await conn.execute(
            "SELECT EXISTS (SELECT 1 FROM usuario_turno ut "
            "JOIN turno t ON t.id = ut.turno_id "
            "JOIN turno_horario th ON th.turno_id = t.id "
            "WHERE ut.user_id = %s AND ut.empresa_id = %s AND t.ativo "
            "AND th.dia_semana = %s "
            "AND th.hora_inicio <= %s::time AND th.hora_fim > %s::time)",
            (user_id, empresa_id, dia_semana, hora, hora),
        )
        row = await cur.fetchone()
    return bool(row and row[0])
