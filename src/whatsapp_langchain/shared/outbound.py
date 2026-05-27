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

from whatsapp_langchain.integrations.waba.client import WabaClient
from whatsapp_langchain.shared.atendimento import get_atendimento_by_id
from whatsapp_langchain.shared.cliente import get_cliente_by_id
from whatsapp_langchain.shared.conexao import (
    get_conexao_by_id,
    get_credentials_decrypted,
)
from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.models import Conexao
from whatsapp_langchain.worker.evolution_client import EvolutionClient
from whatsapp_langchain.worker.outbound_client import OutboundClient
from whatsapp_langchain.worker.twilio_client import TwilioClient

logger = structlog.get_logger()


class OutboundError(Exception):
    """Erro lógico ao tentar enviar mensagem manual."""


async def _build_client(
    pool: AsyncConnectionPool, conexao: Conexao
) -> tuple[OutboundClient, str]:
    """Instancia o cliente outbound certo pro provider da conexão.

    Lê credenciais cifradas (WABA / Evolution multi-instância) quando
    disponíveis, senão cai em env vars (compat com conexões legadas).

    Returns:
        (client, delivery_mode) — `delivery_mode` ("real" / "mock") fica
        em log pra audit e retorno do endpoint.

    Raises:
        OutboundError: provider desconhecido ou config faltando.
    """
    provider = conexao.provider

    # --- WABA real (Meta Cloud API) ---
    if provider == "waba" and conexao.waba_phone_id:
        credentials = await get_credentials_decrypted(pool, conexao.id) or {}
        access_token = credentials.get("access_token")
        if not access_token:
            raise OutboundError(
                "Conexão WABA sem access_token cifrado — refaça o OAuth."
            )
        mode = "real" if settings.is_production else "real"  # WABA não tem 'mock' útil
        client = WabaClient(
            access_token=access_token,
            phone_id=conexao.waba_phone_id,
            delivery_mode=mode,
        )
        return client, mode

    # --- Twilio (sandbox/prod) + legacy 'waba' (sem phone_id, usa Twilio API) ---
    if provider in ("twilio_sandbox", "twilio_prod", "waba"):
        mode = settings.resolved_twilio_outbound_mode
        client = TwilioClient(
            account_sid=settings.twilio_account_sid,
            api_key_sid=settings.twilio_api_key_sid,
            api_key_secret=settings.twilio_api_key_secret,
            from_number=f"whatsapp:{conexao.from_number}",
            delivery_mode=mode,
        )
        return client, mode

    # --- Evolution (com credentials cifradas multi-instance OU env vars fallback) ---
    if provider == "evolution":
        credentials = await get_credentials_decrypted(pool, conexao.id) or {}
        api_url = credentials.get("api_url") or settings.evolution_api_url
        api_key = credentials.get("api_key") or (
            settings.evolution_api_key.get_secret_value()
            if settings.evolution_api_key
            else ""
        )
        instance_name = (
            credentials.get("instance_name")
            or conexao.payload_json.get("instance_name")
            or settings.evolution_instance_name
        )
        if not (api_url and api_key and instance_name):
            raise OutboundError(
                "Evolution não configurada (API URL / key / instance ausentes)."
            )
        mode = settings.evolution_outbound_mode or "mock"
        client = EvolutionClient(
            api_url=api_url,
            api_key=api_key,
            instance_name=instance_name,
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

    client, outbound_mode = await _build_client(pool, conexao)

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


async def send_system_outbound(
    pool: AsyncConnectionPool,
    *,
    atendimento_id: int,
    empresa_id: int,
    conteudo: str,
    tag_user_id: str = "system:transfer",
) -> dict:
    """Envia mensagem do SISTEMA (não-humano) ao cliente — usado pra notificar
    transferência automática, abertura de protocolo, etc.

    Diferenças vs `send_outbound_manual`:
    - `tag_user_id` aceita qualquer string (não exige user real do auth.user).
      Default `"system:transfer"`. Aparece em `normalized_input=manual:<tag>`.
    - **Não levanta exception em falha de envio** — loga warning e retorna {}.
      Importante porque é chamado dentro de tools de agente (transfer_to_human)
      e falha no Twilio não pode quebrar a transferência.
    - Pula validação rígida — atendimento aberto/fechado é decisão do caller.
    """
    text = conteudo.strip()
    if not text:
        return {}

    atendimento = await get_atendimento_by_id(pool, atendimento_id)
    if atendimento is None or atendimento.empresa_id != empresa_id:
        logger.warning(
            "system_outbound_atendimento_invalido",
            atendimento_id=atendimento_id,
            empresa_id=empresa_id,
        )
        return {}

    cliente = await get_cliente_by_id(pool, atendimento.cliente_id)
    if cliente is None:
        logger.warning("system_outbound_cliente_ausente", atendimento_id=atendimento_id)
        return {}

    conexao = await get_conexao_by_id(pool, atendimento.conexao_id)
    if conexao is None:
        logger.warning("system_outbound_conexao_ausente", atendimento_id=atendimento_id)
        return {}

    try:
        client, outbound_mode = await _build_client(pool, conexao)
        provider_message_id = await client.send_message(cliente.telefone, text)
    except Exception as e:  # noqa: BLE001
        logger.warning(
            "system_outbound_send_failed",
            atendimento_id=atendimento_id,
            provider=conexao.provider,
            error=str(e),
        )
        return {}

    row = await _persist_outbound_row(
        pool,
        empresa_id=empresa_id,
        conexao_id=atendimento.conexao_id,
        atendimento_id=atendimento_id,
        phone_number=cliente.telefone,
        agent_id=atendimento.agente_atual,
        response=text,
        user_id=tag_user_id,
        provider_message_id=provider_message_id,
    )
    logger.info(
        "system_outbound_sent",
        atendimento_id=atendimento_id,
        empresa_id=empresa_id,
        tag=tag_user_id,
        provider=conexao.provider,
        outbound_mode=outbound_mode,
        chars=len(text),
    )
    return row


async def send_outbound_template(
    pool: AsyncConnectionPool,
    *,
    conexao_id: int,
    empresa_id: int,
    to: str,
    content_sid: str,
    content_variables: dict[str, str] | None = None,
    atendimento_id: int | None = None,
    user_id: str = "system:template",
) -> dict:
    """Envia template HSM (Twilio Content) — FORA da janela 24h.

    Útil pra notificação ativa: CSAT proativo, lembrete agendamento, alerta.
    Hoje só suporta Twilio (WABA tem fluxo de template próprio via Cloud API
    que será atendido em sprint futura; Evolution não suporta HSM).

    Args:
        conexao_id: ID da conexão (deve ser provider twilio_*).
        empresa_id: Tenant scope.
        to: Número destino E.164 (ex: +5511999999999).
        content_sid: SID do template aprovado no Twilio (ex: HXxxx...).
        content_variables: Dict de variáveis {"1": "valor1", "2": "valor2"}.
        atendimento_id: Opcional — quando setado, persiste row em
            message_queue ligada ao atendimento (timeline). Sem isso,
            template é enviado sem rastro no histórico do cliente.
        user_id: Tag pra normalized_input. Default "system:template".

    Raises:
        OutboundError: provider não-Twilio, conexão não encontrada, ou
            client retornou erro.
    """
    if not content_sid:
        raise OutboundError("content_sid é obrigatório.")

    conexao = await get_conexao_by_id(pool, conexao_id)
    if conexao is None or conexao.empresa_id != empresa_id:
        raise OutboundError("Conexão não encontrada.")
    if conexao.provider not in ("twilio_sandbox", "twilio_prod"):
        raise OutboundError(
            f"send_template não suportado pra provider {conexao.provider!r} "
            "— hoje só Twilio (HSM via Content API)."
        )

    client, outbound_mode = await _build_client(pool, conexao)
    # Guard de tipo: _build_client garante TwilioClient pra twilio_*, mas
    # pyright não infere por causa do Protocol genérico.
    if not isinstance(client, TwilioClient):
        raise OutboundError("Esperado TwilioClient pra conexão Twilio.")

    try:
        provider_message_id = await client.send_template(
            to, content_sid, content_variables
        )
    except Exception as e:  # noqa: BLE001
        logger.error(
            "outbound_template_send_failed",
            conexao_id=conexao_id,
            empresa_id=empresa_id,
            content_sid=content_sid,
            to=to,
            error=str(e),
        )
        raise OutboundError(f"Falha ao enviar template via Twilio: {e}") from e

    # Persiste na timeline SE atendimento_id setado — caso contrário é
    # mensagem "fora de atendimento" (CSAT proativo, broadcast) sem timeline.
    row: dict = {}
    if atendimento_id is not None:
        # Resumo legível do template no campo response (variables inline)
        var_repr = (
            ", ".join(f"{k}={v}" for k, v in content_variables.items())
            if content_variables
            else "no variables"
        )
        response_summary = f"[template {content_sid}] {var_repr}"
        row = await _persist_outbound_row(
            pool,
            empresa_id=empresa_id,
            conexao_id=conexao_id,
            atendimento_id=atendimento_id,
            phone_number=to,
            agent_id=conexao.default_agent_id,
            response=response_summary,
            user_id=user_id,
            provider_message_id=provider_message_id,
        )

    logger.info(
        "outbound_template_sent",
        conexao_id=conexao_id,
        empresa_id=empresa_id,
        atendimento_id=atendimento_id,
        content_sid=content_sid,
        to=to,
        provider_message_id=provider_message_id,
        outbound_mode=outbound_mode,
    )
    return {
        "provider_message_id": provider_message_id,
        "outbound_mode": outbound_mode,
        "message_row": row or None,
    }
