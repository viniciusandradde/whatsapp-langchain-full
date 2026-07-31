"""Envio outbound manual de operador (M4.a — humano respondendo via painel).

Diferente do worker, que envia respostas geradas pelo agente, este módulo
serve as ações do operador no painel: dado um atendimento aberto, envia
texto via o provider da conexão associada (WABA ou Evolution) e
persiste a mensagem como uma row "outbound-only" em `message_queue`
(com `incoming_message=''` e `response=` preenchido) — isso garante que
a mensagem aparece na timeline do drawer sem inventar uma tabela nova.

A mesma row também leva `agent_id = atendimento.agente_atual` para
preservar o thread; `normalized_input` carrega `manual:{user_id}` para
audit.

Roteamento por provider:
- `waba` → `WabaClient`
- `evolution` → `EvolutionClient`
"""

from __future__ import annotations

import base64

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.integrations.waba import templates as waba_templates
from whatsapp_langchain.integrations.waba.client import WabaClient
from whatsapp_langchain.shared.atendimento import get_atendimento_by_id
from whatsapp_langchain.shared.cliente import get_cliente_by_id
from whatsapp_langchain.shared.conexao import (
    get_conexao_by_id,
    get_credentials_decrypted,
)
from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.models import Atendimento, Cliente, Conexao
from whatsapp_langchain.worker.evolution_client import EvolutionClient
from whatsapp_langchain.worker.outbound_client import OutboundClient

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

    # Conexão `waba` sem `waba_phone_id` saía pelo Twilio até a remoção do
    # provider. Vira erro explícito: é uma conexão que nunca completou o
    # Embedded Signup, e falhar aqui é melhor que falhar no envio.
    if provider == "waba":
        raise OutboundError(
            "Conexão WABA sem waba_phone_id — refaça o Embedded Signup."
        )

    # --- Evolution (credenciais por-conexão do DB) ---
    # api_url (server) e api_key (chave do server) podem cair em env por serem
    # infra app-level. instance_name é a IDENTIDADE da conexão → vem só do DB
    # (credentials cifradas ou payload_json). Sem env fallback: conexão tem que
    # ser cadastrada pela UI (sem instance default "via código").
    if provider == "evolution":
        credentials = await get_credentials_decrypted(pool, conexao.id) or {}
        api_url = credentials.get("api_url") or settings.evolution_api_url
        api_key = credentials.get("api_key") or (
            settings.evolution_api_key.get_secret_value()
            if settings.evolution_api_key
            else ""
        )
        instance_name = credentials.get("instance_name") or conexao.payload_json.get(
            "instance_name"
        )
        if not (api_url and api_key and instance_name):
            raise OutboundError(
                "Evolution não configurada: conexão sem api_url/api_key/instance_name "
                "(cadastre/reconecte a conexão pela UI)."
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


# Nome público: o worker (processor) usa o mesmo builder por-conexão que o
# envio manual do painel — fonte única de verdade pro cliente outbound.
build_outbound_client = _build_client


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
    media_url: str | None = None,
    media_type: str | None = None,
) -> dict:
    """Insere row outbound-only em message_queue + bump last_message_at.

    `media_url`/`media_type` vão pras colunas `response_media_*` (mig 146), e
    NÃO pras `media_*`, que são do lado inbound — a timeline decide o lado da
    bolha pela origem do campo, então mídia do operador gravada em `media_url`
    apareceria como se o cliente tivesse mandado.
    """
    thread_id = f"{phone_number}:{agent_id}"
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            INSERT INTO message_queue
                (empresa_id, conexao_id, atendimento_id, message_id,
                 phone_number, agent_id, thread_id,
                 incoming_message, response, normalized_input,
                 response_media_url, response_media_type,
                 status, process_after, processed_at)
            VALUES (%s, %s, %s, %s,
                    %s, %s, %s,
                    %s, %s, %s,
                    %s, %s,
                    'done', NOW(), NOW())
            RETURNING id, agent_id, incoming_message, response, status,
                      created_at, processed_at,
                      response_media_url, response_media_type
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
                media_url,
                media_type,
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
        "response_media_url": row[7],
        "response_media_type": row[8],
    }


