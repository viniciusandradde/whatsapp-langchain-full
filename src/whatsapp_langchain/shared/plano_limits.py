"""Sprint Q.2 — helpers de quota por plano.

Centraliza:
- Lookup do plano da empresa (com cache curto)
- Contagem de recursos consumidos por empresa
- Verificação de disponibilidade de quota
- Verificação de features habilitadas

Limites NULL no plano = ilimitado (Enterprise tipicamente).

Performance: cache LRU 30s por (empresa_id) — quota raramente muda em
janela curta. Pra invalidar manualmente: `clear_plano_cache()`.

Padrão de uso:
    # Em handlers FastAPI (via dependency, ver Q.3):
    info = await get_plano_info(pool, empresa_id)
    if info.recurso_passou_limite("conexoes", await count_conexoes(pool, empresa_id)):
        raise HTTPException(402, "Plano free só permite 1 conexão...")
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Final

from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.rls_context import empresa_scope

# Cache TTL — 30s suficiente pra absorver pico de checks num request
# burst, baixo o suficiente pra mudança de plano refletir rápido.
_CACHE_TTL_SECONDS: Final = 30.0

# Cache: empresa_id → (timestamp, PlanoInfo)
_plano_cache: dict[int, tuple[float, PlanoInfo]] = {}


@dataclass
class PlanoInfo:
    """Snapshot de plano + limites + features da empresa."""

    empresa_id: int
    plano_id: int | None
    plano_slug: str
    plano_nome: str
    preco_mensal_brl: float
    limite_usuarios: int | None  # None = ilimitado
    limite_conexoes: int | None
    limite_atendimentos_mes: int | None
    limite_orcamento_ia_usd: float | None
    limite_documentos_kb: int | None
    features: dict[str, bool] = field(default_factory=dict)

    def limite_de(self, recurso: str) -> int | None:
        """Retorna o limite do recurso (None = ilimitado)."""
        mapa = {
            "usuarios": self.limite_usuarios,
            "conexoes": self.limite_conexoes,
            "atendimentos_mes": self.limite_atendimentos_mes,
            "documentos_kb": self.limite_documentos_kb,
        }
        if recurso not in mapa:
            raise ValueError(f"Recurso desconhecido: {recurso}")
        return mapa[recurso]

    def passou_limite(self, recurso: str, usado: int) -> bool:
        """True se `usado` excede o limite do recurso (limite None = nunca)."""
        limite = self.limite_de(recurso)
        if limite is None:
            return False
        return usado >= limite

    def tem_feature(self, feature: str) -> bool:
        """True se o plano tem a feature habilitada."""
        return bool(self.features.get(feature, False))

    def upgrade_sugerido(self) -> str | None:
        """Próximo plano superior pra sugerir ao user."""
        if self.plano_slug == "free":
            return "pro"
        if self.plano_slug == "pro":
            return "enterprise"
        return None


def clear_plano_cache(empresa_id: int | None = None) -> None:
    """Invalida cache de plano. Chamar após upgrade/downgrade."""
    if empresa_id is None:
        _plano_cache.clear()
    else:
        _plano_cache.pop(empresa_id, None)


async def get_plano_info(
    pool: AsyncConnectionPool, empresa_id: int
) -> PlanoInfo:
    """Retorna PlanoInfo da empresa (com cache 30s).

    Sprint A.2: cross-tenant (lê plano sem RLS pq plano não tem
    empresa_id; empresa filtra por id explícito). Bypass por segurança
    se chamado fora de request context.
    """
    cached = _plano_cache.get(empresa_id)
    now = time.monotonic()
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        return cached[1]

    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT e.plano_id, p.slug, p.nome, p.preco_mensal_brl,
                       p.limite_usuarios, p.limite_conexoes,
                       p.limite_atendimentos_mes, p.limite_orcamento_ia_usd,
                       p.limite_documentos_kb, p.features
                  FROM empresa e
                  LEFT JOIN plano p ON p.id = e.plano_id
                 WHERE e.id = %s
                """,
                (empresa_id,),
            )
            row = await cur.fetchone()

    if row is None:
        raise ValueError(f"Empresa {empresa_id} não existe")

    (
        plano_id, slug, nome, preco,
        lim_users, lim_conex, lim_atend, lim_ia, lim_docs, features,
    ) = row
    info = PlanoInfo(
        empresa_id=empresa_id,
        plano_id=plano_id,
        plano_slug=slug or "free",
        plano_nome=nome or "Free",
        preco_mensal_brl=float(preco) if preco is not None else 0.0,
        limite_usuarios=lim_users,
        limite_conexoes=lim_conex,
        limite_atendimentos_mes=lim_atend,
        limite_orcamento_ia_usd=float(lim_ia) if lim_ia is not None else None,
        limite_documentos_kb=lim_docs,
        features=features or {},
    )
    _plano_cache[empresa_id] = (now, info)
    return info


# =====================================================================
# Contadores de recursos consumidos
# =====================================================================


