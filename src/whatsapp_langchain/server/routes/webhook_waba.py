"""Webhook inbound da WhatsApp Cloud API (Meta).

GET /webhook/waba — Handshake (Meta valida verify_token)
POST /webhook/waba — Recebe mensagens + status updates de templates.

Auth: HMAC-SHA256 do body com meta_app_secret (header X-Hub-Signature-256).
Não usa verify_service_token — Meta não envia esse header.
"""

from __future__ import annotations

import base64
import hmac

import structlog
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import PlainTextResponse

from whatsapp_langchain.integrations.waba.client import download_media
from whatsapp_langchain.integrations.waba.webhook import (
    parse_account_updates,
    parse_history,
    parse_inbound,
    parse_message_echoes,
    parse_state_sync,
    parse_statuses,
    parse_template_status_updates,
    verify_signature,
)
from whatsapp_langchain.shared import waba_coexistence
from whatsapp_langchain.shared.atendimento import open_or_attach_atendimento
from whatsapp_langchain.shared.cliente import upsert_cliente
from whatsapp_langchain.shared.conexao import (
    get_conexao_by_waba_phone_id,
    get_credentials_decrypted,
    liberar_wamid,
    reivindicar_wamid,
)
from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.entrega import aplicar_status, motivo_da_falha
from whatsapp_langchain.shared.hook_dispatcher import dispatch_event
from whatsapp_langchain.shared.models import Conexao
from whatsapp_langchain.shared.queue import detectar_fluxo_guiado, enqueue_or_buffer

logger = structlog.get_logger()

router = APIRouter(prefix="/webhook/waba", tags=["webhook-waba"])


async def _resolve_waba_media_url(pool, conexao, msg) -> str | None:
    """Baixa a mídia inbound do WABA e devolve como data-URL base64.

    Best-effort: sem media_id, sem creds, ou falha de download → None (a msg
    segue como texto/caption). Espelha o que o webhook Evolution faz.
    """
    media_id = getattr(msg, "media_id", None)
    if not media_id:
        return None
    try:
        creds = await get_credentials_decrypted(pool, conexao.id) or {}
        access_token = creds.get("access_token")
        if not access_token:
            return None
        content, mime = await download_media(access_token, media_id)
        b64 = base64.b64encode(content).decode("ascii")
        return f"data:{mime};base64,{b64}"
    except Exception as exc:  # noqa: BLE001 — mídia é best-effort
        logger.warning(
            "waba_media_download_failed",
            media_id=media_id,
            error=str(exc),
        )
        return None


@router.get("")
async def waba_webhook_verify(
    request: Request,
) -> PlainTextResponse:
    """Handshake do Meta — devolve `hub.challenge` se o verify_token bate.

    Aceita query strings `hub.mode`, `hub.verify_token`, `hub.challenge`.

    A resposta é o challenge **cru**, não JSON: é o que a Meta espera para dar o
    webhook por verificado. A versão anterior fazia `int(challenge)` e caía num
    `{"challenge": ...}` quando o valor não era numérico — funcionava por
    acidente enquanto a Meta mandasse só dígitos, e o dia em que mandasse um
    token alfanumérico a verificação falharia sem explicação.
    """
    params = dict(request.query_params)
    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge", "")

    if mode != "subscribe":
        raise HTTPException(status_code=400, detail="hub.mode deve ser 'subscribe'")

    expected = (
        settings.waba_webhook_verify_token.get_secret_value()
        if settings.waba_webhook_verify_token
        else ""
    )
    if not expected or not hmac.compare_digest(token or "", expected):
        logger.warning(
            "waba_webhook_verify_failed", token_received_len=len(token or "")
        )
        raise HTTPException(status_code=403, detail="verify_token inválido")

    logger.info("waba_webhook_verified")
    return PlainTextResponse(challenge)


