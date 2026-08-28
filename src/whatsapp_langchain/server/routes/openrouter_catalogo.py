"""Catálogo OpenRouter — rotas do módulo Saúde de IA (mig 178, Fatia 1).

Recurso de PLATAFORMA, não de tenant: o catálogo fala do ecossistema de
modelos inteiro. Por isso o gate é `is_superadmin` e NÃO uma permissão do
catálogo RBAC — permissão de catálogo é concedida ao perfil Admin de todo
tenant, o que abriria a tela para os clientes (mesmo racional documentado em
`relatorio_producao.py`, mig 173).

O catálogo completo é só observabilidade (decisão do dono, 2026-08-25): a
seleção pelas empresas continua na lista curada (`modelo_llm`); daqui um
modelo só chega lá pela promoção explícita (`POST /{slug}/promover`).
"""

from __future__ import annotations

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from whatsapp_langchain.server.dependencies import (
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.shared.audit import record_audit
from whatsapp_langchain.shared.catalogo import (
    create_modelo_llm,
    list_modelos_llm,
    update_modelo_llm,
)
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.empresa import is_superadmin
from whatsapp_langchain.shared.openrouter_catalogo import (
    coletar_metricas,
    sync_catalogo,
)
from whatsapp_langchain.shared.rls_context import empresa_scope

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/openrouter",
    tags=["openrouter-catalogo"],
    dependencies=[Depends(verify_service_token)],
)


async def _exigir_superadmin(user_id: str) -> None:
    pool = await get_pool()
    if not await is_superadmin(pool, user_id):
        raise HTTPException(status_code=403, detail="Apenas superadmins.")


@router.get("/status")
async def status_endpoint(
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    """Carimbo do último sync — o painel mostra 'sincronizado há X'."""
    await _exigir_superadmin(user_id)
    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT catalogo_sync_at, catalogo_total_modelos,
                   catalogo_total_provs, metricas_sync_at, erro
              FROM openrouter_sync_estado WHERE id = 1
            """
        )
        row = await cur.fetchone()
    if not row:
        return {"catalogo_sync_at": None}
    return {
        "catalogo_sync_at": row[0].isoformat() if row[0] else None,
        "total_modelos": row[1],
        "total_provedores": row[2],
        "metricas_sync_at": row[3].isoformat() if row[3] else None,
        "erro": row[4],
    }


@router.get("/provedores")
async def listar_provedores(
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    await _exigir_superadmin(user_id)
    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT slug, nome, privacy_policy_url, tos_url, status_page_url,
                   hq, datacenters, atualizado_em
              FROM openrouter_provedor ORDER BY nome
            """
        )
        rows = await cur.fetchall()
    return {
        "items": [
            {
                "slug": r[0],
                "nome": r[1],
                "privacy_policy_url": r[2],
                "tos_url": r[3],
                "status_page_url": r[4],
                "hq": r[5],
                "datacenters": r[6],
                "atualizado_em": r[7].isoformat() if r[7] else None,
            }
            for r in rows
        ]
    }


