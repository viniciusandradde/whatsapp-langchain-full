"""Variáveis de ambiente por empresa (M5.d).

Permite que admin cadastre KVs (`{nome, valor}`) e referencie em prompts/
modelos como `{{var.NOME}}`. O `render_template` resolve namespaces:

- `empresa.*` — campos do row de empresa (nome, slug, plano, doc).
- `cliente.*` — campos do cliente do atendimento (quando disponível).
- `data.*`   — runtime (`hoje`, `agora`, `now_iso`).
- `var.*`    — KVs cadastrados por empresa em `variavel_ambiente`.

Render é puro: chaves não encontradas ficam literais (`{{var.x}}`) — assim
problemas de variável quebrada são visíveis no log/UI sem derrubar o flow.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import structlog
from psycopg import errors as pg_errors
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.models import VariavelAmbiente, VariavelAmbienteInput

logger = structlog.get_logger()


class DuplicateNomeError(ValueError):
    """Outra variável da mesma empresa já usa esse nome."""


_SELECT_COLS = (
    "id, empresa_id, nome, valor, descricao, ativo, "
    "created_by_user_id, created_at, updated_at"
)


def _row_to_variavel(row) -> VariavelAmbiente:
    return VariavelAmbiente(
        id=row[0],
        empresa_id=row[1],
        nome=row[2],
        valor=row[3],
        descricao=row[4],
        ativo=row[5],
        created_by_user_id=row[6],
        created_at=row[7],
        updated_at=row[8],
    )


# --- CRUD ---


async def list_variaveis(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    apenas_ativos: bool = False,
) -> list[VariavelAmbiente]:
    where = "empresa_id = %s"
    if apenas_ativos:
        where += " AND ativo"
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {_SELECT_COLS} FROM variavel_ambiente "
            f"WHERE {where} ORDER BY nome ASC",
            (empresa_id,),
        )
        rows = await cur.fetchall()
    return [_row_to_variavel(r) for r in rows]


async def get_variavel_by_id(
    pool: AsyncConnectionPool, empresa_id: int, var_id: int
) -> VariavelAmbiente | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {_SELECT_COLS} FROM variavel_ambiente "
            "WHERE id = %s AND empresa_id = %s",
            (var_id, empresa_id),
        )
        row = await cur.fetchone()
    return _row_to_variavel(row) if row else None


async def create_variavel(
    pool: AsyncConnectionPool,
    empresa_id: int,
    data: VariavelAmbienteInput,
    *,
    user_id: str | None = None,
) -> VariavelAmbiente:
    try:
        async with pool.connection() as conn:
            cur = await conn.execute(
                f"""
                INSERT INTO variavel_ambiente
                    (empresa_id, nome, valor, descricao, ativo,
                     created_by_user_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING {_SELECT_COLS}
                """,
                (
                    empresa_id,
                    data.nome,
                    data.valor,
                    data.descricao,
                    data.ativo,
                    user_id,
                ),
            )
            row = await cur.fetchone()
    except pg_errors.UniqueViolation as e:
        raise DuplicateNomeError(f"variável '{data.nome}' já existe na empresa") from e
    assert row is not None
    return _row_to_variavel(row)


async def update_variavel(
    pool: AsyncConnectionPool,
    empresa_id: int,
    var_id: int,
    data: VariavelAmbienteInput,
) -> VariavelAmbiente | None:
    try:
        async with pool.connection() as conn:
            cur = await conn.execute(
                f"""
                UPDATE variavel_ambiente
                   SET nome = %s,
                       valor = %s,
                       descricao = %s,
                       ativo = %s,
                       updated_at = NOW()
                 WHERE id = %s AND empresa_id = %s
                RETURNING {_SELECT_COLS}
                """,
                (
                    data.nome,
                    data.valor,
                    data.descricao,
                    data.ativo,
                    var_id,
                    empresa_id,
                ),
            )
            row = await cur.fetchone()
    except pg_errors.UniqueViolation as e:
        raise DuplicateNomeError(f"variável '{data.nome}' já existe na empresa") from e
    return _row_to_variavel(row) if row else None


async def delete_variavel(
    pool: AsyncConnectionPool, empresa_id: int, var_id: int
) -> bool:
    async with pool.connection() as conn:
        cur = await conn.execute(
            "DELETE FROM variavel_ambiente WHERE id = %s AND empresa_id = %s",
            (var_id, empresa_id),
        )
    return (cur.rowcount or 0) > 0


# --- Render ---


_TEMPLATE_RE = re.compile(
    r"\{\{\s*([a-zA-Z][a-zA-Z0-9_]*\.[a-zA-Z][a-zA-Z0-9_]*)\s*\}\}"
)


def render_template(text: str, ctx: dict[str, str]) -> str:
    """Substitui `{{namespace.key}}` por `ctx[namespace.key]`.

    Chaves ausentes ficam literais — quem ler o texto final consegue ver
    qual var não resolveu (melhor que silenciar com string vazia).
    """
    if not text:
        return text

    def _sub(m: re.Match[str]) -> str:
        key = m.group(1)
        val = ctx.get(key)
        return val if val is not None else m.group(0)

    return _TEMPLATE_RE.sub(_sub, text)


async def build_render_context(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    atendimento_id: int | None = None,
    now: datetime | None = None,
) -> dict[str, str]:
    """Monta o dict de namespaces pra `render_template`.

    Carrega `empresa.*`, `var.*` (ativos), `data.*`, e — quando
    `atendimento_id` é fornecido — `cliente.*` via JOIN. Variáveis cujo
    namespace.chave não existir são deixadas literais pelo renderizador.
    """
    ctx: dict[str, str] = {}
    now = now or datetime.now(UTC)

    # data.*
    ctx["data.hoje"] = now.date().isoformat()
    ctx["data.agora"] = now.strftime("%H:%M")
    ctx["data.now_iso"] = now.isoformat()
    ctx["data.ano"] = str(now.year)

    async with pool.connection() as conn:
        # empresa.*
        cur = await conn.execute(
            "SELECT nome, slug, doc, plano FROM empresa WHERE id = %s",
            (empresa_id,),
        )
        row = await cur.fetchone()
        if row is not None:
            ctx["empresa.nome"] = row[0] or ""
            ctx["empresa.slug"] = row[1] or ""
            ctx["empresa.doc"] = row[2] or ""
            ctx["empresa.plano"] = row[3] or ""

        # menu.* — primeiro menu ativo da empresa (ou conexão genérica).
        # Usado pelo SYSTEM_PROMPT do agente pra avisar cliente como
        # voltar pro menu (ex: "Digite *{{menu.trigger}}* pra trocar setor").
        cur = await conn.execute(
            "SELECT trigger_keywords, atalho FROM menu_chatbot "
            "WHERE empresa_id = %s AND ativo "
            "ORDER BY conexao_id NULLS LAST, id LIMIT 1",
            (empresa_id,),
        )
        row = await cur.fetchone()
        if row is not None:
            triggers = list(row[0] or [])
            atalho = row[1] or ""
            ctx["menu.trigger"] = triggers[0] if triggers else atalho or "menu"
            ctx["menu.triggers"] = (
                ", ".join(triggers) if triggers else (atalho or "menu")
            )
            ctx["menu.atalho"] = atalho or (triggers[0] if triggers else "menu")
        else:
            # Sem menu cadastrado — placeholders genéricos pra prompt não quebrar
            ctx["menu.trigger"] = "menu"
            ctx["menu.triggers"] = "menu"
            ctx["menu.atalho"] = "menu"

        # var.* (apenas ativos)
        cur = await conn.execute(
            "SELECT nome, valor FROM variavel_ambiente WHERE empresa_id = %s AND ativo",
            (empresa_id,),
        )
        for nome, valor in await cur.fetchall():
            ctx[f"var.{nome}"] = valor or ""

        # cliente.* (opcional, só quando temos atendimento)
        if atendimento_id is not None:
            cur = await conn.execute(
                """
                SELECT c.nome, c.telefone, c.email, c.doc
                  FROM atendimento a
                  JOIN cliente c ON c.id = a.cliente_id
                 WHERE a.id = %s AND a.empresa_id = %s
                """,
                (atendimento_id, empresa_id),
            )
            row = await cur.fetchone()
            if row is not None:
                ctx["cliente.nome"] = row[0] or ""
                ctx["cliente.telefone"] = row[1] or ""
                ctx["cliente.email"] = row[2] or ""
                ctx["cliente.doc"] = row[3] or ""

    return ctx