@router.post("")
async def waba_webhook_post(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
) -> dict[str, str]:
    """Recebe mensagens + atualizações de status de templates.

    Retorna 200 no happy path. Assinatura inválida/ausente → 200 com status
    `rejected` (não dá pra forçar Meta a desistir de payload forjado). Mas
    FALHA de enfileiramento → 5xx, pra Meta retentar e não perder a mensagem do
    cliente (o livro de wamid da mig 200 evita duplicar na redelivery).

    Campos tratados: `messages` (cliente → IA), `message_template_status_update`
    e, no modo Coexistence, `smb_message_echoes` (a empresa respondeu pelo
    celular → pausa a IA), `history`, `smb_app_state_sync` e `account_update`.
    """
    body = await request.body()

    app_secret = (
        settings.meta_app_secret.get_secret_value() if settings.meta_app_secret else ""
    )
    # Sprint D hardening: em produção com META_APP_SECRET configurado,
    # signature é OBRIGATÓRIA. Sem header ou inválida → reject. Webhook
    # sem HMAC = forgery trivial (Meta dispara payloads não autenticados
    # rejeitados pelo próprio Meta após N tentativas, mas atacante pode
    # forjar diretamente). Pré-Sprint D só rejeitava quando assinatura
    # inválida; ausência de header passava silenciosamente.
    # Sem secret NÃO se processa nada. A versão anterior só validava dentro de
    # `if app_secret:` — com a env vazia (o caso de qualquer instalação que ainda
    # não ligou o WABA) o endpoint aceitava payload forjado sem assinatura
    # nenhuma. Fail-open num webhook público é convite: quem descobrisse um
    # `phone_number_id` válido injetaria mensagem em nome do cliente.
    #
    # Fechar aqui não tira função de ninguém: `waba_enabled` já exige o secret
    # para as rotas de conexão, então WABA ligado sempre tem secret.
    if not app_secret:
        logger.warning("waba_webhook_sem_secret", body_size=len(body))
        return {"status": "rejected_no_secret"}

    if not x_hub_signature_256:
        logger.warning(
            "waba_webhook_signature_missing",
            body_size=len(body),
            production=settings.is_production,
        )
        # Assinatura ausente = SEMPRE rejeita (independente de is_production).
        # Antes só rejeitava em prod, o que deixava staging aceitar webhook WABA
        # forjado sem HMAC (injeção de mensagem/empresa).
        return {"status": "rejected_no_signature"}
    if not verify_signature(body, x_hub_signature_256, app_secret):
        logger.warning("waba_webhook_signature_invalid", body_size=len(body))
        return {"status": "rejected"}

    try:
        payload = await request.json()
    except Exception as exc:
        logger.warning("waba_webhook_bad_json", error=str(exc))
        return {"status": "bad_json"}

    return await _processar_payload(payload)


