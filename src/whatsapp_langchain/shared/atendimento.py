"""Helpers de Atendimento — fila estruturada de conversas (M3 CRM Light).

Cada inbound resolve um `atendimento` aberto por (empresa, cliente, conexão)
via `open_or_attach_atendimento`. Política:

- Se já existe um aberto (status `aguardando` ou `em_andamento`), **anexa**
  (atualiza `last_message_at` e retorna o id existente).
- Senão, **abre** um novo com status `aguardando`.
- Status final (`resolvido`/`abandonado`) sai do índice parcial único, então
  o próximo inbound abre um atendimento novo.

Painel: `list_atendimentos` aplica 4 tipos de visualização derivados em
runtime — "meus" (atribuídos ao operador), "aguardando" (sem dono),
"grupos" (futuro — placeholder vazio) e "outros" (catch-all dos abertos).
"""

from __future__ import annotations

from typing import Literal

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.models import Atendimento

logger = structlog.get_logger()


# Sem alias — usado em RETURNING de INSERT/UPDATE (RETURNING não enxerga alias).
# Ordem: 11 colunas base + 5 mig 047 (padrão profissional) + 7 mig 061 (triagem) = 23.
_BARE_COLS = (
    "id, empresa_id, cliente_id, conexao_id, agente_atual, "
    "status, assigned_to_user_id, last_message_at, closed_at, "
    "created_at, updated_at, "
    # Mig 047 padrão profissional
    "protocolo, qtde_resposta_invalida, iniciado_cliente, "
    "finalizado_por_user_id, solicitou_encerramento, "
    # Mig 061 triagem omnichannel
    "departamento_id, classificacao, prioridade, sentimento, "
    "resumo_ia, triagem_completa, triagem_at"
)
# Com alias `a.` — usado em SELECTs com JOIN.
_BASE_COLS = ", ".join(f"a.{c.strip()}" for c in _BARE_COLS.split(","))
_JOIN_COLS = f"{_BASE_COLS}, c.nome, c.telefone"


def _row_to_atendimento(row, *, with_cliente: bool = False) -> Atendimento:
    # Índices fixos (lista BARE_COLS): 0..10 base, 11..15 mig 047, 16..22 mig 061
    base_len = 23
    return Atendimento(
        id=row[0],
        empresa_id=row[1],
        cliente_id=row[2],
        conexao_id=row[3],
        agente_atual=row[4],
        status=row[5],
        assigned_to_user_id=row[6],
        last_message_at=row[7],
        closed_at=row[8],
        created_at=row[9],
        updated_at=row[10],
        # Mig 047
        protocolo=row[11],
        qtde_resposta_invalida=row[12] or 0,
        iniciado_cliente=row[13] if row[13] is not None else True,
        finalizado_por_user_id=row[14],
        solicitou_encerramento=row[15] if row[15] is not None else False,
        # Mig 061
        departamento_id=row[16],
        classificacao=row[17],
        prioridade=row[18],
        sentimento=row[19],
        resumo_ia=row[20],
        triagem_completa=row[21] if row[21] is not None else False,
        triagem_at=row[22],
        # JOIN extras (apenas quando _JOIN_COLS é usado)
        cliente_nome=row[base_len] if with_cliente and len(row) > base_len else None,
        cliente_telefone=row[base_len + 1]
        if with_cliente and len(row) > base_len + 1
        else None,
    )


async def open_or_attach_atendimento(
    pool: AsyncConnectionPool,
    empresa_id: int,
    cliente_id: int,
    conexao_id: int,
    *,
    agente: str = "vsa_tech",
) -> tuple[Atendimento, bool]:
    """Abre novo atendimento ou anexa ao já-aberto (fluxo do webhook).

    Usa o índice parcial `idx_atendimento_aberto_unique` (empresa+cliente+conexao
    WHERE status IN aguardando|em_andamento) pra garantir 1 atendimento aberto
    por tupla. Quando já existe, atualiza `last_message_at` e retorna o id
    existente em uma transação curta.

    Retorna `(atendimento, was_created)` — o flag permite o caller disparar
    o evento `atendimento.aberto` só quando um row novo foi inserido.
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {_BASE_COLS} FROM atendimento a
             WHERE a.empresa_id = %s
               AND a.cliente_id = %s
               AND a.conexao_id = %s
               AND a.status IN ('aguardando', 'em_andamento')
             FOR UPDATE
            """,
            (empresa_id, cliente_id, conexao_id),
        )
        row = await cur.fetchone()
        if row:
            cur = await conn.execute(
                f"""
                UPDATE atendimento
                   SET last_message_at = NOW(), updated_at = NOW()
                 WHERE id = %s
                RETURNING {_BARE_COLS}
                """,
                (row[0],),
            )
            updated = await cur.fetchone()
            assert updated is not None
            return _row_to_atendimento(updated), False

        cur = await conn.execute(
            f"""
            INSERT INTO atendimento (empresa_id, cliente_id, conexao_id, agente_atual)
            VALUES (%s, %s, %s, %s)
            RETURNING {_BARE_COLS}
            """,
            (empresa_id, cliente_id, conexao_id, agente),
        )
        new = await cur.fetchone()
    assert new is not None
    return _row_to_atendimento(new), True


