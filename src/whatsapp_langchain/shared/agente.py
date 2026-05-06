"""CRUD de Agentes IA cadastráveis (Sub-fase A).

Substitui agente_ia_config (mig 014) que era só override pontual. Agora
cada empresa pode ter N agentes; cada conexão WhatsApp aponta pra um
agente via `conexao.default_agent_id` (slug).

Mapping `estilo_resposta` → (temperatura, top_p):
- preciso: 0.1 / 0.6 (mais factual)
- equilibrado: 0.5 / 0.85 (default)
- criativo: 0.9 / 0.95
- muito_criativo: 1.3 / 0.99

`temperatura_override` / `top_p_override` permitem ignorar o preset.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog
from psycopg import errors as pg_errors
from psycopg_pool import AsyncConnectionPool

logger = structlog.get_logger()


# ---- Mapping estilo → (temperatura, top_p) ----

ESTILO_PRESETS: dict[str, tuple[float, float]] = {
    "preciso": (0.1, 0.6),
    "equilibrado": (0.5, 0.85),
    "criativo": (0.9, 0.95),
    "muito_criativo": (1.3, 0.99),
}


def resolve_temperatura_top_p(
    estilo: str,
    temperatura_override: float | None,
    top_p_override: float | None,
) -> tuple[float, float]:
    """Aplica preset + permite override fino."""
    base_temp, base_top_p = ESTILO_PRESETS.get(estilo, (0.5, 0.85))
    return (
        temperatura_override if temperatura_override is not None else base_temp,
        top_p_override if top_p_override is not None else base_top_p,
    )


# ---- Modelo + helpers ----

class DuplicateAgenteError(ValueError):
    """Slug já existe na empresa."""


_COLS = (
    "id, empresa_id, slug, nome, descricao, template_catalog, "
    "prompt_override, modelo, estilo_resposta, temperatura_override, "
    "max_tokens, top_p_override, tools_enabled, tools_config, "
    "aceita_imagem, aceita_audio, aceita_documento, "
    "base_conhecimento_ids, variavel_ids, mcp_server_ids, "
    "limite_custo_acao, ativo, is_default, "
    "created_by_user_id, created_at, updated_at"
)


@dataclass
class AgenteIA:
    id: int
    empresa_id: int
    slug: str
    nome: str
    descricao: str | None
    template_catalog: str
    prompt_override: str | None
    modelo: str | None
    estilo_resposta: str
    temperatura_override: float | None
    max_tokens: int | None
    top_p_override: float | None
    tools_enabled: list[str]
    tools_config: dict
    aceita_imagem: bool
    aceita_audio: bool
    aceita_documento: bool
    base_conhecimento_ids: list[int]
    variavel_ids: list[int]
    mcp_server_ids: list[int]
    limite_custo_acao: str
    ativo: bool
    is_default: bool
    created_by_user_id: str | None
    created_at: Any
    updated_at: Any

    def to_dict(self) -> dict:
        out = {
            "id": self.id,
            "empresa_id": self.empresa_id,
            "slug": self.slug,
            "nome": self.nome,
            "descricao": self.descricao,
            "template_catalog": self.template_catalog,
            "prompt_override": self.prompt_override,
            "modelo": self.modelo,
            "estilo_resposta": self.estilo_resposta,
            "temperatura_override": (
                float(self.temperatura_override)
                if self.temperatura_override is not None
                else None
            ),
            "max_tokens": self.max_tokens,
            "top_p_override": (
                float(self.top_p_override) if self.top_p_override is not None else None
            ),
            "tools_enabled": list(self.tools_enabled or []),
            "tools_config": self.tools_config or {},
            "aceita_imagem": self.aceita_imagem,
            "aceita_audio": self.aceita_audio,
            "aceita_documento": self.aceita_documento,
            "base_conhecimento_ids": list(self.base_conhecimento_ids or []),
            "variavel_ids": list(self.variavel_ids or []),
            "mcp_server_ids": list(self.mcp_server_ids or []),
            "limite_custo_acao": self.limite_custo_acao,
            "ativo": self.ativo,
            "is_default": self.is_default,
            "created_by_user_id": self.created_by_user_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
        # Campos derivados (pra UI mostrar valores efetivos)
        temp, top_p = resolve_temperatura_top_p(
            self.estilo_resposta,
            float(self.temperatura_override) if self.temperatura_override is not None else None,
            float(self.top_p_override) if self.top_p_override is not None else None,
        )
        out["temperatura_efetiva"] = temp
        out["top_p_efetivo"] = top_p
        return out


def _row_to_agente(row) -> AgenteIA:
    return AgenteIA(*row)


# ---- CRUD ----


async def list_agentes(
    pool: AsyncConnectionPool, empresa_id: int, *, only_active: bool = False
) -> list[AgenteIA]:
    where = "empresa_id = %s"
    if only_active:
        where += " AND ativo = TRUE"
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {_COLS} FROM agente_ia WHERE {where} ORDER BY is_default DESC, nome",
            (empresa_id,),
        )
        rows = await cur.fetchall()
    return [_row_to_agente(r) for r in rows]


async def get_agente_by_slug(
    pool: AsyncConnectionPool, empresa_id: int, slug: str
) -> AgenteIA | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {_COLS} FROM agente_ia WHERE empresa_id = %s AND slug = %s",
            (empresa_id, slug),
        )
        row = await cur.fetchone()
    return _row_to_agente(row) if row else None


async def get_agente_by_id(
    pool: AsyncConnectionPool, agente_id: int
) -> AgenteIA | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {_COLS} FROM agente_ia WHERE id = %s",
            (agente_id,),
        )
        row = await cur.fetchone()
    return _row_to_agente(row) if row else None


async def get_default_agente(
    pool: AsyncConnectionPool, empresa_id: int
) -> AgenteIA | None:
    """Retorna o agente default da empresa (uq_agente_ia_default)."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {_COLS} FROM agente_ia "
            "WHERE empresa_id = %s AND is_default = TRUE AND ativo = TRUE LIMIT 1",
            (empresa_id,),
        )
        row = await cur.fetchone()
    return _row_to_agente(row) if row else None


