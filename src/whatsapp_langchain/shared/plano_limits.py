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
from datetime import UTC, date, datetime
from typing import Any, Final, LiteralString

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.rls_context import empresa_scope

logger = structlog.get_logger()

# Cache TTL — 30s suficiente pra absorver pico de checks num request
# burst, baixo o suficiente pra mudança de plano refletir rápido.
_CACHE_TTL_SECONDS: Final = 30.0

# Cache: empresa_id → (timestamp, PlanoInfo)
_plano_cache: dict[int, tuple[float, PlanoInfo]] = {}


# Recursos contáveis cujo teto mora em `plano.features` (mig 192), não em coluna.
LIMITES_EM_FEATURES: Final = {
    "departamentos": "departamentos_max",
    "workflows": "workflows_max",
    "menus": "menus_max",
}


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
    # ADR-005 leva A (mig 189). Fica depois de `features` (com default) para
    # não quebrar quem constrói PlanoInfo posicionalmente nos testes.
    limite_agentes: int | None = None
    # ADR-005 leva E (mig 193): último dia (inclusive) do plano pago; None =
    # sem vencimento.
    plano_valido_ate: date | None = None

    def limite_de(self, recurso: str) -> int | None:
        """Retorna o limite do recurso (None = ilimitado)."""
        mapa = {
            "usuarios": self.limite_usuarios,
            "conexoes": self.limite_conexoes,
            "atendimentos_mes": self.limite_atendimentos_mes,
            "documentos_kb": self.limite_documentos_kb,
            "agentes": self.limite_agentes,
        }
        if recurso in mapa:
            return mapa[recurso]
        if recurso in LIMITES_EM_FEATURES:
            return self.limite_numerico(LIMITES_EM_FEATURES[recurso])
        raise ValueError(f"Recurso desconhecido: {recurso}")

    def limite_numerico(self, chave: str) -> int | None:
        """Teto guardado em `features` (ADR-005 leva C2, mig 192): JSON `null`
        = ilimitado; chave AUSENTE = 0 (errar para o lado barato, como
        `contexto_max`); valor não numérico = 0 também."""
        if chave not in self.features:
            return 0
        valor = self.features.get(chave)
        if valor is None:
            return None
        try:
            return int(valor) if not isinstance(valor, bool) else 0
        except (TypeError, ValueError):
            return 0

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
        if self.plano_slug in ("free", "pessoal"):
            return "pro"
        if self.plano_slug == "pro":
            return "enterprise"
        return None

    # ---- Contexto e modelos (mig 188, ADR-004) ----

    @property
    def contexto_max(self) -> str:
        """Maior tier de contexto que o plano libera (`lite` se a chave faltar)."""
        from whatsapp_langchain.shared.contexto import tier_maximo_de

        return tier_maximo_de(self.features)

    @property
    def modelos_premium(self) -> bool:
        return self.tem_feature("modelos_premium")


def resumo_para_painel(plano: PlanoInfo) -> dict[str, Any]:
    """O que o painel precisa para mostrar cadeados e o `/billing` (ADR-005
    leva D): plano JÁ mesclado com as exceções por empresa (`plano.<chave>`),
    para que a tela trave exatamente o que a rota trava — nem mais, nem menos.
    `limites` traz None = ilimitado, no mesmo contrato de `limite_de`."""
    return {
        "empresa_id": plano.empresa_id,
        "slug": plano.plano_slug,
        "nome": plano.plano_nome,
        "preco_mensal_brl": plano.preco_mensal_brl,
        "features": dict(plano.features),
        "limites": {
            "usuarios": plano.limite_usuarios,
            "conexoes": plano.limite_conexoes,
            "atendimentos_mes": plano.limite_atendimentos_mes,
            "documentos_kb": plano.limite_documentos_kb,
            "agentes": plano.limite_agentes,
            "orcamento_ia_usd": plano.limite_orcamento_ia_usd,
            **{
                recurso: plano.limite_numerico(chave)
                for recurso, chave in LIMITES_EM_FEATURES.items()
            },
        },
        "upgrade_sugerido": plano.upgrade_sugerido(),
        # Vigência (leva E): o banner do painel lê daqui, sem fetch novo.
        "valido_ate": plano.plano_valido_ate.isoformat()
        if plano.plano_valido_ate
        else None,
        "dias_para_vencer": _dias_para_vencer(plano.plano_valido_ate),
        "carencia_dias": 5,
    }


def _dias_para_vencer(valido_ate: date | None) -> int | None:
    if valido_ate is None:
        return None
    from whatsapp_langchain.shared.plano_vigencia import TZ_PADRAO, hoje_local

    return (valido_ate - hoje_local(TZ_PADRAO, datetime.now(UTC))).days


def clear_plano_cache(empresa_id: int | None = None) -> None:
    """Invalida cache de plano. Chamar após upgrade/downgrade."""
    if empresa_id is None:
        _plano_cache.clear()
    else:
        _plano_cache.pop(empresa_id, None)