TipoVisualizacao = Literal["meus", "aguardando", "grupos", "outros"]


async def list_atendimentos(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    tipo: TipoVisualizacao,
    current_user_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    scope_departamento_ids: set[int] | None = None,
    dep_id: int | None = None,
    prioridade: str | None = None,
    q: str | None = None,
) -> list[Atendimento]:
    """Lista atendimentos filtrados por tipo de visualização.

    - `meus`: status='em_andamento' AND assigned_to_user_id=current_user_id
    - `aguardando`: status='aguardando'
    - `grupos`: placeholder (vazio até M-grupos chegar)
    - `outros`: status IN aguardando|em_andamento, fora dos meus

    `scope_departamento_ids` (E2.B):
    - None ⇒ sem filtro (vê todos os departamentos da empresa).
    - set vazio ⇒ user com scope mas sem departamento → retorna [].
    - set com IDs ⇒ filtra `WHERE departamento_id ∈ ids`.
      `departamento_id IS NULL` (atendimentos sem departamento) NÃO
      aparece pra users com scope — política de "default-deny" pra
      garantir isolamento.

    Faz LEFT JOIN com cliente pra preencher nome/telefone na resposta.
    """
    if tipo == "grupos":
        return []

    if scope_departamento_ids is not None and not scope_departamento_ids:
        return []

    where = "WHERE a.empresa_id = %s"
    params: list = [empresa_id]

    if tipo == "meus":
        if not current_user_id:
            return []
        where += " AND a.status = 'em_andamento' AND a.assigned_to_user_id = %s"
        params.append(current_user_id)
    elif tipo == "aguardando":
        where += " AND a.status = 'aguardando'"
    else:  # outros
        where += " AND a.status IN ('aguardando', 'em_andamento')"
        if current_user_id:
            where += (
                " AND (a.assigned_to_user_id IS NULL OR a.assigned_to_user_id <> %s)"
            )
            params.append(current_user_id)

    if scope_departamento_ids is not None:
        where += " AND a.departamento_id = ANY(%s)"
        params.append(list(scope_departamento_ids))

    # Filtros opcionais Sprint F.2 — admin/atendente refina a lista
    if dep_id is not None:
        where += " AND a.departamento_id = %s"
        params.append(dep_id)
    if prioridade is not None:
        where += " AND a.prioridade = %s"
        params.append(prioridade)
    if q:
        where += " AND (c.nome ILIKE %s OR a.protocolo ILIKE %s)"
        like = f"%{q.strip()}%"
        params.extend([like, like])

    params.extend([limit, offset])
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {_JOIN_COLS}
              FROM atendimento a
              LEFT JOIN cliente c ON c.id = a.cliente_id
            {where}
            ORDER BY a.last_message_at DESC, a.id DESC
            LIMIT %s OFFSET %s
            """,  # type: ignore[arg-type]
            tuple(params),
        )
        rows = await cur.fetchall()
    return [_row_to_atendimento(r, with_cliente=True) for r in rows]


async def get_atendimento_by_id(
    pool: AsyncConnectionPool, atendimento_id: int
) -> Atendimento | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {_JOIN_COLS}
              FROM atendimento a
              LEFT JOIN cliente c ON c.id = a.cliente_id
             WHERE a.id = %s
            """,
            (atendimento_id,),
        )
        row = await cur.fetchone()
    return _row_to_atendimento(row, with_cliente=True) if row else None


