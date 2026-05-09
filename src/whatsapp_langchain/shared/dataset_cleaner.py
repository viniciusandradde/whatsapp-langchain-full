"""Dataset cleaner — Sprint S.5.

Filtros pra limpar fewshot_example antes de clusterizar:
- Saudações isoladas ("oi", "boa tarde")
- Mensagens muito curtas ou só emoji
- Duplicatas exatas

Estratégia: NÃO deleta. Marca status='disabled' (reversível via UPDATE).
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

import structlog
from psycopg_pool import AsyncConnectionPool

logger = structlog.get_logger()


_GREETING_RE = re.compile(
    r"^\s*(ol[áa]|oi+|opa|salve|boa\s*(tarde|noite)|bom\s*dia|"
    r"hello|hi|hey|tudo\s*bem|td\s*bem|tdb|"
    r"obrigad[oa]+|valeu|tks?|thanks|ok+|certo|sim|n[ãa]o|"
    r"\.+|!+|\?+)\s*[\.\!\?]*\s*$",
    re.IGNORECASE,
)
_EMOJI_ONLY_RE = re.compile(
    r"^[\s\U0001F300-\U0001FAFF\U00002600-\U000027BF✀-➿\.\!\?\,]+$"
)


@dataclass
class CleanStats:
    total: int
    greetings: int
    low_value: int
    duplicates: int
    will_disable: int


def is_greeting(msg: str) -> bool:
    if not msg or len(msg.strip()) > 30:
        return False
    return bool(_GREETING_RE.match(msg.strip()))


def is_low_value(msg: str) -> bool:
    s = msg.strip() if msg else ""
    if len(s) < 6:
        return True
    if _EMOJI_ONLY_RE.match(s):
        return True
    if s.lower() in ("ok", "sim", "não", "nao", "obrigado", "obrigada", "valeu"):
        return True
    return False


async def analyze_dataset(
    pool: AsyncConnectionPool, empresa_id: int
) -> CleanStats:
    """Conta quantas msgs cairiam em cada filtro (dry-run)."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT cliente_msg
              FROM fewshot_example
             WHERE empresa_id = %s
               AND status != 'disabled'
            """,
            (empresa_id,),
        )
        rows = await cur.fetchall()

    msgs = [r[0] for r in rows if r[0]]
    total = len(msgs)
    greetings = sum(1 for m in msgs if is_greeting(m))
    low_value = sum(1 for m in msgs if is_low_value(m) and not is_greeting(m))

    # Duplicatas: msg_normalizada → count
    counts = Counter(m.strip().lower() for m in msgs)
    duplicates = sum(c - 1 for c in counts.values() if c > 1)

    # will_disable = greetings + low_value + duplicates (sem dupla contagem
    # exata: aproximação razoável)
    will_disable = greetings + low_value + duplicates
    return CleanStats(
        total=total,
        greetings=greetings,
        low_value=low_value,
        duplicates=duplicates,
        will_disable=min(will_disable, total),
    )


async def clean_dataset(
    pool: AsyncConnectionPool, empresa_id: int
) -> CleanStats:
    """Marca status='disabled' nas mensagens de baixo valor.

    Idempotente: re-runs não fazem nada nos já desativados.
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT id, cliente_msg
              FROM fewshot_example
             WHERE empresa_id = %s AND status != 'disabled'
            """,
            (empresa_id,),
        )
        rows = await cur.fetchall()

    to_disable: list[int] = []
    seen: set[str] = set()
    counts = {
        "total": len(rows),
        "greetings": 0,
        "low_value": 0,
        "duplicates": 0,
    }

    for fid, msg in rows:
        if not msg:
            continue
        norm = msg.strip().lower()
        if is_greeting(msg):
            counts["greetings"] += 1
            to_disable.append(fid)
        elif is_low_value(msg):
            counts["low_value"] += 1
            to_disable.append(fid)
        elif norm in seen:
            counts["duplicates"] += 1
            to_disable.append(fid)
        else:
            seen.add(norm)

    # Bulk update
    if to_disable:
        async with pool.connection() as conn:
            cur = conn.cursor()
            await cur.executemany(
                "UPDATE fewshot_example SET status='disabled' WHERE id=%s",
                [(fid,) for fid in to_disable],
            )
            await conn.commit()

    logger.info(
        "dataset_cleaned",
        empresa_id=empresa_id,
        disabled=len(to_disable),
        **counts,
    )
    return CleanStats(
        total=counts["total"],
        greetings=counts["greetings"],
        low_value=counts["low_value"],
        duplicates=counts["duplicates"],
        will_disable=len(to_disable),
    )