async def get_plano_info(pool: AsyncConnectionPool, empresa_id: int) -> PlanoInfo:
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
                       p.limite_documentos_kb, p.features, p.limite_agentes,
                       e.plano_valido_ate
                  FROM empresa e
                  LEFT JOIN plano p ON p.id = e.plano_id
                 WHERE e.id = %s
                """,
                (empresa_id,),
            )
            row = await cur.fetchone()
            # Grandfathering (ADR-005 D3): exceção por empresa em
            # `feature_flag` com chave `plano.<nome>` sobrepõe o plano.
            cur = await conn.execute(
                """
                SELECT key, value FROM feature_flag
                 WHERE empresa_id = %s AND ativo AND key LIKE 'plano.%%'
                """,
                (empresa_id,),
            )
            excecoes = {k[len("plano.") :]: v for k, v in await cur.fetchall()}

    if row is None:
        raise ValueError(f"Empresa {empresa_id} não existe")

    (
        plano_id,
        slug,
        nome,
        preco,
        lim_users,
        lim_conex,
        lim_atend,
        lim_ia,
        lim_docs,
        features,
        lim_agentes,
        valido_ate,
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
        limite_agentes=lim_agentes,
        plano_valido_ate=valido_ate,
    )
    aplicar_excecoes(info, excecoes)
    _plano_cache[empresa_id] = (now, info)
    return info


# Colunas numéricas de `plano` que uma flag `plano.limite_*` pode sobrepor.
_LIMITES_SOBREPONIVEIS: Final = frozenset(
    {
        "limite_usuarios",
        "limite_conexoes",
        "limite_atendimentos_mes",
        "limite_orcamento_ia_usd",
        "limite_documentos_kb",
        "limite_agentes",
    }
)


def aplicar_excecoes(info: PlanoInfo, excecoes: dict[str, object]) -> None:
    """Sobrepõe o plano com as flags `plano.<nome>` da empresa (ADR-005 D3).

    `plano.limite_*` mexe na coluna numérica (JSON `null` = ilimitado, como
    NULL na tabela; texto numérico vale, o resto é ignorado com log — a tela
    de flags aceita qualquer JSON). Qualquer outra chave vira entrada de
    `features` com o valor que estiver na flag. Muta `info` no lugar.
    """
    for chave, valor in excecoes.items():
        if chave in _LIMITES_SOBREPONIVEIS:
            if valor is None:
                setattr(info, chave, None)
                continue
            try:
                if isinstance(valor, bool):
                    raise TypeError("bool não é limite")
                numero = float(valor)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                logger.warning(
                    "plano_excecao_ignorada",
                    empresa_id=info.empresa_id,
                    chave=chave,
                    valor=valor,
                )
                continue
            if chave == "limite_orcamento_ia_usd":
                info.limite_orcamento_ia_usd = numero
            else:
                setattr(info, chave, int(numero))
        elif chave:
            info.features[chave] = valor  # type: ignore[assignment]


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
                "SELECT count(*) FROM agente_ia WHERE empresa_id = %s AND ativo = TRUE",
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


async def _count_simples(
    pool: AsyncConnectionPool, empresa_id: int, sql: LiteralString
) -> int:
    with empresa_scope(empresa_id=empresa_id):
        async with pool.connection() as conn:
            cur = await conn.execute(sql, (empresa_id,))
            row = await cur.fetchone()
    return int(row[0]) if row else 0


async def count_departamentos(pool: AsyncConnectionPool, empresa_id: int) -> int:
    return await _count_simples(
        pool, empresa_id, "SELECT count(*) FROM departamento WHERE empresa_id = %s"
    )


async def count_workflows(pool: AsyncConnectionPool, empresa_id: int) -> int:
    """Só workflows ATIVOS contam (o teto é de automação rodando, não de rascunho)."""
    return await _count_simples(
        pool,
        empresa_id,
        "SELECT count(*) FROM workflow_chatbot WHERE empresa_id = %s AND ativo",
    )


async def count_menus(pool: AsyncConnectionPool, empresa_id: int) -> int:
    return await _count_simples(
        pool, empresa_id, "SELECT count(*) FROM menu_chatbot WHERE empresa_id = %s"
    )


# Mapa recurso → função de contagem
_COUNTERS = {
    "conexoes": count_conexoes,
    "agentes": count_agentes,
    "usuarios": count_usuarios,
    "atendimentos_mes": count_atendimentos_mes,
    "documentos_kb": count_documentos_kb,
    "departamentos": count_departamentos,
    "workflows": count_workflows,
    "menus": count_menus,
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
                "agentes": self.plano.limite_agentes,
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

    # `agentes` ganhou limite na mig 189 (ADR-005 leva A)
    percentual: dict[str, float | None] = {}
    for recurso in (
        "usuarios",
        "conexoes",
        "atendimentos_mes",
        "documentos_kb",
        "agentes",
    ):
        limite = plano.limite_de(recurso)
        if limite is None or limite == 0:
            percentual[recurso] = None
        else:
            percentual[recurso] = round(usado[recurso] * 100.0 / limite, 1)

    return QuotaSnapshot(plano=plano, usado=usado, percentual=percentual)