@router.get("/modelos")
async def listar_modelos(
    q: str | None = None,
    modalidade: str | None = None,
    limit: int = 500,
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    """Catálogo sincronizado, com filtro de busca e modalidade de entrada.

    `promovido` diz se o slug já existe no catálogo curado global — a UI
    troca o botão "Promover" por um selo.
    """
    await _exigir_superadmin(user_id)
    limit = max(1, min(limit, 1000))
    pool = await get_pool()
    where = "TRUE"
    params: list = []
    if q:
        where += " AND (m.slug ILIKE %s OR m.nome ILIKE %s)"
        params.extend([f"%{q}%", f"%{q}%"])
    if modalidade:
        where += " AND %s = ANY(m.input_modalities)"
        params.append(modalidade)
    params.append(limit)
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT m.slug, m.nome, m.context_length, m.input_modalities,
                   m.output_modalities, m.pricing, m.benchmarks,
                   m.criado_no_or, m.atualizado_em,
                   EXISTS (
                     SELECT 1 FROM modelo_llm ml
                      WHERE ml.empresa_id IS NULL
                        AND ml.provedor || '/' || ml.nome = m.slug
                   ) AS promovido
              FROM openrouter_modelo m
             WHERE {where}
             ORDER BY m.slug
             LIMIT %s
            """,
            tuple(params),
        )
        rows = await cur.fetchall()
    return {
        "items": [
            {
                "slug": r[0],
                "nome": r[1],
                "context_length": r[2],
                "input_modalities": r[3],
                "output_modalities": r[4],
                "pricing": r[5],
                "benchmarks": r[6],
                "criado_no_or": r[7].isoformat() if r[7] else None,
                "atualizado_em": r[8].isoformat() if r[8] else None,
                "promovido": bool(r[9]),
            }
            for r in rows
        ]
    }


@router.get("/modelos/{author}/{slug}/metricas")
async def metricas_modelo(
    author: str,
    slug: str,
    horas: int = 24,
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    """Série de saúde por endpoint do modelo (uptime/latência/throughput)."""
    await _exigir_superadmin(user_id)
    horas = max(1, min(horas, 24 * 90))
    modelo_slug = f"{author}/{slug}"
    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT provider_tag, provider_nome, quantization, status,
                   uptime_5m, uptime_30m, uptime_1d, latencia, throughput,
                   pricing, coletado_em
              FROM openrouter_endpoint_metrica
             WHERE modelo_slug = %s
               AND coletado_em > NOW() - make_interval(hours => %s)
             ORDER BY coletado_em DESC
            """,
            (modelo_slug, horas),
        )
        rows = await cur.fetchall()
    return {
        "modelo": modelo_slug,
        "items": [
            {
                "provider_tag": r[0],
                "provider_nome": r[1],
                "quantization": r[2],
                "status": r[3],
                "uptime_5m": float(r[4]) if r[4] is not None else None,
                "uptime_30m": float(r[5]) if r[5] is not None else None,
                "uptime_1d": float(r[6]) if r[6] is not None else None,
                "latencia": r[7],
                "throughput": r[8],
                "pricing": r[9],
                "coletado_em": r[10].isoformat(),
            }
            for r in rows
        ],
    }


@router.get("/saude")
async def saude_funcoes(
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    """Visão geral do Saúde de IA (F3): as 4 funções do Nexus com o modelo
    REALMENTE em uso, cruzando o OpenRouter (uptime/latência do último
    snapshot) com a NOSSA operação (`ia_execucao`, 24h).

    Plataforma inteira, não tenant — por isso o bypass de RLS (rota já é
    superadmin-only).
    """
    await _exigir_superadmin(user_id)
    pool = await get_pool()
    from whatsapp_langchain.shared.config import settings
    from whatsapp_langchain.shared.rls_context import empresa_scope

    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT DISTINCT modelo FROM agente_ia "
                "WHERE ativo AND modelo IS NOT NULL AND modelo <> ''"
            )
            modelos_agentes = [str(r[0]) for r in await cur.fetchall()]

    # As 4 funções e quem as serve de fato. Documentos = OCR usa o modelo de
    # mídia; PDF/DOCX/XLSX são extraídos localmente sem LLM (mig 164).
    funcoes = [
        {
            "funcao": "texto",
            "modelos": sorted({*modelos_agentes, settings.openrouter_model}),
        },
        {"funcao": "imagem", "modelos": [settings.openrouter_midia_model]},
        {
            "funcao": "audio",
            "modelos": sorted({settings.openrouter_midia_model, settings.tts_model}),
        },
        {"funcao": "documentos", "modelos": [settings.openrouter_midia_model]},
    ]

    todos = sorted({m for f in funcoes for m in f["modelos"]})
    saude: dict[str, dict] = {}
    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            for slug in todos:
                provedor, _, nome = slug.partition("/")
                # OpenRouter: melhor uptime e menor p50 entre os endpoints do
                # último snapshot (o roteador escolhe o melhor caminho).
                cur = await conn.execute(
                    """
                    SELECT max(uptime_30m),
                           min((latencia->>'p50')::numeric),
                           count(*)
                      FROM (
                        SELECT DISTINCT ON (provider_tag)
                               uptime_30m, latencia
                          FROM openrouter_endpoint_metrica
                         WHERE modelo_slug = %s
                           AND coletado_em > NOW() - interval '2 hours'
                         ORDER BY provider_tag, coletado_em DESC
                      ) ult
                    """,
                    (slug,),
                )
                orow = await cur.fetchone()
                # Nossa operação, 24h.
                cur = await conn.execute(
                    """
                    SELECT count(*),
                           count(*) FILTER (WHERE status <> 'success'),
                           percentile_cont(0.5)
                             WITHIN GROUP (ORDER BY duracao_ms),
                           coalesce(sum(custo_total), 0)
                      FROM ia_execucao
                     WHERE modelo_provedor = %s AND modelo_nome = %s
                       AND created_at > NOW() - interval '24 hours'
                    """,
                    (provedor, nome),
                )
                nrow = await cur.fetchone()
                saude[slug] = {
                    "uptime_30m": float(orow[0])
                    if orow and orow[0] is not None
                    else None,
                    "latencia_p50_ms": float(orow[1])
                    if orow and orow[1] is not None
                    else None,
                    "endpoints": int(orow[2]) if orow else 0,
                    "chamadas_24h": int(nrow[0]) if nrow else 0,
                    "erros_24h": int(nrow[1]) if nrow else 0,
                    "nossa_p50_ms": float(nrow[2])
                    if nrow and nrow[2] is not None
                    else None,
                    "custo_24h_usd": float(nrow[3]) if nrow else 0.0,
                }

    return {"funcoes": funcoes, "saude": saude}