async def _resolver_destino(
    pool: AsyncConnectionPool,
    atendimento_id: int,
    empresa_id: int,
) -> tuple[Atendimento, Cliente, Conexao]:
    """Valida o atendimento e devolve para onde e por onde enviar.

    Compartilhado por texto e mídia: são as mesmas quatro pré-condições (existe
    na empresa, está aberto, tem cliente, tem conexão viva), e mantê-las em dois
    lugares garantiria que um dia divergissem.
    """
    atendimento = await get_atendimento_by_id(pool, atendimento_id)
    if atendimento is None or atendimento.empresa_id != empresa_id:
        raise OutboundError("Atendimento não encontrado.")
    if atendimento.status not in ("aguardando", "em_andamento"):
        raise OutboundError("Atendimento já fechado — reabra um novo para responder.")

    cliente = await get_cliente_by_id(pool, atendimento.cliente_id)
    if cliente is None or cliente.empresa_id != empresa_id:
        raise OutboundError("Cliente do atendimento não encontrado.")

    if atendimento.conexao_id is None:
        raise OutboundError(
            "A conexão deste atendimento foi removida — reatribua a uma conexão "
            "ativa para responder."
        )
    conexao = await get_conexao_by_id(pool, atendimento.conexao_id)
    if conexao is None or conexao.empresa_id != empresa_id:
        raise OutboundError(
            "A conexão deste atendimento foi removida — reatribua a uma conexão "
            "ativa para responder."
        )
    return atendimento, cliente, conexao


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
    provider da conexão (WABA ou Evolution) com `from_number` da conexão
    associada, e persiste a mensagem na timeline.

    Raises:
        OutboundError: cliente/conexão ausentes, atendimento já fechado,
        provider desconhecido, ou client retornou erro.
    """
    text = conteudo.strip()
    if not text:
        raise OutboundError("Mensagem vazia.")

    atendimento, cliente, conexao = await _resolver_destino(
        pool, atendimento_id, empresa_id
    )
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

    # `_resolver_destino` já levantou se a conexão fosse ausente; o assert é só
    # pro type checker, que perde o narrowing ao atravessar a função.
    assert atendimento.conexao_id is not None

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


#: Teto prático do WhatsApp para documento. Acima disso o provider recusa, e
#: recusar aqui dá erro legível em vez de 4xx cru do Evolution.
MIDIA_MAX_BYTES = 16 * 1024 * 1024


def _mediatype_de(mime: str) -> str:
    """MIME → `mediatype` do Evolution, que só conhece três valores."""
    if mime.startswith("image/"):
        return "image"
    if mime.startswith("video/"):
        return "video"
    return "document"


async def send_outbound_manual_midia(
    pool: AsyncConnectionPool,
    *,
    atendimento_id: int,
    empresa_id: int,
    user_id: str,
    arquivo: bytes,
    mime: str,
    filename: str | None = None,
    legenda: str = "",
) -> dict:
    """Envia mídia do operador (áudio gravado, foto, documento) ao cliente.

    Áudio vai por `send_audio` e o resto por `send_media`: o WhatsApp trata
    "nota de voz" e "arquivo de áudio anexado" como coisas diferentes, e só a
    primeira chega com player e forma de onda.

    Dois formatos do mesmo conteúdo, de propósito:
    - **no fio**, base64 puro — é o que o Evolution espera nos campos `media` e
      `audio`;
    - **no banco**, data-URL (`data:<mime>;base64,...`) — é o formato que o
      renderizador do painel e do app já leem para a mídia inbound, então a
      bolha de saída não precisa de um caminho novo.

    Raises:
        OutboundError: arquivo vazio/grande demais, atendimento fechado, ou
        provider sem suporte a mídia.
    """
    if not arquivo:
        raise OutboundError("Arquivo vazio.")
    if len(arquivo) > MIDIA_MAX_BYTES:
        limite = MIDIA_MAX_BYTES // (1024 * 1024)
        raise OutboundError(f"Arquivo acima do limite de {limite} MB.")

    atendimento, cliente, conexao = await _resolver_destino(
        pool, atendimento_id, empresa_id
    )
    client, outbound_mode = await _build_client(pool, conexao)

    # Envio de mídia por operador só existe no Evolution hoje. O WABA exigiria
    # subir o arquivo pro /media do Graph e mandar pelo id devolvido, e o Twilio
    # exigiria hospedar o arquivo numa URL pública — nenhum dos dois está
    # implementado. Falhar explícito aqui é melhor que aceitar o upload e não
    # entregar nada ao cliente.
    enviar_audio = getattr(client, "send_audio", None)
    enviar_media = getattr(client, "send_media", None)
    if enviar_audio is None or enviar_media is None:
        raise OutboundError(
            f"Enviar arquivo ainda não é suportado em conexões {conexao.provider}. "
            "Use uma conexão Evolution para anexos e áudio."
        )

    base64_puro = base64.b64encode(arquivo).decode("ascii")
    e_audio = mime.startswith("audio/")
    texto = legenda.strip()

    try:
        if e_audio:
            provider_message_id = await enviar_audio(cliente.telefone, base64_puro)
        else:
            provider_message_id = await enviar_media(
                cliente.telefone,
                base64_puro,
                mediatype=_mediatype_de(mime),
                caption=texto or None,
                filename=filename,
            )
    except Exception as e:  # noqa: BLE001 — embrulha qualquer falha do client
        logger.error(
            "outbound_manual_midia_failed",
            atendimento_id=atendimento_id,
            empresa_id=empresa_id,
            provider=conexao.provider,
            mime=mime,
            bytes=len(arquivo),
            error=str(e),
        )
        raise OutboundError(f"Falha ao enviar via {conexao.provider}: {e}") from e

    # `_resolver_destino` já levantou se a conexão fosse ausente; o assert é só
    # pro type checker, que perde o narrowing ao atravessar a função.
    assert atendimento.conexao_id is not None

    row = await _persist_outbound_row(
        pool,
        empresa_id=empresa_id,
        conexao_id=atendimento.conexao_id,
        atendimento_id=atendimento_id,
        phone_number=cliente.telefone,
        agent_id=atendimento.agente_atual,
        response=texto,
        user_id=user_id,
        provider_message_id=provider_message_id,
        media_url=f"data:{mime};base64,{base64_puro}",
        media_type=mime,
    )

    logger.info(
        "outbound_manual_midia_sent",
        atendimento_id=atendimento_id,
        empresa_id=empresa_id,
        user_id=user_id,
        provider=conexao.provider,
        provider_message_id=provider_message_id,
        outbound_mode=outbound_mode,
        mime=mime,
        bytes=len(arquivo),
        nota_de_voz=e_audio,
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
      e falha no envio não pode quebrar a transferência.
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

    if atendimento.conexao_id is None:
        # Conexão apagada (mig 129) — system msg no-opa em conexão morta.
        logger.warning("system_outbound_conexao_ausente", atendimento_id=atendimento_id)
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


async def send_template_by_id(
    pool: AsyncConnectionPool,
    *,
    conexao_id: int,
    empresa_id: int,
    to: str,
    template_id: int,
    variables: dict[str, str] | None = None,
    atendimento_id: int | None = None,
    user_id: str = "system:template",
) -> dict:
    """Envia um template HSM **aprovado** (por id no banco), roteando por provider.

    Caminho único usado por campanhas (broadcast fora da janela 24h) e pelo
    composer do `/atendimento`. WABA → Cloud API (`send_template_message`);
    Só WABA suporta template HSM hoje. `variables` = `{"1": "...", ...}`.

    Persiste row na timeline quando `atendimento_id` é setado.

    Raises:
        OutboundError: conexão/template ausentes, template não-approved,
        provider sem suporte a HSM, ou falha do client.
    """
    variables = variables or {}
    conexao = await get_conexao_by_id(pool, conexao_id)
    if conexao is None or conexao.empresa_id != empresa_id:
        raise OutboundError("Conexão não encontrada.")

    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT nome, idioma, status, provider "
            "FROM waba_template WHERE id = %s AND conexao_id = %s",
            (template_id, conexao_id),
        )
        row = await cur.fetchone()
    if row is None:
        raise OutboundError("Template não encontrado nesta conexão.")
    nome, idioma, status, _tpl_provider = row
    if status != "approved":
        raise OutboundError(f"Template não está aprovado (status={status}).")

    if conexao.provider == "waba" and conexao.waba_phone_id:
        creds = await get_credentials_decrypted(pool, conexao_id) or {}
        access_token = creds.get("access_token")
        if not access_token:
            raise OutboundError("Conexão WABA sem access_token — refaça o OAuth.")
        try:
            provider_message_id = await waba_templates.send_template_message(
                access_token,
                conexao.waba_phone_id,
                to=to,
                template_name=nome,
                language=idioma,
                variables=variables,
            )
        except Exception as e:  # noqa: BLE001
            raise OutboundError(f"Falha ao enviar template WABA: {e}") from e
    else:
        raise OutboundError(f"Provider {conexao.provider!r} não suporta template HSM.")

    row_out: dict = {}
    if atendimento_id is not None:
        var_repr = ", ".join(f"{k}={v}" for k, v in variables.items()) or "no variables"
        row_out = await _persist_outbound_row(
            pool,
            empresa_id=empresa_id,
            conexao_id=conexao_id,
            atendimento_id=atendimento_id,
            phone_number=to,
            agent_id=conexao.default_agent_id,
            response=f"[template {nome}] {var_repr}",
            user_id=user_id,
            provider_message_id=provider_message_id,
        )

    logger.info(
        "outbound_template_by_id_sent",
        conexao_id=conexao_id,
        empresa_id=empresa_id,
        template_id=template_id,
        provider=conexao.provider,
        to=to,
        provider_message_id=provider_message_id,
    )
    return {"provider_message_id": provider_message_id, "message_row": row_out or None}