async def _processar_payload(
    payload: dict, *, restrito: Conexao | None = None
) -> dict[str, str]:
    """Processa um payload JÁ AUTENTICADO (assinatura conferida por quem chama).

    Compartilhado pelo `/webhook/waba` (App do ChatNexus) e pelo
    `/webhook/waba/{phone_number_id}` (App da própria empresa, ADR-006).
    Com `restrito`, só entra o que for DAQUELA conexão: itens de outro
    `phone_number_id` (ou de outra WABA, no account_update/templates) são
    descartados — o App de uma empresa não injeta mensagem em outra.
    """
    from whatsapp_langchain.shared.rls_context import set_request_context

    inbound_messages = parse_inbound(payload)
    template_updates = parse_template_status_updates(payload)
    # Coexistence (mig 200): o que vem do WhatsApp Business do celular.
    ecos = parse_message_echoes(payload)
    historicos = parse_history(payload)
    contatos = parse_state_sync(payload)
    contas = parse_account_updates(payload)
    # Avisos de entrega do que a Cloud API enviou (mig 203).
    estados = parse_statuses(payload)

    if restrito is not None:
        antes = (
            len(inbound_messages)
            + len(ecos)
            + len(historicos)
            + len(contatos)
            + len(contas)
            + len(template_updates)
        )
        phone = restrito.waba_phone_id
        waba = restrito.waba_account_id
        inbound_messages = [m for m in inbound_messages if m.waba_phone_id == phone]
        ecos = [e for e in ecos if e.waba_phone_id == phone]
        historicos = [h for h in historicos if h.waba_phone_id == phone]
        contatos = [c for c in contatos if c.waba_phone_id == phone]
        contas = [c for c in contas if c.waba_account_id == waba]
        estados = [e for e in estados if e.waba_phone_id == phone]
        template_updates = [
            t for t in template_updates if t.get("waba_account_id") == waba
        ]
        depois = (
            len(inbound_messages)
            + len(ecos)
            + len(historicos)
            + len(contatos)
            + len(contas)
            + len(template_updates)
        )
        if depois < antes:
            logger.warning(
                "waba_webhook_app_proprio_item_de_outra_conexao",
                conexao_id=restrito.id,
                descartados=antes - depois,
            )

    # Sem nada a processar, não toca o banco. A Meta entrega vários eventos que
    # não são mensagem nem status de template, e abrir conexão só para
    # descartá-los é trabalho à toa.
    #
    # Também era o que travava a suíte: o pool é singleton e nascia preso ao
    # event loop efêmero de um `TestClient` sem lifespan, onde cada request cria
    # e destrói o próprio portal do anyio — que então esperava para sempre por
    # tasks que ninguém ia fechar. Ver docs/MIGRACAO_DEV.md.
    if not (
        inbound_messages
        or template_updates
        or ecos
        or historicos
        or contatos
        or contas
        or estados
    ):
        logger.info("waba_webhook_sem_conteudo")
        return {"status": "received", "inbound_count": "0"}

    pool = await get_pool()
    enqueue_failed = False
    # Tenant SEMPRE pelo `phone_number_id` do payload (ou `entry.id` no
    # account_update) → conexão → empresa. Nenhum `empresa_id` vem da Meta.
    for msg in inbound_messages:
        conexao = await get_conexao_by_waba_phone_id(pool, msg.waba_phone_id)
        if conexao is None:
            logger.warning(
                "waba_webhook_no_conexao",
                phone_id=msg.waba_phone_id,
                from_number=msg.from_number,
            )
            continue

        # Sprint A.2 — seta RLS context da empresa após resolver conexão.
        set_request_context(conexao.empresa_id)

        # Idempotência (mig 200): a Meta reentrega o lote inteiro depois de um
        # 5xx. Reivindica o wamid antes; libera se falhar, para a reentrega
        # processar. Antes os comentários prometiam ON CONFLICT e o INSERT era
        # puro — um 503 duplicava todas as mensagens do lote.
        if not await reivindicar_wamid(pool, msg.message_id):
            logger.info("waba_webhook_duplicado", message_id=msg.message_id)
            continue

        try:
            await _enfileirar_inbound(pool, conexao, msg)
        except Exception as exc:
            # NÃO engolir: marca falha e ao final retorna 5xx pra Meta retentar
            # (antes retornava 200 e a mensagem do cliente era perdida pra
            # sempre numa falha transitória de DB).
            logger.exception("waba_webhook_enqueue_failed", error=str(exc))
            await liberar_wamid(pool, msg.message_id)
            enqueue_failed = True

    for eco in ecos:
        conexao = await get_conexao_by_waba_phone_id(pool, eco.waba_phone_id)
        if conexao is None:
            logger.warning("waba_webhook_no_conexao", phone_id=eco.waba_phone_id)
            continue
        set_request_context(conexao.empresa_id)
        if not await reivindicar_wamid(pool, eco.message_id):
            logger.info("waba_webhook_duplicado", message_id=eco.message_id)
            continue
        try:
            await waba_coexistence.registrar_eco(pool, conexao, eco)
        except Exception as exc:
            logger.exception("waba_coexistence_echo_failed", error=str(exc))
            await liberar_wamid(pool, eco.message_id)
            enqueue_failed = True

    for lote in historicos:
        conexao = await get_conexao_by_waba_phone_id(pool, lote.waba_phone_id)
        if conexao is None:
            logger.warning("waba_webhook_no_conexao", phone_id=lote.waba_phone_id)
            continue
        set_request_context(conexao.empresa_id)
        try:
            # Deduplica por wamid dentro da própria transação de gravação.
            await waba_coexistence.importar_historico(pool, conexao, lote)
        except Exception as exc:
            logger.exception("waba_coexistence_history_failed", error=str(exc))
            enqueue_failed = True

    for contato in contatos:
        conexao = await get_conexao_by_waba_phone_id(pool, contato.waba_phone_id)
        if conexao is None:
            logger.warning("waba_webhook_no_conexao", phone_id=contato.waba_phone_id)
            continue
        set_request_context(conexao.empresa_id)
        try:
            await waba_coexistence.sincronizar_contato(pool, conexao, contato)
        except Exception as exc:
            logger.exception("waba_coexistence_state_sync_failed", error=str(exc))
            enqueue_failed = True
    if contatos:
        logger.info("waba_coexistence_state_sync", contatos=len(contatos))

    for conta in contas:
        try:
            await waba_coexistence.processar_account_update(pool, conta)
        except Exception as exc:
            logger.exception("waba_coexistence_account_update_failed", error=str(exc))
            enqueue_failed = True

    await _aplicar_estados(pool, estados)

    # Updates de template status (já lidos acima, junto do inbound)
    for upd in template_updates:
        event = upd.get("event", "").upper()
        # Mapeia evento Meta → status local
        status_map = {
            "APPROVED": "approved",
            "REJECTED": "rejected",
            "PAUSED": "paused",
            "DISABLED": "disabled",
            "PENDING": "pending",
            "FLAGGED": "approved",  # Flagged = aprovado mas quality baixa
        }
        new_status = status_map.get(event)
        if not new_status:
            continue

        async with pool.connection() as conn:
            await conn.execute(
                """
                UPDATE waba_template
                   SET status = %s,
                       motivo_rejeicao = COALESCE(%s, motivo_rejeicao),
                       ultimo_sync_at = NOW(),
                       updated_at = NOW()
                 WHERE meta_template_id = %s
                """,
                (new_status, upd.get("reason"), upd.get("meta_template_id")),
            )
        logger.info(
            "waba_template_status_updated",
            template_id=upd.get("meta_template_id"),
            evento=event,  # `event` é o 1º argumento do structlog
            new_status=new_status,
        )

    if enqueue_failed:
        # 5xx → Meta redelivera o webhook inteiro; o livro de wamid (mig 200)
        # garante que o que já entrou não duplique.
        raise HTTPException(status_code=503, detail="enqueue failed; retry")

    return {"status": "received", "inbound_count": str(len(inbound_messages))}