@router.get("/modelos/{author}/{slug}/analise")
async def analise_modelo(
    author: str,
    slug: str,
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    """Ficha de análise do modelo pro construtor de agente e pra página de
    comparação: dados do catálogo + o ÚLTIMO snapshot de cada endpoint.

    Modelo fora da lista coletada (só ~25 têm coleta periódica) ganha snapshot
    NA HORA via `coletar_metricas` — a análise nasce sob demanda e o modelo
    passa a ter histórico dali em diante.
    """
    await _exigir_superadmin(user_id)
    modelo_slug = f"{author}/{slug}"
    pool = await get_pool()

    async def _snapshot() -> list[tuple]:
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT DISTINCT ON (provider_tag)
                       provider_tag, provider_nome, quantization, status,
                       uptime_5m, uptime_30m, uptime_1d, latencia, throughput,
                       pricing, coletado_em
                  FROM openrouter_endpoint_metrica
                 WHERE modelo_slug = %s
                   AND coletado_em > NOW() - interval '2 hours'
                 ORDER BY provider_tag, coletado_em DESC
                """,
                (modelo_slug,),
            )
            return await cur.fetchall()

    rows = await _snapshot()
    coletado_agora = False
    if not rows:
        await coletar_metricas(pool, [modelo_slug])
        rows = await _snapshot()
        coletado_agora = True

    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT nome, descricao, context_length, input_modalities,
                   output_modalities, pricing, benchmarks, supported_parameters
              FROM openrouter_modelo WHERE slug = %s
            """,
            (modelo_slug,),
        )
        m = await cur.fetchone()
    if m is None and not rows:
        raise HTTPException(
            status_code=404,
            detail="Modelo não está no catálogo sincronizado nem respondeu "
            "no OpenRouter. Rode o sync e confira o slug.",
        )

    return {
        "modelo": modelo_slug,
        "coletado_agora": coletado_agora,
        "catalogo": (
            {
                "nome": m[0],
                "descricao": m[1],
                "context_length": m[2],
                "input_modalities": m[3],
                "output_modalities": m[4],
                "pricing": m[5],
                "benchmarks": m[6],
                "supported_parameters": m[7],
            }
            if m
            else None
        ),
        "endpoints": [
            {
                "provider_tag": r[0],
                "provider_nome": r[1],
                "quantization": r[2],
                "status": r[3],
                "uptime_5m": float(r[4]) if r[4] is not None else None,
                "uptime_30m": float(r[5]) if r[5] is not None else None,
                "uptime_1d": float(r[6]) if r[6] is not None else None,
                "latencia": r[7],
                "throughput": r[8],
                "pricing": r[9],
                "coletado_em": r[10].isoformat(),
            }
            for r in rows
        ],
    }


