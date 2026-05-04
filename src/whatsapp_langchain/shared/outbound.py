"""Envio outbound manual de operador (M4.a — humano respondendo via painel).

Diferente do worker, que envia respostas geradas pelo agente, este módulo
serve as ações do operador no painel: dado um atendimento aberto, envia
texto via o provider da conexão associada (Twilio ou Evolution) e
persiste a mensagem como uma row "outbound-only" em `message_queue`
(com `incoming_message=''` e `response=` preenchido) — isso garante que
a mensagem aparece na timeline do drawer sem inventar uma tabela nova.

A mesma row também leva `agent_id = atendimento.agente_atual` para
preservar o thread; `normalized_input` carrega `manual:{user_id}` para
audit.

Roteamento por provider:
- `twilio_sandbox`, `twilio_prod`, `waba` → `TwilioClient`
- `evolution` → `EvolutionClient`
"""

from __future__ import annotations

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.atendimento import get_atendimento_by_id
from whatsapp_langchain.shared.cliente import get_cliente_by_id
from whatsapp_langchain.shared.conexao import get_conexao_by_id
from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.worker.evolution_client import EvolutionClient
from whatsapp_langchain.worker.outbound_client import OutboundClient
from whatsapp_langchain.worker.twilio_client import TwilioClient

logger = structlog.get_logger()


class OutboundError(Exception):
    """Erro lógico ao tentar enviar mensagem manual."""


def _build_client(provider: str, from_number: str) -> tuple[OutboundClient, str]:
    """Instancia o cliente outbound certo pro provider da conexão.

    Returns:
        (client, delivery_mode) — `delivery_mode` ("real" / "mock") fica
        em log pra audit e retorno do endpoint.

    Raises:
        OutboundError: provider desconhecido ou config faltando.
    """
    if provider in ("twilio_sandbox", "twilio_prod", "waba"):
        mode = settings.resolved_twilio_outbound_mode
        client = TwilioClient(
            account_sid=settings.twilio_account_sid,
            api_key_sid=settings.twilio_api_key_sid,
            api_key_secret=settings.twilio_api_key_secret,
            from_number=f"whatsapp:{from_number}",
            delivery_mode=mode,
        )
        return client, mode

    if provider == "evolution":
        if not (
            settings.evolution_api_url
            and settings.evolution_api_key
            and settings.evolution_instance_name
        ):
            raise OutboundError(
                "Evolution não configurada (API URL / key / instance ausentes)."
            )
        mode = settings.evolution_outbound_mode or "mock"
        client = EvolutionClient(
            api_url=settings.evolution_api_url,
            api_key=settings.evolution_api_key.get_secret_value(),
            instance_name=settings.evolution_instance_name,
            delivery_mode=mode,
        )
        return client, mode

    raise OutboundError(f"Provider desconhecido: {provider!r}")


async def _persist_outbound_row(
    pool: AsyncConnectionPool,
    *,
    empresa_id: int,
    conexao_id: int,
    atendimento_id: int,
    phone_number: str,
    agent_id: str,
    response: str,
    user_id: str,
    provider_message_id: str,
) -> dict:
    """Insere row outbound-only em message_queue + bump last_message_at."""
    thread_id = f"{phone_number}:{agent_id}"
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            INSERT INTO message_queue
                (empresa_id, conexao_id, atendimento_id, message_id,
                 phone_number, agent_id, thread_id,
                 incoming_message, response, normalized_input,
                 status, process_after, processed_at)
            VALUES (%s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    'done', NOW(), NOW())
            RETURNING id, agent_id, incoming_message, response, status,
                      created_at, processed_at
            """,
            (
                empresa_id,
                conexao_id,
                atendimento_id,
                provider_message_id,
                phone_number,
                agent_id,
                thread_id,
                "",
                response,
                f"manual:{user_id}",
            ),
        )
        row = await cur.fetchone()
        await conn.execute(
            """
            UPDATE atendimento
               SET last_message_at = NOW(), updated_at = NOW()
             WHERE id = %s
            """,
            (atendimento_id,),
        )
        await conn.commit()
    assert row is not None
    return {
        "id": row[0],
        "agent_id": row[1],
        "incoming_message": row[2],
        "response": row[3],
        "status": row[4],
        "created_at": row[5].isoformat() if row[5] else None,
        "processed_at": row[6].isoformat() if row[6] else None,
    }


async def send_outbound_manual(
    pool: AsyncConnectionPool,
    *,
    atendimento_id: int,
    empresa_id: int,
    user_id: str,
    conteudo: str,
) -> dict:
    """Envia mensagem manual a partir do painel.

    Carrega o atendimento + cliente + conexão (todos escopados pela empresa,
    a guarda cross-tenant é responsabilidade do caller), envia via o
    provider da conexão (Twilio ou Evolution) com `from_number` da conexão
    associada, e persiste a mensagem na timeline.

    Raises:
        OutboundError: cliente/conexão ausentes, atendimento já fechado,
        provider desconhecido, ou client retornou erro.
    """
    text = conteudo.strip()
    if not text:
        raise OutboundError("Mensagem vazia.")

    atendimento = await get_atendimento_by_id(pool, atendimento_id)
    if atendimento is None or atendimento.empresa_id != empresa_id:
        raise OutboundError("Atendimento não encontrado.")
    if atendimento.status not in ("aguardando", "em_andamento"):
        raise OutboundError("Atendimento já fechado — reabra um novo para responder.")

    cliente = await get_cliente_by_id(pool, atendimento.cliente_id)
    if cliente is None or cliente.empresa_id != empresa_id:
        raise OutboundError("Cliente do atendimento não encontrado.")

    conexao = await get_conexao_by_id(pool, atendimento.conexao_id)
    if conexao is None or conexao.empresa_id != empresa_id:
        raise OutboundError("Conexão do atendimento não encontrada.")

    client, outbound_mode = _build_client(conexao.provider, conexao.from_number)

    try:
        provider_message_id = await client.send_message(cliente.telefone, text)
    except Exception as e:  # noqa: BLE001 — embrulha qualquer falha do client
        logger.error(
            "outbound_manual_send_failed",
            atendimento_id=atendimento_id,
            empresa_id=empresa_id,
            provider=conexao.provider,
            error=str(e),
        )
        raise OutboundError(f"Falha ao enviar via {conexao.provider}: {e}") from e

    row = await _persist_outbound_row(
        pool,
        empresa_id=empresa_id,
        conexao_id=atendimento.conexao_id,
        atendimento_id=atendimento_id,
        phone_number=cliente.telefone,
        agent_id=atendimento.agente_atual,
        response=text,
        user_id=user_id,
        provider_message_id=provider_message_id,
    )

    logger.info(
        "outbound_manual_sent",
        atendimento_id=atendimento_id,
        empresa_id=empresa_id,
        user_id=user_id,
        provider=conexao.provider,
        provider_message_id=provider_message_id,
        outbound_mode=outbound_mode,
    )
    return row