async def _aplicar_estados(pool, estados) -> None:
    """Grava entregue/lida/falhou na mensagem que saiu (mig 203).

    Best-effort e sem 5xx: o aviso é informativo, e devolver erro faria a
    Meta reentregar o lote inteiro (mensagens junto). A falha SEMPRE vai para
    o log com o código — é o que faltava para saber por que uma mensagem
    "enviada" não chegou.
    """
    from whatsapp_langchain.shared.rls_context import set_request_context

    conexoes: dict[str, Conexao | None] = {}
    for st in estados:
        if st.waba_phone_id not in conexoes:
            conexoes[st.waba_phone_id] = await get_conexao_by_waba_phone_id(
                pool, st.waba_phone_id
            )
        conexao = conexoes[st.waba_phone_id]
        if conexao is None:
            continue
        set_request_context(conexao.empresa_id)
        erro = (
            motivo_da_falha(st.erro_codigo, st.erro_titulo, st.erro_detalhe)
            if st.status == "failed"
            else None
        )
        try:
            linha = await aplicar_status(
                pool,
                conexao_id=conexao.id,
                wamid=st.message_id,
                status=st.status,
                erro=erro,
            )
        except Exception as exc:
            logger.exception("waba_status_falhou_ao_gravar", error=str(exc))
            linha = None
        if st.status == "failed":
            logger.warning(
                "waba_mensagem_nao_entregue",
                empresa_id=conexao.empresa_id,
                conexao_id=conexao.id,
                message_queue_id=linha,
                wamid=st.message_id,
                codigo=st.erro_codigo,
                titulo=st.erro_titulo,
                detalhe=st.erro_detalhe,
            )
    if estados:
        logger.info(
            "waba_status_recebidos",
            total=len(estados),
            falhas=sum(1 for e in estados if e.status == "failed"),
        )


