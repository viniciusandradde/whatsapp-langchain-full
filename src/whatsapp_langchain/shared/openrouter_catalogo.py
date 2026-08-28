"""Catálogo OpenRouter dentro do Nexus (módulo Saúde de IA — mig 178).

Sincroniza o catálogo COMPLETO (provedores + modelos, com benchmarks
Artificial Analysis embutidos) e coleta a série de saúde por endpoint
(uptime, latência p50..p99, throughput) SÓ dos modelos que interessam ao
Nexus — os em uso + os curados. É a base do dashboard, da comparação por
provedor e dos alertas de degradação.

Fatos da API que governam este módulo (provados em 2026-08-25, ver ADR-001 e
docs/ADR-001-roteamento-openrouter.md):
- `/api/v1/providers` e `/api/v1/models` são públicos e oficiais;
- `/api/v1/models/{slug}/endpoints` devolve latência/throughput **somente com
  chave** (sem auth os campos vêm null — não é erro, é omissão silenciosa);
- `GET /api/v1/models/{author}/{slug}` (sem /endpoints) responde 404 — nunca
  usar;
- a API de frontend (`/api/frontend/*`) NÃO é usada aqui de propósito: é
  não-documentada e já mudou de path uma vez.

Escopo de plataforma: tabelas sem empresa_id/RLS (padrão mig 173); as rotas
protegem com `is_superadmin`.
"""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.llm import CURATED_MODELS

if TYPE_CHECKING:
    from psycopg_pool import AsyncConnectionPool

logger = structlog.get_logger()

# Retenção da série de métricas: 90 dias cobre o baseline de alerta (7d) com
# folga de sobra pra investigação histórica, sem deixar a tabela crescer
# pra sempre (6 modelos × ~4 endpoints × 144 ticks/dia ≈ 3,5k rows/dia).
METRICA_RETENCAO_DIAS = 90

_TIMEOUT = 60.0


def _base() -> str:
    return settings.openrouter_base_url.rstrip("/")


def _headers(com_chave: bool) -> dict[str, str]:
    h = {"Content-Type": "application/json"}
    if com_chave and settings.openrouter_api_key:
        h["Authorization"] = f"Bearer {settings.openrouter_api_key.get_secret_value()}"
    return h


