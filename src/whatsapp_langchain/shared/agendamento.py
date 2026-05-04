"""CRUD + validação de regras de agendamentos (S2/S3 Calendar v2).

Source-of-truth interno. `calendar_integration.create_event` insere aqui
ANTES de chamar o Google e atualiza com `evento_id_externo` retornado.
Em caso de falha do Google, marca `status='cancelado'` (drift compensado)
e dispara warning estruturado.

S3 adiciona `validate_request(empresa_id, start, end)` que aplica regras
da tabela `agendamento_regras` antes de chamar Google: janela de horário,
antecedência mínima, dias permitidos, dias bloqueados.

Padrão segue `shared/cliente.py` e outros módulos de domínio.
"""

from __future__ import annotations

import json
from datetime import datetime, time, timedelta, timezone
from typing import Final
from zoneinfo import ZoneInfo

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.models import Agendamento

logger = structlog.get_logger()


VALID_STATUS: Final[frozenset[str]] = frozenset(
    {"pendente", "confirmado", "cancelado"}
)

_SELECT_COLS = (
    "id, empresa_id, calendar_id, user_id_criador, cliente_id, "
    "evento_id_externo, summary, descricao, data_inicio, data_fim, "
    "status, aprovado, gestor_notificado, payload_externo, "
    "created_at, updated_at"
)


def _row_to_agendamento(row) -> Agendamento:
    return Agendamento(
        id=row[0],
        empresa_id=row[1],
        calendar_id=row[2],
        user_id_criador=row[3],
        cliente_id=row[4],
        evento_id_externo=row[5],
        summary=row[6],
        descricao=row[7],
        data_inicio=row[8],
        data_fim=row[9],
        status=row[10],
        aprovado=row[11],
        gestor_notificado=row[12],
        payload_externo=row[13] or {},
        created_at=row[14],
        updated_at=row[15],
    )


async def create(
    pool: AsyncConnectionPool,
    *,
    empresa_id: int,
    calendar_id: str,
    summary: str,
    data_inicio: datetime,
    data_fim: datetime,
    user_id_criador: str | None = None,
    cliente_id: int | None = None,
    descricao: str | None = None,
    status: str = "confirmado",
    aprovado: bool = True,
) -> Agendamento:
    """Cria row em `agendamento`. Retorna o objeto persistido."""
    if status not in VALID_STATUS:
        raise ValueError(f"status inválido: {status!r}")

    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            INSERT INTO agendamento
                (empresa_id, calendar_id, user_id_criador, cliente_id,
                 summary, descricao, data_inicio, data_fim, status, aprovado)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING {_SELECT_COLS}
            """,
            (
                empresa_id,
                calendar_id,
                user_id_criador,
                cliente_id,
                summary,
                descricao,
                data_inicio,
                data_fim,
                status,
                aprovado,
            ),
        )
        row = await cur.fetchone()
        await conn.commit()
    assert row is not None
    return _row_to_agendamento(row)


async def get_by_id(
    pool: AsyncConnectionPool, agendamento_id: int, empresa_id: int
) -> Agendamento | None:
    """Busca por id, escopado por empresa pra anti-tenant escape."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {_SELECT_COLS}
              FROM agendamento
             WHERE id = %s AND empresa_id = %s
            """,
            (agendamento_id, empresa_id),
        )
        row = await cur.fetchone()
    return _row_to_agendamento(row) if row else None


async def list_by_period(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    inicio: datetime,
    fim: datetime,
    status: str | None = None,
    cliente_id: int | None = None,
    limit: int = 100,
) -> list[Agendamento]:
    """Lista agendamentos da empresa cuja data_inicio está em [inicio, fim].

    Filtros opcionais: `status`, `cliente_id`. Ordenado por data_inicio asc.
    """
    where = ["empresa_id = %s", "data_inicio >= %s", "data_inicio <= %s"]
    params: list = [empresa_id, inicio, fim]
    if status:
        if status not in VALID_STATUS:
            raise ValueError(f"status inválido: {status!r}")
        where.append("status = %s")
        params.append(status)
    if cliente_id is not None:
        where.append("cliente_id = %s")
        params.append(cliente_id)
    params.append(limit)

    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {_SELECT_COLS}
              FROM agendamento
             WHERE {" AND ".join(where)}
             ORDER BY data_inicio ASC
             LIMIT %s
            """,
            params,
        )
        rows = await cur.fetchall()
    return [_row_to_agendamento(r) for r in rows]


async def update_external_event(
    pool: AsyncConnectionPool,
    agendamento_id: int,
    *,
    evento_id_externo: str,
    payload_externo: dict,
) -> None:
    """Atualiza com o id retornado pelo Google e snapshot do payload.

    Chamado logo após `events.insert` retornar com sucesso.
    """
    async with pool.connection() as conn:
        await conn.execute(
            """
            UPDATE agendamento
               SET evento_id_externo = %s,
                   payload_externo = %s::jsonb,
                   updated_at = NOW()
             WHERE id = %s
            """,
            (evento_id_externo, json.dumps(payload_externo), agendamento_id),
        )
        await conn.commit()