# ---------- App da Meta da própria empresa (ADR-006) ----------
#
# Cada App da Meta tem a própria URL de webhook e assina as notificações com o
# PRÓPRIO App Secret (doc "Webhooks — Getting Started"). A empresa que usa o App
# dela aponta o webhook para esta URL exclusiva; o `phone_number_id` do caminho
# diz qual conexão — e, portanto, qual segredo e qual verify token — valem ANTES
# de ler o corpo. Conexão que usa o App do ChatNexus continua no `/webhook/waba`.


async def _conexao_app_proprio(phone_number_id: str):
    """Conexão ativa do caminho + credenciais, ou (None, {}) se não for App próprio."""
    from whatsapp_langchain.shared.rls_context import set_request_context

    pool = await get_pool()
    conexao = await get_conexao_by_waba_phone_id(pool, phone_number_id)
    if conexao is None:
        return None, {}
    set_request_context(conexao.empresa_id)
    creds = await get_credentials_decrypted(pool, conexao.id) or {}
    if not creds.get("app_secret"):
        return None, {}
    return conexao, creds


@router.get("/{phone_number_id}")
async def waba_webhook_verify_conexao(
    phone_number_id: str, request: Request
) -> PlainTextResponse:
    """Handshake da URL exclusiva — compara com o verify token DA CONEXÃO."""
    params = dict(request.query_params)
    if params.get("hub.mode") != "subscribe" or not phone_number_id.isdigit():
        raise HTTPException(status_code=400, detail="hub.mode deve ser 'subscribe'")
    conexao, _creds = await _conexao_app_proprio(phone_number_id)
    esperado = (conexao.webhook_verify_token or "") if conexao else ""
    token = params.get("hub.verify_token") or ""
    if conexao is None or not esperado or not hmac.compare_digest(token, esperado):
        logger.warning(
            "waba_webhook_app_proprio_verify_failed",
            phone_id=phone_number_id,
            conexao_encontrada=conexao is not None,
        )
        raise HTTPException(status_code=403, detail="verify_token inválido")
    logger.info("waba_webhook_app_proprio_verified", conexao_id=conexao.id)
    return PlainTextResponse(params.get("hub.challenge", ""))


@router.post("/{phone_number_id}")
async def waba_webhook_post_conexao(
    phone_number_id: str,
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
) -> dict[str, str]:
    """POST da URL exclusiva: assinatura com o App Secret DA EMPRESA.

    Mesmo contrato do `/webhook/waba`: 200 com `rejected*` para assinatura
    ausente/inválida, 5xx só em falha interna (a Meta reentrega).
    """
    body = await request.body()
    if not phone_number_id.isdigit():
        return {"status": "rejected"}
    conexao, creds = await _conexao_app_proprio(phone_number_id)
    if conexao is None:
        logger.warning("waba_webhook_app_proprio_sem_conexao", phone_id=phone_number_id)
        return {"status": "rejected_no_secret"}
    if not x_hub_signature_256:
        logger.warning("waba_webhook_signature_missing", conexao_id=conexao.id)
        return {"status": "rejected_no_signature"}
    if not verify_signature(body, x_hub_signature_256, creds["app_secret"]):
        logger.warning("waba_webhook_signature_invalid", conexao_id=conexao.id)
        return {"status": "rejected"}
    try:
        payload = await request.json()
    except Exception as exc:
        logger.warning("waba_webhook_bad_json", error=str(exc))
        return {"status": "bad_json"}
    return await _processar_payload(payload, restrito=conexao)


