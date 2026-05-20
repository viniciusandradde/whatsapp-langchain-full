"""Helpers de auditoria LGPD pra agentes IA hospitalares.

Toda ação que toca dado sensível (CPF, data nasc, prontuário, agendamento)
deve registrar evento via `log_event`. Verificação de identidade via
`verify_cliente_identity` valida 3 campos contra a tabela `cliente`.

Compliance: LGPD Art. 37 (relatório de impacto) + CFM (sigilo médico).
"""

from __future__ import annotations

import json
import unicodedata
from datetime import date, datetime
from typing import Any

import structlog
from psycopg_pool import AsyncConnectionPool

logger = structlog.get_logger()


# Tipos de evento aceitos pelo CHECK constraint da mig 094.
# Manter sincronizado com 094_lgpd_event_log.sql.
EVENT_TYPES = {
    "identity_verified",
    "identity_verification_failed",
    "cpf_collected",
    "dob_collected",
    "appointment_lookup",
    "data_shared_with_human",
    "modality_qualified",
    "document_request_created",
    "sensitive_data_exposed",
    "patient_record_accessed",
}


class LGPDEventTypeError(ValueError):
    """event_type não está no conjunto EVENT_TYPES."""


async def log_event(
    pool: AsyncConnectionPool,
    *,
    empresa_id: int,
    event_type: str,
    details: dict[str, Any] | None = None,
    atendimento_id: int | None = None,
    cliente_id: int | None = None,
    agent_slug: str | None = None,
    user_id: str | None = None,
    ip_address: str | None = None,
) -> int:
    """Grava evento de auditoria LGPD. Retorna id do row.

    Levanta `LGPDEventTypeError` se event_type não estiver em EVENT_TYPES.

    Sempre faz `conn.commit()` — psycopg async pool não comita
    automaticamente.
    """
    if event_type not in EVENT_TYPES:
        raise LGPDEventTypeError(
            f"event_type '{event_type}' inválido. Use um de: {sorted(EVENT_TYPES)}"
        )

    payload = json.dumps(details or {}, ensure_ascii=False, default=str)

    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            INSERT INTO lgpd_event_log (
                empresa_id, atendimento_id, cliente_id,
                agent_slug, user_id, event_type, details, ip_address
            ) VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
            RETURNING id
            """,
            (
                empresa_id,
                atendimento_id,
                cliente_id,
                agent_slug,
                user_id,
                event_type,
                payload,
                ip_address,
            ),
        )
        row = await cur.fetchone()
        await conn.commit()

    event_id = int(row[0]) if row else 0
    logger.info(
        "lgpd_event_logged",
        event_id=event_id,
        event_type=event_type,
        empresa_id=empresa_id,
        atendimento_id=atendimento_id,
        cliente_id=cliente_id,
        agent_slug=agent_slug,
    )
    return event_id


def _normalize_nome(nome: str) -> str:
    """Pra match case-insensitive + sem acentos."""
    nfkd = unicodedata.normalize("NFKD", nome.strip().lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _normalize_data(raw: str) -> date | None:
    """Aceita dd/mm/aaaa ou aaaa-mm-dd. Retorna None se inválido."""
    raw = raw.strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


def _normalize_cpf_ultimos4(raw: str) -> str | None:
    """Extrai os últimos 4 dígitos."""
    digits = "".join(c for c in raw if c.isdigit())
    if len(digits) < 4:
        return None
    return digits[-4:]


async def verify_cliente_identity(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    nome: str,
    data_nascimento: str,
    cpf_ultimos4: str,
) -> dict[str, Any]:
    """Match contra tabela `cliente` (mig 010 + mig 038).

    Critérios (todos obrigatórios):
    - nome: match exato após normalização (lower + sem acento + trim)
    - data_nascimento: igual à coluna DATE
    - cpf_ultimos4: últimos 4 dígitos do `cliente.cpf`

    Returns:
        {"verified": True, "patient_id": int} se match único OU
        {"verified": False, "reason": str} caso contrário.

    Reasons: "nome_invalido", "data_invalida", "cpf_invalido",
    "nao_encontrado", "multiplos_matches".
    """
    nome_norm = _normalize_nome(nome)
    if not nome_norm:
        return {"verified": False, "reason": "nome_invalido"}

    data_obj = _normalize_data(data_nascimento)
    if data_obj is None:
        return {"verified": False, "reason": "data_invalida"}

    cpf4 = _normalize_cpf_ultimos4(cpf_ultimos4)
    if cpf4 is None:
        return {"verified": False, "reason": "cpf_invalido"}

    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT id, nome, cpf
              FROM cliente
             WHERE empresa_id = %s
               AND data_nascimento = %s
               AND cpf IS NOT NULL
               AND RIGHT(REGEXP_REPLACE(cpf, '[^0-9]', '', 'g'), 4) = %s
            """,
            (empresa_id, data_obj, cpf4),
        )
        rows = await cur.fetchall()

    # Match nome em Python pra normalizar acentos/case
    matches = [
        r for r in rows if r[1] and _normalize_nome(r[1]) == nome_norm
    ]
    if not matches:
        return {"verified": False, "reason": "nao_encontrado"}
    if len(matches) > 1:
        logger.warning(
            "lgpd_verify_multiple_matches",
            empresa_id=empresa_id,
            count=len(matches),
        )
        return {"verified": False, "reason": "multiplos_matches"}

    return {"verified": True, "patient_id": int(matches[0][0])}


async def list_events(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    event_type: str | None = None,
    atendimento_id: int | None = None,
    cliente_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Lista eventos LGPD da empresa, ordenado por created_at DESC."""
    filters = ["empresa_id = %s"]
    args: list[Any] = [empresa_id]

    if event_type:
        filters.append("event_type = %s")
        args.append(event_type)
    if atendimento_id is not None:
        filters.append("atendimento_id = %s")
        args.append(atendimento_id)
    if cliente_id is not None:
        filters.append("cliente_id = %s")
        args.append(cliente_id)
    if date_from:
        filters.append("created_at >= %s")
        args.append(date_from)
    if date_to:
        filters.append("created_at <= %s")
        args.append(date_to)

    where = " AND ".join(filters)
    args.extend([limit, offset])

    query = (
        "SELECT id, empresa_id, atendimento_id, cliente_id, agent_slug, "
        "user_id, event_type, details, ip_address, created_at "
        f"FROM lgpd_event_log WHERE {where} "
        "ORDER BY created_at DESC LIMIT %s OFFSET %s"
    )

    async with pool.connection() as conn:
        cur = await conn.execute(query, tuple(args))  # type: ignore[arg-type]
        rows = await cur.fetchall()

    return [
        {
            "id": r[0],
            "empresa_id": r[1],
            "atendimento_id": r[2],
            "cliente_id": r[3],
            "agent_slug": r[4],
            "user_id": r[5],
            "event_type": r[6],
            "details": r[7] or {},
            "ip_address": r[8],
            "created_at": r[9].isoformat() if r[9] else None,
        }
        for r in rows
    ]


async def count_events(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    event_type: str | None = None,
    atendimento_id: int | None = None,
) -> int:
    """Conta eventos pra paginação."""
    filters = ["empresa_id = %s"]
    args: list[Any] = [empresa_id]
    if event_type:
        filters.append("event_type = %s")
        args.append(event_type)
    if atendimento_id is not None:
        filters.append("atendimento_id = %s")
        args.append(atendimento_id)
    where = " AND ".join(filters)
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT COUNT(*) FROM lgpd_event_log WHERE {where}",  # type: ignore[arg-type]
            tuple(args),
        )
        row = await cur.fetchone()
    return int(row[0]) if row else 0