async def count_conexoes(pool: AsyncConnectionPool, empresa_id: int) -> int:
    """Conta conexões ativas (não-disabled) da empresa."""
    with empresa_scope(empresa_id=empresa_id):
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT count(*) FROM conexao "
                "WHERE empresa_id = %s AND status != 'disabled'",
                (empresa_id,),
            )
            row = await cur.fetchone()
    return int(row[0]) if row else 0


async def count_agentes(pool: AsyncConnectionPool, empresa_id: int) -> int:
    """Conta agentes IA ativos da empresa."""
    with empresa_scope(empresa_id=empresa_id):
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT count(*) FROM agente_ia "
                "WHERE empresa_id = %s AND ativo = TRUE",
                (empresa_id,),
            )
            row = await cur.fetchone()
    return int(row[0]) if row else 0


async def count_usuarios(pool: AsyncConnectionPool, empresa_id: int) -> int:
    """Conta usuários (memberships) da empresa."""
    with empresa_scope(empresa_id=empresa_id):
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT count(*) FROM empresa_membro WHERE empresa_id = %s",
                (empresa_id,),
            )
            row = await cur.fetchone()
    return int(row[0]) if row else 0


async def count_atendimentos_mes(pool: AsyncConnectionPool, empresa_id: int) -> int:
    """Conta atendimentos criados no mês corrente (UTC) da empresa.

    Definição: 1 atendimento = 1 row em `atendimento` com `created_at`
    no mês corrente. Reset implícito quando o mês vira (não precisa
    cron — query baseada em data_trunc).
    """
    with empresa_scope(empresa_id=empresa_id):
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT count(*) FROM atendimento
                 WHERE empresa_id = %s
                   AND created_at >= date_trunc('month', NOW())
                """,
                (empresa_id,),
            )
            row = await cur.fetchone()
    return int(row[0]) if row else 0


async def count_documentos_kb(pool: AsyncConnectionPool, empresa_id: int) -> int:
    """Conta documentos na base de conhecimento."""
    with empresa_scope(empresa_id=empresa_id):
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT count(*) FROM documento_conhecimento WHERE empresa_id = %s",
                (empresa_id,),
            )
            row = await cur.fetchone()
    return int(row[0]) if row else 0


# Mapa recurso → função de contagem
_COUNTERS = {
    "conexoes": count_conexoes,
    "agentes": count_agentes,
    "usuarios": count_usuarios,
    "atendimentos_mes": count_atendimentos_mes,
    "documentos_kb": count_documentos_kb,
}


async def count_recurso(
    pool: AsyncConnectionPool, empresa_id: int, recurso: str
) -> int:
    """Despacha pra contador apropriado."""
    if recurso not in _COUNTERS:
        raise ValueError(f"Recurso desconhecido: {recurso}")
    return await _COUNTERS[recurso](pool, empresa_id)


# =====================================================================
# Snapshot completo de uso (pra UI / endpoint /quota)
# =====================================================================


@dataclass
class QuotaSnapshot:
    """Visão completa: plano + limites + usado + percentual."""

    plano: PlanoInfo
    usado: dict[str, int]
    percentual: dict[str, float | None]  # None = ilimitado

    def to_dict(self) -> dict:
        return {
            "plano": {
                "id": self.plano.plano_id,
                "slug": self.plano.plano_slug,
                "nome": self.plano.plano_nome,
                "preco_mensal_brl": self.plano.preco_mensal_brl,
            },
            "limites": {
                "usuarios": self.plano.limite_usuarios,
                "conexoes": self.plano.limite_conexoes,
                "atendimentos_mes": self.plano.limite_atendimentos_mes,
                "documentos_kb": self.plano.limite_documentos_kb,
                "orcamento_ia_usd": self.plano.limite_orcamento_ia_usd,
            },
            "usado": self.usado,
            "percentual": self.percentual,
            "features": self.plano.features,
            "upgrade_sugerido": self.plano.upgrade_sugerido(),
        }


async def get_quota_snapshot(
    pool: AsyncConnectionPool, empresa_id: int
) -> QuotaSnapshot:
    """Lê plano + conta todos os recursos. Custo: ~5 queries paralelas."""
    import asyncio

    plano = await get_plano_info(pool, empresa_id)

    # Conta tudo em paralelo
    recursos = ["conexoes", "agentes", "usuarios", "atendimentos_mes", "documentos_kb"]
    counts = await asyncio.gather(
        *(count_recurso(pool, empresa_id, r) for r in recursos)
    )
    usado = dict(zip(recursos, counts))

    # Calcula percentual (ignora 'agentes' — sem limite ainda na tabela plano)
    percentual: dict[str, float | None] = {}
    for recurso in ("usuarios", "conexoes", "atendimentos_mes", "documentos_kb"):
        limite = plano.limite_de(recurso)
        if limite is None or limite == 0:
            percentual[recurso] = None
        else:
            percentual[recurso] = round(usado[recurso] * 100.0 / limite, 1)

    return QuotaSnapshot(plano=plano, usado=usado, percentual=percentual)