async def list_atendimentos_by_cliente(
    pool: AsyncConnectionPool,
    empresa_id: int,
    cliente_id: int,
    *,
    limit: int = 10,
    exclude_id: int | None = None,
) -> list[Atendimento]:
    """Histórico de atendimentos do cliente — usado por tools do agente (M5.b.1).

    `exclude_id` permite o agente pedir "histórico exceto o atendimento
    atual" pra não se citar a si próprio.
    """
    where = "WHERE a.empresa_id = %s AND a.cliente_id = %s"
    params: list = [empresa_id, cliente_id]
    if exclude_id is not None:
        where += " AND a.id <> %s"
        params.append(exclude_id)
    params.append(limit)
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {_JOIN_COLS}
              FROM atendimento a
              LEFT JOIN cliente c ON c.id = a.cliente_id
            {where}
            ORDER BY a.created_at DESC
            LIMIT %s
            """,  # type: ignore[arg-type]
            tuple(params),
        )
        rows = await cur.fetchall()
    return [_row_to_atendimento(r, with_cliente=True) for r in rows]


async def claim_atendimento(
    pool: AsyncConnectionPool, atendimento_id: int, user_id: str
) -> Atendimento | None:
    """Operador "puxa" o atendimento. status → em_andamento, assigned → user."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            UPDATE atendimento
               SET status = 'em_andamento',
                   assigned_to_user_id = %s,
                   updated_at = NOW()
             WHERE id = %s AND status IN ('aguardando', 'em_andamento')
            RETURNING {_BARE_COLS}
            """,
            (user_id, atendimento_id),
        )
        row = await cur.fetchone()
    return _row_to_atendimento(row) if row else None


async def close_atendimento(
    pool: AsyncConnectionPool,
    atendimento_id: int,
    status: Literal["resolvido", "abandonado"] = "resolvido",
) -> Atendimento | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            UPDATE atendimento
               SET status = %s, closed_at = NOW(), updated_at = NOW()
             WHERE id = %s
            RETURNING {_BARE_COLS}
            """,
            (status, atendimento_id),
        )
        row = await cur.fetchone()
    return _row_to_atendimento(row) if row else None


async def list_atendimento_mensagens(
    pool: AsyncConnectionPool,
    atendimento_id: int,
    empresa_id: int,
    *,
    limit: int = 200,
) -> list[dict]:
    """Lista mensagens do atendimento em ordem cronológica.

    Filtra por (empresa_id, atendimento_id) na message_queue. Retorna
    dicts simples (sem Pydantic) com os campos relevantes ao painel —
    o tipo `Message` já é um shape público da API admin/chats.
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT id, agent_id, incoming_message, media_url, media_type,
                   normalized_input, media_processing_status,
                   response, status, created_at, processed_at,
                   media_processing_error, error
              FROM message_queue
             WHERE empresa_id = %s
               AND atendimento_id = %s
             ORDER BY created_at ASC, id ASC
             LIMIT %s
            """,
            (empresa_id, atendimento_id, limit),
        )
        rows = await cur.fetchall()
    return [
        {
            "id": r[0],
            "agent_id": r[1],
            "incoming_message": r[2],
            "media_url": r[3],
            "media_type": r[4],
            "normalized_input": r[5],
            "media_processing_status": r[6],
            "response": r[7],
            "status": r[8],
            "created_at": r[9].isoformat() if r[9] else None,
            "processed_at": r[10].isoformat() if r[10] else None,
            "media_processing_error": r[11],
            "error": r[12],
        }
        for r in rows
    ]


async def transfer_atendimento(
    pool: AsyncConnectionPool, atendimento_id: int, new_user_id: str
) -> Atendimento | None:
    """Transfere o atendimento para outro operador (mantém em_andamento)."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            UPDATE atendimento
               SET assigned_to_user_id = %s,
                   status = 'em_andamento',
                   updated_at = NOW()
             WHERE id = %s
            RETURNING {_BARE_COLS}
            """,
            (new_user_id, atendimento_id),
        )
        row = await cur.fetchone()
    return _row_to_atendimento(row) if row else None