@router.post("/sync", status_code=202)
async def sync_endpoint(
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    """Dispara sync do catálogo + coleta de métricas em background.

    202 de propósito: o sync completo leva ~10s (2 chamadas grandes + ~500
    UPSERTs) e o botão do painel não deve segurar a request.
    """
    await _exigir_superadmin(user_id)
    pool = await get_pool()

    async def _rodar() -> None:
        try:
            await sync_catalogo(pool)
            await coletar_metricas(pool)
        except Exception as exc:  # noqa: BLE001 — background: registra e o /status expõe
            logger.warning("or_sync_manual_falhou", error=str(exc)[:300])
            async with pool.connection() as conn:
                await conn.execute(
                    "UPDATE openrouter_sync_estado SET erro = %s WHERE id = 1",
                    (str(exc)[:500],),
                )
                await conn.commit()

    background_tasks.add_task(_rodar)
    return {"status": "processando"}


class PromoverInput(BaseModel):
    tipo: str = Field(default="chat", pattern="^(chat|embedding|midia|audio|imagem)$")


@router.post("/modelos/{author}/{slug}/promover", status_code=201)
async def promover_modelo(
    author: str,
    slug: str,
    body: PromoverInput,
    request: Request,
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    """Promove um modelo do catálogo sincronizado ao curado (`modelo_llm`).

    Preços entram do `pricing` do OpenRouter — que vem em USD **por token**;
    o catálogo curado guarda USD por MILHÃO de tokens, daí o ×1e6. Slug já
    promovido vira update de preços, não duplicata.
    """
    await _exigir_superadmin(user_id)
    modelo_slug = f"{author}/{slug}"
    pool = await get_pool()
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT nome, pricing, context_length FROM openrouter_modelo "
            "WHERE slug = %s",
            (modelo_slug,),
        )
        row = await cur.fetchone()
    if not row:
        raise HTTPException(
            status_code=404,
            detail="Modelo não está no catálogo sincronizado. Rode o sync antes.",
        )
    nome_exibicao, pricing, context_length = row[0], row[1] or {}, row[2]

    def _mtok(chave: str) -> float | None:
        v = pricing.get(chave)
        try:
            return round(float(v) * 1_000_000, 4) if v is not None else None
        except (TypeError, ValueError):
            return None

    custo_in = _mtok("prompt")
    custo_out = _mtok("completion")
    custo_cache = _mtok("input_cache_read")

    # `provedor/nome` do curado = slug exato do OpenRouter (contrato mig 138).
    #
    # Escrever linha GLOBAL (empresa_id NULL) exige bypass: o WITH CHECK da
    # mig 136 é estrito no tenant de propósito (tenant não cria global) — o
    # mesmo motivo pelo qual o seed do versionamento de prompt precisou de
    # bypass. Rota já é superadmin-only, então o bypass não fura RBAC.
    provedor, _, nome = modelo_slug.partition("/")
    with empresa_scope(None, bypass=True):
        existentes = await list_modelos_llm(pool, 0, only_active=False)
        ja = next(
            (
                m
                for m in existentes
                if m.empresa_id is None and f"{m.provedor}/{m.nome}" == modelo_slug
            ),
            None,
        )
        if ja is not None:
            out = await update_modelo_llm(
                pool,
                ja.id,
                custo_input_mtok=custo_in,
                custo_output_mtok=custo_out,
                custo_cache_mtok=custo_cache,
                janela_contexto=context_length,
                ativo=True,
            )
            acao = "modelo_llm.promover_update"
        else:
            out = await create_modelo_llm(
                pool,
                empresa_id=None,
                provedor=provedor,
                nome=nome,
                tipo=body.tipo,
                descricao=nome_exibicao,
                custo_input_mtok=custo_in,
                custo_output_mtok=custo_out,
                custo_cache_mtok=custo_cache,
                janela_contexto=context_length,
            )
            acao = "modelo_llm.promover"
        assert out is not None
        # audit_log.empresa_id é NOT NULL — ação de plataforma entra na
        # empresa 1 (VSA, dona da plataforma), padrão dos atos de superadmin.
        await record_audit(
            pool,
            empresa_id=1,
            user_id=user_id,
            action=acao,
            entity_type="modelo_llm",
            entity_id=str(out.id),
            payload_diff={"after": out.to_dict(), "origem": "openrouter_catalogo"},
            request=request,
        )
    return out.to_dict()