async def _enfileirar_inbound(pool, conexao, msg) -> None:
    """Mensagem do cliente → cliente + atendimento + fila (vai ao worker).

    Abre cliente/atendimento como o webhook da Evolution: sem isso a mensagem
    WABA entrava com `atendimento_id` NULL — não aparecia na fila de
    atendimento, não notificava e pulava menu e handoff no worker.
    """
    # Mídia inbound: baixa via Graph /{media_id} e embute como data-URL
    # base64 (igual Evolution) — o worker já sabe processar data URLs
    # (visão/transcrição). Best-effort: falha vira texto/caption.
    media_url = await _resolve_waba_media_url(pool, conexao, msg)

    agente = conexao.default_agent_id
    cliente = await upsert_cliente(
        pool, conexao.empresa_id, msg.from_number, nome=msg.profile_name
    )
    atendimento, atendimento_aberto = await open_or_attach_atendimento(
        pool,
        empresa_id=conexao.empresa_id,
        cliente_id=cliente.id,
        conexao_id=conexao.id,
        agente=agente,
        conexao=conexao,  # snapshot do canal (mig 129)
    )

    # Agrupamento adaptativo (mig 144).
    grouping_seconds = float(conexao.resposta_agrupamento_segundos)
    is_guided_flow = grouping_seconds > 0 and await detectar_fluxo_guiado(
        pool,
        phone_number=msg.from_number,
        agent_id=agente,
        atendimento=atendimento,
    )

    body = msg.text or msg.media_caption or f"[{msg.type}]"
    await enqueue_or_buffer(
        pool,
        phone_number=msg.from_number,
        agent_id=agente,
        body=body,
        empresa_id=conexao.empresa_id,
        to_number=conexao.from_number,
        message_id=msg.message_id,
        conexao_id=conexao.id,
        atendimento_id=atendimento.id,
        media_url=media_url,
        media_type=msg.media_mime_type,
        media_filename=msg.media_filename,
        grouping_seconds=grouping_seconds,
        grouping_max_seconds=settings.message_grouping_max_seconds,
        is_guided_flow=is_guided_flow,
    )
    logger.info(
        "webhook_waba_received",
        empresa_id=conexao.empresa_id,
        conexao_id=conexao.id,
        cliente_id=cliente.id,
        atendimento_id=atendimento.id,
        atendimento_aberto=atendimento_aberto,
        message_id=msg.message_id,
        waba_mode=conexao.waba_mode,
    )

    if atendimento_aberto:
        await dispatch_event(
            pool,
            conexao.empresa_id,
            "atendimento.aberto",
            {
                "atendimento_id": atendimento.id,
                "cliente_id": cliente.id,
                "cliente_telefone": cliente.telefone,
                "cliente_nome": cliente.nome,
                "conexao_id": conexao.id,
                "agente_atual": atendimento.agente_atual,
            },
        )
    await dispatch_event(
        pool,
        conexao.empresa_id,
        "mensagem.recebida",
        {
            "atendimento_id": atendimento.id,
            "cliente_id": cliente.id,
            "cliente_telefone": cliente.telefone,
            "message_sid": msg.message_id,
            "body": body,
            "num_media": 1 if media_url else 0,
            "media_type": msg.media_mime_type,
        },
    )