async def create_agente(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    slug: str,
    nome: str,
    template_catalog: str,
    descricao: str | None = None,
    user_id: str | None = None,
) -> AgenteIA:
    """Cria agente mínimo. Detalhes (prompt, tools, etc) editados depois via update."""
    try:
        async with pool.connection() as conn:
            cur = await conn.execute(
                f"""
                INSERT INTO agente_ia
                    (empresa_id, slug, nome, descricao, template_catalog, created_by_user_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING {_COLS}
                """,
                (empresa_id, slug, nome, descricao, template_catalog, user_id),
            )
            row = await cur.fetchone()
            await conn.commit()
    except pg_errors.UniqueViolation as e:
        raise DuplicateAgenteError(
            f"Agente com slug '{slug}' já existe nessa empresa"
        ) from e
    assert row is not None
    return _row_to_agente(row)


async def update_agente(
    pool: AsyncConnectionPool,
    empresa_id: int,
    slug: str,
    **fields: Any,
) -> AgenteIA | None:
    """Atualiza qualquer subset de campos. Bloqueia colunas read-only
    (id, slug, empresa_id, created_at, etc)."""
    READONLY = {"id", "empresa_id", "slug", "created_at", "updated_at",
                "created_by_user_id", "temperatura_efetiva", "top_p_efetivo"}
    sets: list[str] = []
    params: list = []
    for k, v in fields.items():
        if k in READONLY or v is None:
            continue
        # Listas + JSON precisam cast explícito em alguns drivers
        if k in ("tools_enabled", "base_conhecimento_ids", "variavel_ids", "mcp_server_ids"):
            sets.append(f"{k} = %s::text[]" if k == "tools_enabled" else f"{k} = %s::bigint[]")
            params.append(list(v))
        elif k == "tools_config":
            import json
            sets.append("tools_config = %s::jsonb")
            params.append(json.dumps(v))
        else:
            sets.append(f"{k} = %s")
            params.append(v)

    if not sets:
        return await get_agente_by_slug(pool, empresa_id, slug)
    sets.append("updated_at = NOW()")
    params.extend([empresa_id, slug])
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            UPDATE agente_ia SET {", ".join(sets)}
             WHERE empresa_id = %s AND slug = %s
            RETURNING {_COLS}
            """,
            tuple(params),
        )
        row = await cur.fetchone()
        await conn.commit()
    return _row_to_agente(row) if row else None


async def soft_delete_agente(
    pool: AsyncConnectionPool, empresa_id: int, slug: str
) -> bool:
    """Marca como ativo=false. Não DROPa pra preservar atendimentos passados."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            "UPDATE agente_ia SET ativo = FALSE, updated_at = NOW() "
            "WHERE empresa_id = %s AND slug = %s",
            (empresa_id, slug),
        )
        await conn.commit()
        return (cur.rowcount or 0) > 0