async def transfer_atendimento_to_departamento(
    pool: AsyncConnectionPool, atendimento_id: int, departamento_id: int
) -> Atendimento | None:
    """Transfere o atendimento pra um departamento — limpa o atendente atual e
    volta o status pra 'aguardando' (atendimento entra na fila do depto, qualquer
    atendente do depto pode puxar via `claim`).
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            UPDATE atendimento
               SET departamento_id = %s,
                   assigned_to_user_id = NULL,
                   status = 'aguardando',
                   updated_at = NOW()
             WHERE id = %s
            RETURNING {_BARE_COLS}
            """,
            (departamento_id, atendimento_id),
        )
        row = await cur.fetchone()
    return _row_to_atendimento(row) if row else None


# --- Triagem omnichannel (mig 061) ---


_PRIORIDADES_VALIDAS = {"baixa", "media", "alta", "urgente"}
_SENTIMENTOS_VALIDOS = {"positivo", "neutro", "negativo", "frustrado"}


async def set_classificacao(
    pool: AsyncConnectionPool,
    atendimento_id: int,
    *,
    prioridade: str,
    sentimento: str,
    classificacao: str,
) -> Atendimento | None:
    """Registra classificação da triagem feita pelo agente IA.

    Idempotente — pode ser chamada múltiplas vezes pra re-classificar.
    Atualiza `triagem_at = NOW()`. Levanta `ValueError` em valores inválidos
    (mesmos do CHECK da migration 061).
    """
    if prioridade not in _PRIORIDADES_VALIDAS:
        raise ValueError(
            f"prioridade inválida: {prioridade!r} (use {_PRIORIDADES_VALIDAS})"
        )
    if sentimento not in _SENTIMENTOS_VALIDOS:
        raise ValueError(
            f"sentimento inválido: {sentimento!r} (use {_SENTIMENTOS_VALIDOS})"
        )
    classificacao_clean = (classificacao or "").strip()[:120] or None
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            UPDATE atendimento
               SET prioridade = %s,
                   sentimento = %s,
                   classificacao = %s,
                   triagem_at = NOW(),
                   updated_at = NOW()
             WHERE id = %s
            RETURNING {_BARE_COLS}
            """,
            (prioridade, sentimento, classificacao_clean, atendimento_id),
        )
        row = await cur.fetchone()
    return _row_to_atendimento(row) if row else None


async def count_fila_departamento(
    pool: AsyncConnectionPool,
    *,
    empresa_id: int,
    departamento_id: int,
    atendimento_id: int,
) -> int:
    """Posição (1-based) do atendimento na fila do departamento.

    Conta atendimentos abertos (aguardando|em_andamento) no mesmo dep
    que foram atualizados ANTES (last_message_at <=) do atendimento_id
    em questão. Posição 1 = próximo a ser atendido. Útil pra mensagem
    "Você está na posição N da fila".
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT COUNT(*) FROM atendimento a
              JOIN atendimento self ON self.id = %s
             WHERE a.empresa_id = %s
               AND a.departamento_id = %s
               AND a.status IN ('aguardando', 'em_andamento')
               AND a.assigned_to_user_id IS NULL
               AND a.last_message_at <= self.last_message_at
            """,
            (atendimento_id, empresa_id, departamento_id),
        )
        row = await cur.fetchone()
    return int(row[0]) if row else 1


async def complete_triagem(
    pool: AsyncConnectionPool,
    atendimento_id: int,
    *,
    departamento_id: int,
    resumo_ia: str,
    prioridade: str | None = None,
) -> Atendimento | None:
    """Marca triagem completa: vincula depto, salva resumo, opcional prioridade.

    Setado por `transfer_to_human` ao final da triagem. Não toca em
    classificacao/sentimento (set_classificacao já cuida disso). Define
    `triagem_completa=TRUE` e `triagem_at` se ainda não setado.
    """
    if prioridade is not None and prioridade not in _PRIORIDADES_VALIDAS:
        raise ValueError(f"prioridade inválida: {prioridade!r}")
    sets = [
        "departamento_id = %s",
        "resumo_ia = %s",
        "triagem_completa = TRUE",
        "triagem_at = COALESCE(triagem_at, NOW())",
        "updated_at = NOW()",
    ]
    params: list = [departamento_id, resumo_ia]
    if prioridade is not None:
        sets.insert(2, "prioridade = %s")
        params.insert(2, prioridade)
    params.append(atendimento_id)
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"UPDATE atendimento SET {', '.join(sets)} WHERE id = %s "  # type: ignore[arg-type]
            f"RETURNING {_BARE_COLS}",
            tuple(params),
        )
        row = await cur.fetchone()
    return _row_to_atendimento(row) if row else None
