"""Catálogo de modelos LLM + servidores MCP — Sprint 1+ padrão profissional.

modelo_llm: catálogo central de modelos LLM com custo USD/M tokens.
mcp_server: catálogo de servidores MCP (Model Context Protocol) por empresa.

Ambos são read-mostly + criados/editados via UI admin.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from psycopg_pool import AsyncConnectionPool


# ============================================================================
# modelo_llm
# ============================================================================


@dataclass
class ModeloLLM:
    id: int
    empresa_id: int | None
    provedor: str
    nome: str
    descricao: str | None
    tipo: str
    custo_input_mtok: float | None
    custo_output_mtok: float | None
    janela_contexto: int | None
    ativo: bool
    created_at: Any
    updated_at: Any

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "empresa_id": self.empresa_id,
            "provedor": self.provedor,
            "nome": self.nome,
            "descricao": self.descricao,
            "tipo": self.tipo,
            "custo_input_mtok": (
                float(self.custo_input_mtok) if self.custo_input_mtok is not None else None
            ),
            "custo_output_mtok": (
                float(self.custo_output_mtok) if self.custo_output_mtok is not None else None
            ),
            "janela_contexto": self.janela_contexto,
            "ativo": self.ativo,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


_MODELO_COLS = (
    "id, empresa_id, provedor, nome, descricao, tipo, "
    "custo_input_mtok, custo_output_mtok, janela_contexto, "
    "ativo, created_at, updated_at"
)


def _row_to_modelo(row) -> ModeloLLM:
    return ModeloLLM(*row)


async def list_modelos_llm(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    tipo: str | None = None,
    only_active: bool = True,
) -> list[ModeloLLM]:
    """Lista modelos disponíveis pra empresa: globais (NULL) + da empresa."""
    where = "(empresa_id IS NULL OR empresa_id = %s)"
    params: list = [empresa_id]
    if only_active:
        where += " AND ativo = TRUE"
    if tipo:
        where += " AND tipo = %s"
        params.append(tipo)
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {_MODELO_COLS} FROM modelo_llm "
            f"WHERE {where} ORDER BY provedor, nome",
            tuple(params),
        )
        rows = await cur.fetchall()
    return [_row_to_modelo(r) for r in rows]


async def get_modelo_llm(
    pool: AsyncConnectionPool, modelo_id: int
) -> ModeloLLM | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {_MODELO_COLS} FROM modelo_llm WHERE id = %s",
            (modelo_id,),
        )
        row = await cur.fetchone()
    return _row_to_modelo(row) if row else None


async def create_modelo_llm(
    pool: AsyncConnectionPool,
    *,
    empresa_id: int | None,
    provedor: str,
    nome: str,
    tipo: str,
    descricao: str | None = None,
    custo_input_mtok: float | None = None,
    custo_output_mtok: float | None = None,
    janela_contexto: int | None = None,
) -> ModeloLLM:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            INSERT INTO modelo_llm
                (empresa_id, provedor, nome, descricao, tipo,
                 custo_input_mtok, custo_output_mtok, janela_contexto)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING {_MODELO_COLS}
            """,
            (empresa_id, provedor, nome, descricao, tipo,
             custo_input_mtok, custo_output_mtok, janela_contexto),
        )
        row = await cur.fetchone()
        await conn.commit()
    assert row is not None
    return _row_to_modelo(row)


async def update_modelo_llm(
    pool: AsyncConnectionPool, modelo_id: int, **fields: Any
) -> ModeloLLM | None:
    # PATCH parcial — None = limpar. Ver docs/dev/PATCH_PATTERN.md.
    READONLY = {"id", "empresa_id", "created_at", "updated_at"}
    sets: list[str] = []
    params: list = []
    for k, v in fields.items():
        if k in READONLY:
            continue
        sets.append(f"{k} = %s")
        params.append(v)
    if not sets:
        return await get_modelo_llm(pool, modelo_id)
    sets.append("updated_at = NOW()")
    params.append(modelo_id)
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"UPDATE modelo_llm SET {', '.join(sets)} WHERE id = %s "
            f"RETURNING {_MODELO_COLS}",
            tuple(params),
        )
        row = await cur.fetchone()
        await conn.commit()
    return _row_to_modelo(row) if row else None