async def update_status(
    pool: AsyncConnectionPool,
    agendamento_id: int,
    empresa_id: int,
    *,
    status: str,
) -> bool:
    """Muda status (ex: confirmado → cancelado). Retorna True se afetou row."""
    if status not in VALID_STATUS:
        raise ValueError(f"status inválido: {status!r}")

    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            UPDATE agendamento
               SET status = %s, updated_at = NOW()
             WHERE id = %s AND empresa_id = %s
            """,
            (status, agendamento_id, empresa_id),
        )
        await conn.commit()
        return cur.rowcount > 0


async def cancel_local(
    pool: AsyncConnectionPool, agendamento_id: int, empresa_id: int
) -> bool:
    """Atalho pra `update_status(... 'cancelado')`."""
    return await update_status(
        pool, agendamento_id, empresa_id, status="cancelado"
    )


async def get_by_external_id(
    pool: AsyncConnectionPool, empresa_id: int, evento_id_externo: str
) -> Agendamento | None:
    """Lookup por Google event id — usado em S5 pra reconciliar drift."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {_SELECT_COLS}
              FROM agendamento
             WHERE empresa_id = %s AND evento_id_externo = %s
             LIMIT 1
            """,
            (empresa_id, evento_id_externo),
        )
        row = await cur.fetchone()
    return _row_to_agendamento(row) if row else None


# ---------------------------------------------------------------------------
# S3: Validação de regras de negócio
# ---------------------------------------------------------------------------


def _parse_hora(hora_str: str) -> time:
    """Converte 'HH:MM' em time. Já validado em `agendamento_regras`."""
    h, m = hora_str.split(":")
    return time(int(h), int(m))


async def validate_request(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    start: datetime,
    end: datetime,
) -> tuple[bool, str | None]:
    """Aplica regras de `agendamento_regras` e timezone da empresa.

    Returns:
        `(True, None)` quando OK; `(False, motivo)` quando recusado. O
        motivo é uma string amigável que vai parar na resposta da tool
        (`calendar_create_event`) e o agente repassa ao cliente.

    Regras (em ordem de checagem):
    1. `start < end` (sanity)
    2. Antecedência mínima: `start >= now + antecedencia_minima_minutos`
    3. Dia da semana permitido (ISO 1-7, default seg-sex)
    4. Dia não está em `dias_bloqueados` (YYYY-MM-DD lista)
    5. Janela de horário comercial em hora LOCAL (timezone da empresa)
    """
    # Lazy imports pra evitar ciclo
    from whatsapp_langchain.shared.agendamento_regras import get as _get_regras
    from whatsapp_langchain.shared.calendar_integration import (
        get_calendar_config as _get_cal_config,
    )

    if start >= end:
        return False, "Início precisa ser antes do fim."

    regras = await _get_regras(pool, empresa_id)

    # Timezone da empresa (default America/Sao_Paulo se sem config)
    cal_config = await _get_cal_config(pool, empresa_id)
    tz_name = cal_config.timezone if cal_config else "America/Sao_Paulo"
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("America/Sao_Paulo")

    # Garante que start/end sejam timezone-aware
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)

    # Antecedência mínima
    now = datetime.now(timezone.utc)
    minimo = now + timedelta(minutes=regras.antecedencia_minima_minutos)
    if start < minimo:
        return (
            False,
            f"Antecedência mínima é de {regras.antecedencia_minima_minutos} "
            "minutos. Escolha um horário mais distante.",
        )

    # Converte pra hora local
    start_local = start.astimezone(tz)
    end_local = end.astimezone(tz)

    # Dia da semana permitido (1=seg, 7=dom no padrão ISO; Python isoweekday faz 1=seg, 7=dom)
    dia_semana = start_local.isoweekday()
    if dia_semana not in regras.dias_semana_permitidos:
        nomes = {1: "seg", 2: "ter", 3: "qua", 4: "qui", 5: "sex", 6: "sáb", 7: "dom"}
        permitidos = [nomes.get(d, str(d)) for d in regras.dias_semana_permitidos]
        return (
            False,
            f"Não atendemos {nomes.get(dia_semana, dia_semana)}. "
            f"Dias permitidos: {', '.join(permitidos)}.",
        )

    # Dias bloqueados (feriados/férias)
    data_iso = start_local.date().isoformat()
    if data_iso in regras.dias_bloqueados:
        return (
            False,
            f"Dia {data_iso} está bloqueado (feriado/férias). Escolha outro.",
        )

    # Janela horária local
    hora_inicio = _parse_hora(regras.hora_inicio)
    hora_fim = _parse_hora(regras.hora_fim)
    if start_local.time() < hora_inicio or end_local.time() > hora_fim:
        return (
            False,
            f"Horário fora da janela {regras.hora_inicio}-{regras.hora_fim}. "
            "Sugira um slot dentro do expediente.",
        )

    return True, None