async def set_default_agente(
    pool: AsyncConnectionPool, empresa_id: int, slug: str
) -> bool:
    """Promove agente a default da empresa. Limpa default antigo (uq partial)."""
    async with pool.connection() as conn:
        async with conn.transaction():
            # Limpa default atual (não conflita com partial unique)
            await conn.execute(
                "UPDATE agente_ia SET is_default = FALSE WHERE empresa_id = %s AND is_default = TRUE",
                (empresa_id,),
            )
            cur = await conn.execute(
                "UPDATE agente_ia SET is_default = TRUE, updated_at = NOW() "
                "WHERE empresa_id = %s AND slug = %s AND ativo = TRUE",
                (empresa_id, slug),
            )
            return (cur.rowcount or 0) > 0


# ---- Runtime resolution (A.6) ----


@dataclass
class AgenteRuntime:
    """Config efetiva pro loader montar o graph.

    Combina `agente_ia` row + ESTILO_PRESETS resolvidos. `template_catalog`
    indica qual diretório Python carregar; demais campos viram overrides
    aplicados em `build_graph` do template.
    """

    slug: str
    template_catalog: str
    prompt_override: str | None
    modelo: str | None
    temperatura: float
    top_p: float
    max_tokens: int | None
    tools_enabled: list[str]
    base_conhecimento_ids: list[int]

    @classmethod
    def from_agente(cls, agente: AgenteIA) -> AgenteRuntime:
        temp, top_p = resolve_temperatura_top_p(
            agente.estilo_resposta,
            float(agente.temperatura_override)
            if agente.temperatura_override is not None
            else None,
            float(agente.top_p_override)
            if agente.top_p_override is not None
            else None,
        )
        return cls(
            slug=agente.slug,
            template_catalog=agente.template_catalog,
            prompt_override=agente.prompt_override,
            modelo=agente.modelo,
            temperatura=temp,
            top_p=top_p,
            max_tokens=agente.max_tokens,
            tools_enabled=list(agente.tools_enabled or []),
            base_conhecimento_ids=list(agente.base_conhecimento_ids or []),
        )


async def resolve_agente_runtime(
    pool: AsyncConnectionPool, empresa_id: int, slug: str
) -> AgenteRuntime | None:
    """Resolve runtime config pra um slug — multi-agente DB com fallbacks.

    Ordem de resolução:
    1. agente_ia.row(slug) ativo → usa diretamente
    2. agente_ia.row(slug) inativo → cai pro default da empresa
    3. nenhuma row pro slug → retorna None (caller usa caminho legacy)

    Retorna None significa "não tem agente cadastrado em DB pra esse slug —
    use comportamento legacy (catálogo + agente_ia_config)".
    """
    agente = await get_agente_by_slug(pool, empresa_id, slug)
    if agente is not None and agente.ativo:
        return AgenteRuntime.from_agente(agente)
    # Fallback default — útil quando admin desativa o agente atual
    default = await get_default_agente(pool, empresa_id)
    if default is not None:
        return AgenteRuntime.from_agente(default)
    return None