async def delete_modelo_llm(pool: AsyncConnectionPool, modelo_id: int) -> bool:
    """Hard delete. Modelos globais (empresa_id NULL) não devem ser deletados via UI normal."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            "DELETE FROM modelo_llm WHERE id = %s AND empresa_id IS NOT NULL",
            (modelo_id,),
        )
        await conn.commit()
        return (cur.rowcount or 0) > 0


# ============================================================================
# mcp_server
# ============================================================================


@dataclass
class McpServer:
    id: int
    empresa_id: int
    nome: str
    descricao: str | None
    tipo_conexao: str
    url: str | None
    comando: str | None
    args: str | None
    headers: dict
    status: str
    ultimo_teste_at: Any
    ultimo_erro: str | None
    ativo: bool
    created_by_user_id: str | None
    created_at: Any
    updated_at: Any

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "empresa_id": self.empresa_id,
            "nome": self.nome,
            "descricao": self.descricao,
            "tipo_conexao": self.tipo_conexao,
            "url": self.url,
            "comando": self.comando,
            "args": self.args,
            "headers": self.headers or {},
            "status": self.status,
            "ultimo_teste_at": (
                self.ultimo_teste_at.isoformat() if self.ultimo_teste_at else None
            ),
            "ultimo_erro": self.ultimo_erro,
            "ativo": self.ativo,
            "created_by_user_id": self.created_by_user_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


_MCP_COLS = (
    "id, empresa_id, nome, descricao, tipo_conexao, url, comando, args, "
    "headers, status, ultimo_teste_at, ultimo_erro, ativo, "
    "created_by_user_id, created_at, updated_at"
)


def _row_to_mcp(row) -> McpServer:
    return McpServer(*row)


async def list_mcp_servers(
    pool: AsyncConnectionPool, empresa_id: int, *, only_active: bool = False
) -> list[McpServer]:
    where = "empresa_id = %s"
    if only_active:
        where += " AND ativo = TRUE"
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {_MCP_COLS} FROM mcp_server "
            f"WHERE {where} ORDER BY nome",
            (empresa_id,),
        )
        rows = await cur.fetchall()
    return [_row_to_mcp(r) for r in rows]


async def get_mcp_server(
    pool: AsyncConnectionPool, empresa_id: int, mcp_id: int
) -> McpServer | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {_MCP_COLS} FROM mcp_server "
            f"WHERE empresa_id = %s AND id = %s",
            (empresa_id, mcp_id),
        )
        row = await cur.fetchone()
    return _row_to_mcp(row) if row else None


async def create_mcp_server(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    nome: str,
    tipo_conexao: str,
    descricao: str | None = None,
    url: str | None = None,
    comando: str | None = None,
    args: str | None = None,
    headers: dict | None = None,
    user_id: str | None = None,
) -> McpServer:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            INSERT INTO mcp_server
                (empresa_id, nome, descricao, tipo_conexao, url, comando, args,
                 headers, created_by_user_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
            RETURNING {_MCP_COLS}
            """,
            (empresa_id, nome, descricao, tipo_conexao, url, comando, args,
             json.dumps(headers or {}), user_id),
        )
        row = await cur.fetchone()
        await conn.commit()
    assert row is not None
    return _row_to_mcp(row)


async def update_mcp_server(
    pool: AsyncConnectionPool,
    empresa_id: int,
    mcp_id: int,
    **fields: Any,
) -> McpServer | None:
    # PATCH parcial — None = limpar. Ver docs/dev/PATCH_PATTERN.md.
    READONLY = {"id", "empresa_id", "created_at", "updated_at",
                "created_by_user_id"}
    sets: list[str] = []
    params: list = []
    for k, v in fields.items():
        if k in READONLY:
            continue
        if k == "headers":
            sets.append("headers = %s::jsonb")
            params.append(json.dumps(v) if v is not None else None)
        else:
            sets.append(f"{k} = %s")
            params.append(v)
    if not sets:
        return await get_mcp_server(pool, empresa_id, mcp_id)
    sets.append("updated_at = NOW()")
    params.extend([empresa_id, mcp_id])
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"UPDATE mcp_server SET {', '.join(sets)} "
            f"WHERE empresa_id = %s AND id = %s "
            f"RETURNING {_MCP_COLS}",
            tuple(params),
        )
        row = await cur.fetchone()
        await conn.commit()
    return _row_to_mcp(row) if row else None


async def delete_mcp_server(
    pool: AsyncConnectionPool, empresa_id: int, mcp_id: int
) -> bool:
    async with pool.connection() as conn:
        cur = await conn.execute(
            "DELETE FROM mcp_server WHERE empresa_id = %s AND id = %s",
            (empresa_id, mcp_id),
        )
        await conn.commit()
        return (cur.rowcount or 0) > 0