async def _get_json(client: httpx.AsyncClient, url: str, *, com_chave: bool) -> Any:
    resp = await client.get(url, headers=_headers(com_chave), timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Feed de novidades por DIFF (mig 181) — o OpenRouter não tem API de notícias
# oficial; o que muda entre syncs É a notícia, e sai auditável.
# ---------------------------------------------------------------------------


def diff_catalogo(
    anterior: dict[str, dict[str, Any]], atuais: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Função PURA: compara o estado gravado com o payload novo e devolve os
    eventos. `anterior` vazio = primeira carga — catálogo inteiro não é
    notícia, devolve [].

    `anterior`: {slug: {prompt, completion, context_length, ativo}}.
    """
    if not anterior:
        return []
    eventos: list[dict[str, Any]] = []
    vistos: set[str] = set()
    for m in atuais:
        slug = m.get("id")
        if not slug:
            continue
        vistos.add(slug)
        pricing = m.get("pricing") or {}
        ant = anterior.get(slug)
        if ant is None:
            eventos.append(
                {
                    "tipo": "modelo_novo",
                    "slug": slug,
                    "detalhe": {
                        "nome": m.get("name") or slug,
                        "prompt": pricing.get("prompt"),
                        "completion": pricing.get("completion"),
                        "context_length": m.get("context_length"),
                    },
                }
            )
            continue
        if not ant.get("ativo", True):
            eventos.append({"tipo": "modelo_voltou", "slug": slug, "detalhe": {}})

        def _f(v: Any) -> float | None:
            try:
                return float(v) if v is not None else None
            except (TypeError, ValueError):
                return None

        p_ant, p_novo = _f(ant.get("prompt")), _f(pricing.get("prompt"))
        c_ant, c_novo = _f(ant.get("completion")), _f(pricing.get("completion"))
        mudou_prompt = p_ant is not None and p_novo is not None and p_novo != p_ant
        mudou_compl = c_ant is not None and c_novo is not None and c_novo != c_ant
        if mudou_prompt or mudou_compl:
            ref_ant, ref_novo = (p_ant, p_novo) if mudou_prompt else (c_ant, c_novo)
            pct = None
            if ref_ant is not None and ref_novo is not None and ref_ant != 0:
                pct = round((ref_novo - ref_ant) * 100 / ref_ant, 1)
            eventos.append(
                {
                    "tipo": "preco_mudou",
                    "slug": slug,
                    "detalhe": {
                        "prompt_antes": ant.get("prompt"),
                        "prompt_depois": pricing.get("prompt"),
                        "completion_antes": ant.get("completion"),
                        "completion_depois": pricing.get("completion"),
                        "pct": pct,
                    },
                }
            )
        ctx_ant, ctx_novo = ant.get("context_length"), m.get("context_length")
        if ctx_ant and ctx_novo and ctx_ant != ctx_novo:
            eventos.append(
                {
                    "tipo": "contexto_mudou",
                    "slug": slug,
                    "detalhe": {"antes": ctx_ant, "depois": ctx_novo},
                }
            )
    for slug, ant in anterior.items():
        if slug not in vistos and ant.get("ativo", True):
            eventos.append({"tipo": "modelo_removido", "slug": slug, "detalhe": {}})
    return eventos


async def _gravar_eventos(conn: Any, eventos: list[dict[str, Any]]) -> None:
    for e in eventos:
        await conn.execute(
            "INSERT INTO openrouter_evento (tipo, modelo_slug, detalhe) "
            "VALUES (%s, %s, %s::jsonb)",
            (e["tipo"], e["slug"], _json(e.get("detalhe") or {})),
        )


# ---------------------------------------------------------------------------
# Sync do catálogo (provedores + modelos) — 1x/dia ou sob demanda pelo botão.
# ---------------------------------------------------------------------------


async def sync_catalogo(pool: AsyncConnectionPool) -> dict[str, int]:
    """Baixa provedores e modelos e faz UPSERT. Retorna contagens.

    Idempotente: rodar duas vezes no mesmo minuto só atualiza `atualizado_em`.
    Erro em um item não derruba o lote (loga e segue) — catálogo parcial é
    melhor que nenhum.
    """
    inicio = time.monotonic()
    async with httpx.AsyncClient() as client:
        provs = (await _get_json(client, f"{_base()}/providers", com_chave=False)).get(
            "data"
        ) or []
        modelos = (await _get_json(client, f"{_base()}/models", com_chave=False)).get(
            "data"
        ) or []

    n_provs = n_modelos = 0
    async with pool.connection() as conn:
        # Estado anterior pro diff de novidades (mig 181) — 388 rows, barato.
        cur = await conn.execute(
            "SELECT slug, pricing->>'prompt', pricing->>'completion', "
            "context_length, ativo FROM openrouter_modelo"
        )
        anterior = {
            str(r[0]): {
                "prompt": r[1],
                "completion": r[2],
                "context_length": r[3],
                "ativo": bool(r[4]),
            }
            for r in await cur.fetchall()
        }
        for p in provs:
            try:
                await conn.execute(
                    """
                    INSERT INTO openrouter_provedor
                        (slug, nome, privacy_policy_url, tos_url,
                         status_page_url, hq, datacenters, atualizado_em)
                    VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, NOW())
                    ON CONFLICT (slug) DO UPDATE SET
                        nome = EXCLUDED.nome,
                        privacy_policy_url = EXCLUDED.privacy_policy_url,
                        tos_url = EXCLUDED.tos_url,
                        status_page_url = EXCLUDED.status_page_url,
                        hq = EXCLUDED.hq,
                        datacenters = EXCLUDED.datacenters,
                        atualizado_em = NOW()
                    """,
                    (
                        p.get("slug"),
                        p.get("name") or p.get("slug"),
                        p.get("privacy_policy_url"),
                        p.get("terms_of_service_url"),
                        p.get("status_page_url"),
                        p.get("headquarters"),
                        _json(p.get("datacenters") or []),
                    ),
                )
                n_provs += 1
            except Exception as exc:  # noqa: BLE001 — item isolado não derruba o lote
                logger.warning(
                    "or_sync_provedor_falhou", slug=p.get("slug"), error=str(exc)[:200]
                )
        for m in modelos:
            try:
                arch = m.get("architecture") or {}
                await conn.execute(
                    """
                    INSERT INTO openrouter_modelo
                        (slug, canonical_slug, nome, descricao, context_length,
                         input_modalities, output_modalities,
                         supported_parameters, pricing, benchmarks,
                         criado_no_or, atualizado_em)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                            %s::jsonb, %s::jsonb, to_timestamp(%s), NOW())
                    ON CONFLICT (slug) DO UPDATE SET
                        canonical_slug = EXCLUDED.canonical_slug,
                        nome = EXCLUDED.nome,
                        descricao = EXCLUDED.descricao,
                        context_length = EXCLUDED.context_length,
                        input_modalities = EXCLUDED.input_modalities,
                        output_modalities = EXCLUDED.output_modalities,
                        supported_parameters = EXCLUDED.supported_parameters,
                        pricing = EXCLUDED.pricing,
                        benchmarks = EXCLUDED.benchmarks,
                        criado_no_or = EXCLUDED.criado_no_or,
                        ativo = TRUE,
                        atualizado_em = NOW()
                    """,
                    (
                        m.get("id"),
                        m.get("canonical_slug"),
                        m.get("name") or m.get("id"),
                        (m.get("description") or "")[:2000] or None,
                        m.get("context_length"),
                        arch.get("input_modalities") or [],
                        arch.get("output_modalities") or [],
                        m.get("supported_parameters") or [],
                        _json(m.get("pricing") or {}),
                        _json(m.get("benchmarks") or {}),
                        m.get("created") or 0,
                    ),
                )
                n_modelos += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "or_sync_modelo_falhou", slug=m.get("id"), error=str(exc)[:200]
                )
        eventos = diff_catalogo(anterior, modelos)
        await _gravar_eventos(conn, eventos)
        removidos = [e["slug"] for e in eventos if e["tipo"] == "modelo_removido"]
        if removidos:
            await conn.execute(
                "UPDATE openrouter_modelo SET ativo = FALSE, "
                "atualizado_em = NOW() WHERE slug = ANY(%s)",
                (removidos,),
            )
        await conn.execute(
            """
            UPDATE openrouter_sync_estado
               SET catalogo_sync_at = NOW(), catalogo_total_modelos = %s,
                   catalogo_total_provs = %s, erro = NULL
             WHERE id = 1
            """,
            (n_modelos, n_provs),
        )
        # Retenção da série: apaga aqui (1x/dia junto do catálogo) — sem cron.
        await conn.execute(
            "DELETE FROM openrouter_endpoint_metrica "
            "WHERE coletado_em < NOW() - make_interval(days => %s)",
            (METRICA_RETENCAO_DIAS,),
        )
        await conn.commit()

    logger.info(
        "or_sync_catalogo_ok",
        provedores=n_provs,
        modelos=n_modelos,
        duracao_ms=int((time.monotonic() - inicio) * 1000),
    )
    return {"provedores": n_provs, "modelos": n_modelos}


def _json(obj: Any) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Modelos que interessam: em uso (settings + agentes) + curados.
# ---------------------------------------------------------------------------


async def modelos_em_uso(
    pool: AsyncConnectionPool, incluir_curados: bool = True
) -> list[str]:
    """Slugs cuja saúde importa ao Nexus, deduplicados e ordenados.

    Em uso de verdade (settings + `agente_ia.modelo` de agentes ativos) vem
    primeiro — são os que dirigem alertas; os curados completam a lista pro
    dashboard comparativo. `incluir_curados=False` devolve só os em uso —
    é o escopo dos alertas (mig 180): modelo curado que ninguém usa não
    acorda ninguém.
    """
    from whatsapp_langchain.shared.rls_context import empresa_scope

    em_uso: list[str] = [
        settings.openrouter_model,
        settings.openrouter_midia_model,
        settings.tts_model,
    ]
    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT DISTINCT modelo FROM agente_ia "
                "WHERE ativo AND modelo IS NOT NULL AND modelo <> ''"
            )
            em_uso.extend(str(r[0]) for r in await cur.fetchall())
    curados = [str(m["id"]) for m in CURATED_MODELS] if incluir_curados else []
    vistos: set[str] = set()
    out: list[str] = []
    for slug in em_uso + curados:
        if slug and slug not in vistos:
            vistos.add(slug)
            out.append(slug)
    return out


# ---------------------------------------------------------------------------
# Coleta de métricas por endpoint (COM chave — latência/throughput).
# ---------------------------------------------------------------------------


async def coletar_metricas(
    pool: AsyncConnectionPool, slugs: list[str] | None = None
) -> int:
    """Snapshot de saúde dos endpoints dos `slugs` (default: modelos_em_uso).

    Uma linha por (modelo, endpoint) por tick. Modelo que o OpenRouter não
    conhece (404) só loga — catálogo curado pode carregar slug aposentado e
    isso não pode calar a coleta dos demais.
    """
    if slugs is None:
        slugs = await modelos_em_uso(pool)
    gravadas = 0
    async with httpx.AsyncClient() as client:
        for slug in slugs:
            try:
                data = (
                    await _get_json(
                        client, f"{_base()}/models/{slug}/endpoints", com_chave=True
                    )
                ).get("data") or {}
            except httpx.HTTPStatusError as exc:
                logger.warning(
                    "or_metricas_modelo_indisponivel",
                    slug=slug,
                    status=exc.response.status_code,
                )
                continue
            except httpx.HTTPError as exc:
                logger.warning("or_metricas_rede", slug=slug, error=str(exc)[:200])
                continue
            endpoints = data.get("endpoints") or []
            async with pool.connection() as conn:
                for e in endpoints:
                    await conn.execute(
                        """
                        INSERT INTO openrouter_endpoint_metrica
                            (modelo_slug, provider_tag, provider_nome,
                             quantization, status, uptime_5m, uptime_30m,
                             uptime_1d, latencia, throughput, pricing)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                                %s::jsonb, %s::jsonb, %s::jsonb)
                        """,
                        (
                            slug,
                            e.get("tag") or e.get("provider_name") or "?",
                            e.get("provider_name") or "?",
                            e.get("quantization"),
                            str(e.get("status"))
                            if e.get("status") is not None
                            else None,
                            e.get("uptime_last_5m"),
                            e.get("uptime_last_30m"),
                            e.get("uptime_last_1d"),
                            _json(e.get("latency_last_30m") or {}),
                            _json(e.get("throughput_last_30m") or {}),
                            _json(e.get("pricing") or {}),
                        ),
                    )
                    gravadas += 1
                await conn.commit()
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE openrouter_sync_estado SET metricas_sync_at = NOW() WHERE id = 1"
        )
        await conn.commit()
    logger.info("or_metricas_ok", modelos=len(slugs), linhas=gravadas)
    return gravadas


# ---------------------------------------------------------------------------
# Rankings diários (GET /datasets/rankings-daily — COM chave; mig 179).
# ---------------------------------------------------------------------------

# O permaslug do dataset vem DATADO (deepseek/deepseek-v4-flash-20260731);
# a base sem o -YYYYMMDD é o que casa com openrouter_modelo e com o curado.
# A data vem ANTES da variante quando há uma (minimax-m3-20260531:free →
# minimax/minimax-m3:free) — visto nos dados reais em 2026-08-28.
_SUFIXO_VERSAO = re.compile(r"-\d{8}(?=$|:)")


def _slug_base(permaslug: str) -> str:
    return _SUFIXO_VERSAO.sub("", permaslug)


async def sync_rankings(pool: AsyncConnectionPool) -> int:
    """Baixa o dataset de rankings (tokens/dia, ~51 modelos × 30 dias) e faz
    UPSERT. A janela da API é móvel; a tabela local ACUMULA — sem retenção de
    propósito (51 rows/dia ≈ 18k/ano, e histórico além de 30d é o valor).
    """
    async with httpx.AsyncClient() as client:
        rows = (
            await _get_json(
                client, f"{_base()}/datasets/rankings-daily", com_chave=True
            )
        ).get("data") or []
    gravadas = 0
    async with pool.connection() as conn:
        for r in rows:
            try:
                permaslug = str(r["model_permaslug"])
                await conn.execute(
                    """
                    INSERT INTO openrouter_ranking_diario
                        (data, model_permaslug, slug, total_tokens, coletado_em)
                    VALUES (%s, %s, %s, %s, NOW())
                    ON CONFLICT (data, model_permaslug) DO UPDATE SET
                        slug = EXCLUDED.slug,
                        total_tokens = EXCLUDED.total_tokens,
                        coletado_em = NOW()
                    """,
                    (
                        r["date"],
                        permaslug,
                        _slug_base(permaslug),
                        int(r["total_tokens"]),
                    ),
                )
                gravadas += 1
            except Exception as exc:  # noqa: BLE001 — item isolado não derruba o lote
                logger.warning(
                    "or_sync_ranking_falhou", row=str(r)[:120], error=str(exc)[:200]
                )
        # Eventos de top 20 (mig 181): quem entrou/saiu entre o último dia e
        # o anterior. Determinístico dos DADOS (não do momento do sync) — o
        # NOT EXISTS por dia torna o re-run idempotente.
        await conn.execute(
            """
            WITH dias AS (
              SELECT max(data) AS hoje,
                     (SELECT max(data) FROM openrouter_ranking_diario
                       WHERE data < (SELECT max(data)
                                       FROM openrouter_ranking_diario)) AS ontem
                FROM openrouter_ranking_diario
            ), por_slug AS (
              SELECT r.slug, r.data, sum(r.total_tokens) AS tokens
                FROM openrouter_ranking_diario r, dias d
               WHERE r.data IN (d.hoje, d.ontem) AND r.slug <> 'other'
               GROUP BY r.slug, r.data
            ), ranked AS (
              SELECT slug, data,
                     rank() OVER (PARTITION BY data ORDER BY tokens DESC) AS pos
                FROM por_slug
            ), hoje AS (
              SELECT slug, pos FROM ranked, dias WHERE data = hoje AND pos <= 20
            ), ontem AS (
              SELECT slug, pos FROM ranked, dias WHERE data = ontem AND pos <= 20
            ), mudancas AS (
              SELECT 'entrou_top' AS tipo, h.slug, h.pos
                FROM hoje h LEFT JOIN ontem o USING (slug)
               WHERE o.slug IS NULL AND (SELECT ontem FROM dias) IS NOT NULL
              UNION ALL
              SELECT 'saiu_top', o.slug, o.pos
                FROM ontem o LEFT JOIN hoje h USING (slug)
               WHERE h.slug IS NULL
            )
            INSERT INTO openrouter_evento (tipo, modelo_slug, detalhe)
            SELECT m.tipo, m.slug,
                   jsonb_build_object('pos', m.pos,
                                      'dia', (SELECT hoje::text FROM dias))
              FROM mudancas m
             WHERE NOT EXISTS (
               SELECT 1 FROM openrouter_evento e
                WHERE e.tipo = m.tipo AND e.modelo_slug = m.slug
                  AND e.detalhe->>'dia' = (SELECT hoje::text FROM dias)
             )
            """
        )
        await conn.execute(
            "UPDATE openrouter_sync_estado SET rankings_sync_at = NOW() WHERE id = 1"
        )
        await conn.commit()
    logger.info("or_sync_rankings_ok", linhas=gravadas)
    return gravadas


# ---------------------------------------------------------------------------
# Claim do sync diário (padrão resumo_diario) + entrypoint do loop do worker.
# ---------------------------------------------------------------------------


async def _claim_catalogo_hoje(pool: AsyncConnectionPool) -> bool:
    """True = este worker ganhou o direito de sincronizar o catálogo hoje."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            UPDATE openrouter_sync_estado
               SET catalogo_sync_date = CURRENT_DATE
             WHERE id = 1
               AND (catalogo_sync_date IS NULL
                    OR catalogo_sync_date < CURRENT_DATE)
            """
        )
        await conn.commit()
        return bool(cur.rowcount)


async def _claim_rankings_hoje(pool: AsyncConnectionPool) -> bool:
    """True = este worker ganhou o direito de sincronizar os rankings hoje."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            UPDATE openrouter_sync_estado
               SET rankings_sync_date = CURRENT_DATE
             WHERE id = 1
               AND (rankings_sync_date IS NULL
                    OR rankings_sync_date < CURRENT_DATE)
            """
        )
        await conn.commit()
        return bool(cur.rowcount)


async def run_openrouter_sync(pool: AsyncConnectionPool) -> None:
    """Um tick do loop: métricas sempre; catálogo e rankings 1x/dia (claims
    independentes — falha num não segura o outro)."""
    if await _claim_catalogo_hoje(pool):
        try:
            await sync_catalogo(pool)
        except Exception as exc:  # noqa: BLE001 — devolve o dia pra retentar no próximo tick
            logger.warning("or_sync_catalogo_falhou", error=str(exc)[:300])
            async with pool.connection() as conn:
                await conn.execute(
                    "UPDATE openrouter_sync_estado "
                    "SET catalogo_sync_date = NULL, erro = %s WHERE id = 1",
                    (str(exc)[:500],),
                )
                await conn.commit()
    if await _claim_rankings_hoje(pool):
        try:
            await sync_rankings(pool)
        except Exception as exc:  # noqa: BLE001 — devolve o dia pra retentar no próximo tick
            logger.warning("or_sync_rankings_falhou", error=str(exc)[:300])
            async with pool.connection() as conn:
                await conn.execute(
                    "UPDATE openrouter_sync_estado "
                    "SET rankings_sync_date = NULL WHERE id = 1"
                )
                await conn.commit()
    await coletar_metricas(pool)
    # F4 (mig 180): a avaliação roda TODO tick, logo depois da coleta —
    # é ela que abre/resolve episódios e aciona WhatsApp/Telegram/banner.
    from whatsapp_langchain.shared.ia_alertas import avaliar_alertas

    try:
        await avaliar_alertas(pool)
    except Exception as exc:  # noqa: BLE001 — alerta não pode derrubar o sync
        logger.warning("ia_alertas_falhou", error=str(exc)[:300])
