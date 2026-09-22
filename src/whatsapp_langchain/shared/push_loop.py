"""Loop do worker: LISTEN atendimento_event → push FCM (mig 168).

Reusa o MESMO canal NOTIFY dos triggers da mig 035/145 — zero trigger novo.
Só o `kind: "inbound"` interessa (INSERT de mensagem nova); `updated` é o
worker gravando resposta, e notificar o operador da resposta da IA seria
ruído puro.

Conexão psycopg dedicada, fora do pool (LISTEN a bloqueia), com reconexão —
a lição do incidente de 26/07: conexão crua sem retry morre no primeiro
crash do Postgres e ninguém percebe.
"""

from __future__ import annotations

import asyncio
import json

import psycopg
import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.dispositivo_push import (
    apagar_token_invalido,
    tokens_da_empresa,
)
from whatsapp_langchain.shared.push_fcm import enviar_push, push_configurado
from whatsapp_langchain.shared.rls_context import empresa_scope

logger = structlog.get_logger()


async def _dados_da_mensagem(
    pool: AsyncConnectionPool, empresa_id: int, message_id: int
) -> dict[str, str] | None:
    """Monta o payload do push. None = não notificar.

    Filtros que o NOTIFY não carrega:
    - `incoming_message` vazia = outbound do operador (INSERT também dispara
      o trigger) — ninguém precisa de push da própria resposta;
    - `interna` = nota da equipe, não mensagem de cliente;
    - histórico importado do WhatsApp Business (Coexistence, mig 200) — são
      conversas antigas, e o lote inteiro viraria uma notificação por mensagem.
    """
    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT q.incoming_message, q.interna, q.atendimento_id,
                       COALESCE(c.nome, c.telefone, 'Cliente') AS quem,
                       q.normalized_input
                  FROM message_queue q
                  JOIN atendimento a ON a.id = q.atendimento_id
                  LEFT JOIN cliente c ON c.id = a.cliente_id
                 WHERE q.id = %s AND q.empresa_id = %s
                """,
                (message_id, empresa_id),
            )
            row = await cur.fetchone()
    if row is None:
        return None
    texto, interna, atendimento_id, quem, normalized_input = row
    if interna or not (texto or "").strip():
        return None
    if str(normalized_input or "").startswith("historico:"):
        return None
    preview = " ".join(str(texto).split())[:96]
    return {
        "atendimento_id": str(atendimento_id),
        "titulo": str(quem),
        "corpo": preview,
    }


async def _notificar_empresa(
    pool: AsyncConnectionPool, empresa_id: int, dados: dict[str, str]
) -> None:
    tokens = await tokens_da_empresa(pool, empresa_id)
    for token in tokens:
        resultado = await enviar_push(token, dados)
        if resultado == "token_invalido":
            await apagar_token_invalido(pool, token)


async def push_loop(pool: AsyncConnectionPool) -> None:
    """Loop de vida inteira do worker. Sai imediatamente se push desligado."""
    if not push_configurado():
        logger.info("push_loop_desligado", motivo="FIREBASE_SERVICE_ACCOUNT_JSON vazio")
        return
    logger.info("push_loop_iniciado")
    while True:
        try:
            async with await psycopg.AsyncConnection.connect(
                settings.database_url, autocommit=True
            ) as conn:
                await conn.execute("LISTEN atendimento_event")
                gen = conn.notifies()
                async for notif in gen:
                    try:
                        payload = json.loads(notif.payload)
                        if payload.get("event") != "mensagem":
                            continue
                        if payload.get("kind") != "inbound":
                            continue
                        empresa_id = int(payload["empresa_id"])
                        message_id = int(payload["message_id"])
                        dados = await _dados_da_mensagem(pool, empresa_id, message_id)
                        if dados is not None:
                            await _notificar_empresa(pool, empresa_id, dados)
                    except Exception:
                        # Um evento ruim não pode derrubar o LISTEN.
                        logger.exception("push_evento_falhou")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("push_loop_reconectando")
            await asyncio.sleep(5)
