"""Disparador (Task 7) — resolução de destinatários + preview do disparo.

O preview é STATELESS: resolve a origem escolhida (manual/grupos/contatos
capturados/janela 24h) numa lista de telefones, deduplica, (opcionalmente)
valida no WhatsApp via Evolution, aplica o limite do plano e devolve
contagens + amostra. A UI só habilita "ENVIAR" depois do preview ("Preparar").
"""

from __future__ import annotations

from typing import Literal

import structlog
from psycopg_pool import AsyncConnectionPool
from pydantic import BaseModel

from whatsapp_langchain.shared.campanha import normalize_phone
from whatsapp_langchain.shared.conexao import get_conexao_by_id
from whatsapp_langchain.shared.rls_context import empresa_scope
from whatsapp_langchain.worker.evolution_client import EvolutionClient

logger = structlog.get_logger()

# Quantos itens no máximo retornar na amostra do preview (resto é "truncado").
PREVIEW_AMOSTRA_MAX = 100


class OrigemConfig(BaseModel):
    tipo: Literal["manual", "grupos", "contatos", "janela_24h"]
    grupo_ids: list[int] | None = None
    telefones_manual: list[str] | None = None


async def resolver_telefones(
    pool: AsyncConnectionPool, empresa_id: int, origem: OrigemConfig
) -> list[str]:
    """Resolve a origem numa lista de telefones E.164 (pré-dedup).

    Só inclui destinatários com telefone (membros só-LID não são enviáveis por
    telefone). Para `janela_24h` usa as mensagens recebidas nas últimas 24h.
    """
    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            if origem.tipo == "manual":
                return [p for p in (origem.telefones_manual or [])]
            if origem.tipo == "grupos":
                cur = await conn.execute(
                    """
                    SELECT telefone FROM grupo_membro
                     WHERE empresa_id = %s AND grupo_id = ANY(%s)
                       AND telefone IS NOT NULL
                    """,
                    (empresa_id, origem.grupo_ids or []),
                )
            elif origem.tipo == "contatos":
                cur = await conn.execute(
                    """
                    SELECT telefone FROM contato_capturado
                     WHERE empresa_id = %s AND telefone IS NOT NULL
                    """,
                    (empresa_id,),
                )
            else:  # janela_24h
                cur = await conn.execute(
                    """
                    SELECT DISTINCT phone_number FROM message_queue
                     WHERE empresa_id = %s AND incoming_message <> ''
                       AND created_at >= NOW() - INTERVAL '24 hours'
                    """,
                    (empresa_id,),
                )
            rows = await cur.fetchall()
    return [r[0] for r in rows if r[0]]


async def _limite_plano(pool: AsyncConnectionPool, empresa_id: int) -> int | None:
    """Limite de contatos por disparo do plano (None = ilimitado).

    Lê `features['disparador_max_contatos']`; ausente ⇒ ilimitado (a feature é
    semeada na migration de planos do disparador).
    """
    try:
        from whatsapp_langchain.shared.plano_limits import get_plano_info

        plano = await get_plano_info(pool, empresa_id)
        val = plano.features.get("disparador_max_contatos")
        return int(val) if val is not None else None
    except Exception:  # noqa: BLE001 — gating não pode derrubar o preview
        return None


class PreviewResultado(BaseModel):
    total_bruto: int
    count_duplicado: int
    count_invalido: int
    total_disponivel: int
    amostra: list[str]
    amostra_truncada: bool
    limite_plano: int | None
    excede_plano: bool


async def preview_disparo(
    pool: AsyncConnectionPool,
    empresa_id: int,
    origem: OrigemConfig,
    *,
    conexao_id: int | None = None,
    validar_numeros: bool = False,
) -> PreviewResultado:
    """Resolve + deduplica + (opcional) valida números + aplica limite do plano."""
    brutos = await resolver_telefones(pool, empresa_id, origem)
    total_bruto = len(brutos)

    # Dedup por telefone normalizado (E.164).
    vistos: set[str] = set()
    normalizados: list[str] = []
    for raw in brutos:
        norm = normalize_phone(raw)
        if norm and norm not in vistos:
            vistos.add(norm)
            normalizados.append(norm)
    count_duplicado = total_bruto - len(normalizados)

    # Validação opcional via Evolution (onWhatsApp/exists).
    count_invalido = 0
    validos = normalizados
    if validar_numeros and conexao_id is not None and normalizados:
        conexao = await get_conexao_by_id(pool, conexao_id)
        if conexao is not None and conexao.provider == "evolution":
            from whatsapp_langchain.shared.outbound import build_outbound_client

            client, _ = await build_outbound_client(pool, conexao)
            if isinstance(client, EvolutionClient):
                checked = await client.check_numbers(normalizados)
                existem = {
                    (n["telefone"] or "").lstrip("+") for n in checked if n["exists"]
                }
                validos = [p for p in normalizados if p.lstrip("+") in existem]
                count_invalido = len(normalizados) - len(validos)

    limite = await _limite_plano(pool, empresa_id)
    excede = limite is not None and len(validos) > limite

    return PreviewResultado(
        total_bruto=total_bruto,
        count_duplicado=count_duplicado,
        count_invalido=count_invalido,
        total_disponivel=len(validos),
        amostra=validos[:PREVIEW_AMOSTRA_MAX],
        amostra_truncada=len(validos) > PREVIEW_AMOSTRA_MAX,
        limite_plano=limite,
        excede_plano=excede,
    )


class PreviewRequest(BaseModel):
    conexao_id: int | None = None
    origem: OrigemConfig
    validar_numeros: bool = False
