"""Resposta do dono pelo celular pausa a IA (ADR-008, mig 205).

Na conexão Evolution, mensagem enviada pelo número da conexão FORA do
ChatNexus (celular, WhatsApp Web ou Desktop do dono) chega ao webhook com
`key.fromMe = true`. Ela é resposta humana:

1. entra na conversa como linha de saída (`origem_resposta = 'celular'`,
   `normalized_input = 'manual:app:whatsapp'`, rótulo "WhatsApp (celular)");
2. pausa a IA naquela conversa: dono sentinela `HUMANO_CELULAR`, o mesmo
   mecanismo do `HUMANO_APP` da Coexistência (`shared/waba_coexistence.py`).
   O gate de handoff do worker cala o agente; "Devolver à IA" retoma;
3. entra no contexto do agente quando ele voltar a responder:
   `respostas_humanas_recentes` + `bloco_respostas_humanas`, injetados pelo
   worker antes do modelo (vale também para a resposta do operador do painel,
   que até aqui o agente não via).

A Evolution v2 não reemite o que ela mesma enviou (conferido no dev em
21/09/2026), então `fromMe` aqui é o dono. O eco de saúde da mig 198 é
tratado ANTES, no webhook.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

import structlog
from psycopg import errors as pg_errors
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.atendimento import (
    claim_atendimento,
    open_or_attach_atendimento,
)
from whatsapp_langchain.shared.cliente import upsert_cliente
from whatsapp_langchain.shared.models import Conexao
from whatsapp_langchain.shared.outbound import _persist_outbound_row

logger = structlog.get_logger()

#: Dono sentinela do atendimento quando o dono respondeu pelo celular
#: (conexão Evolution). Espelho de `waba_coexistence.HUMANO_APP`.
HUMANO_CELULAR: Final = "whatsapp_celular"

#: `origem_resposta` (mig 144) das linhas vindas do celular.
ORIGEM_CELULAR: Final = "celular"

#: `user_id` do `_persist_outbound_row` → `normalized_input='manual:app:whatsapp'`.
USUARIO_CELULAR: Final = "app:whatsapp"

#: Quantas respostas humanas, no máximo, entram no contexto do agente.
MAX_RESPOSTAS_NO_CONTEXTO: Final = 5
#: Corte por resposta, para uma mensagem longa do dono não dominar o prompt.
MAX_CHARS_POR_RESPOSTA: Final = 500

_SUFIXOS_IGNORADOS: Final = ("@g.us", "@broadcast", "@newsletter")

_MIDIA_ROTULO: Final = {
    "imageMessage": "foto",
    "videoMessage": "vídeo",
    "audioMessage": "áudio",
    "documentMessage": "documento",
    "stickerMessage": "figurinha",
}


@dataclass(frozen=True)
class RespostaCelular:
    """O que interessa de um `messages.upsert` com `fromMe = true`."""

    message_id: str
    para: str  # telefone do cliente (destinatário), já normalizado pelo webhook
    texto: str


def destino_ignorado(remote_jid: str | None) -> bool:
    """Grupo, lista de transmissão, canal e status não são conversa de atendimento."""
    jid = (remote_jid or "").strip()
    return not jid or jid.endswith(_SUFIXOS_IGNORADOS)


def texto_da_resposta(message: dict | None) -> str | None:
    """Texto que vai para a bolha. Mídia vira um indicativo com a legenda.

    O arquivo em si não é baixado: a IA não vai responder a esta mensagem, e
    baixar mídia do celular custaria banda e armazenamento sem uso. Reação,
    enquete e mensagens de protocolo devolvem None (não viram bolha).
    """
    if not isinstance(message, dict):
        return None
    conversa = message.get("conversation")
    if isinstance(conversa, str) and conversa.strip():
        return conversa.strip()
    ext = message.get("extendedTextMessage")
    if isinstance(ext, dict):
        t = ext.get("text")
        if isinstance(t, str) and t.strip():
            return t.strip()
    for chave, rotulo in _MIDIA_ROTULO.items():
        corpo = message.get(chave)
        if isinstance(corpo, dict):
            legenda = corpo.get("caption")
            nome = corpo.get("fileName") if chave == "documentMessage" else None
            base = (
                f"[{rotulo} enviada pelo celular]"
                if rotulo in ("foto", "figurinha")
                else f"[{rotulo} enviado pelo celular]"
            )
            if nome:
                base = f"[documento enviado pelo celular: {nome}]"
            if isinstance(legenda, str) and legenda.strip():
                return f"{base} {legenda.strip()}"
            return base
    return None


async def registrar_resposta_celular(
    pool: AsyncConnectionPool, conexao: Conexao, resposta: RespostaCelular
):
    """Grava a resposta do dono e pausa a IA daquela conversa.

    Devolve o `Atendimento` usado, ou None quando a mensagem já tinha sido
    registrada (reentrega do webhook).
    """
    cliente = await upsert_cliente(pool, conexao.empresa_id, resposta.para)
    atendimento, criado = await open_or_attach_atendimento(
        pool,
        empresa_id=conexao.empresa_id,
        cliente_id=cliente.id,
        conexao_id=conexao.id,
        agente=conexao.default_agent_id,
        conexao=conexao,
        iniciado_cliente=False,
        assigned_to_user_id=HUMANO_CELULAR,
    )
    # Anexar a um atendimento aberto não troca o dono (regra do
    # open_or_attach). Sem dono = com a IA → o dono assumiu pelo celular.
    # Com um operador do painel → fica com ele (não rouba).
    if not criado and not atendimento.assigned_to_user_id:
        atendimento = (
            await claim_atendimento(pool, atendimento.id, HUMANO_CELULAR) or atendimento
        )
    try:
        await _persist_outbound_row(
            pool,
            empresa_id=conexao.empresa_id,
            conexao_id=conexao.id,
            atendimento_id=atendimento.id,
            phone_number=resposta.para,
            agent_id=conexao.default_agent_id,
            response=resposta.texto,
            user_id=USUARIO_CELULAR,
            provider_message_id=resposta.message_id,
            origem_resposta=ORIGEM_CELULAR,
        )
    except pg_errors.UniqueViolation:
        # Reentrega do webhook: a bolha já existe (índice da mig 205).
        logger.info(
            "evolution_resposta_celular_repetida",
            conexao_id=conexao.id,
            message_id=resposta.message_id,
        )
        return None
    logger.info(
        "evolution_resposta_celular_registrada",
        conexao_id=conexao.id,
        empresa_id=conexao.empresa_id,
        atendimento_id=atendimento.id,
        ia_pausada=atendimento.assigned_to_user_id == HUMANO_CELULAR,
    )
    return atendimento


# --- contexto do agente -------------------------------------------------------


@dataclass(frozen=True)
class RespostaHumana:
    texto: str
    canal: str  # "celular" | "painel"


def canal_da_resposta(normalized_input: str | None) -> str | None:
    """`manual:app:…` = celular (Evolution ou Coexistência); `manual:<user>` =
    painel; `manual:system:…` (avisos automáticos) e o resto não contam."""
    n = normalized_input or ""
    if n.startswith("manual:app:"):
        return "celular"
    if n.startswith("manual:system:") or not n.startswith("manual:"):
        return None
    return "painel"


def bloco_respostas_humanas(itens: list[RespostaHumana]) -> str:
    """Bloco que vai antes do texto do cliente, no mesmo formato dos outros
    avisos do worker (`[FORA DO EXPEDIENTE]`, `[JÁ ENCAMINHADO…]`)."""
    if not itens:
        return ""
    partes = []
    for i in itens[-MAX_RESPOSTAS_NO_CONTEXTO:]:
        t = " ".join(i.texto.split())
        if len(t) > MAX_CHARS_POR_RESPOSTA:
            t = t[: MAX_CHARS_POR_RESPOSTA - 1] + "…"
        origem = "pelo celular" if i.canal == "celular" else "pelo painel"
        partes.append(f"({origem}) {t}")
    return (
        "[A EQUIPE JÁ RESPONDEU ESTE CLIENTE desde a sua última mensagem — "
        "não repita, não contradiga e continue a partir daqui: "
        + " | ".join(partes)
        + "]"
    )


async def respostas_humanas_recentes(
    pool: AsyncConnectionPool,
    *,
    empresa_id: int,
    phone_number: str,
    agent_id: str | None,
    antes_do_id: int,
) -> list[RespostaHumana]:
    """Respostas humanas (celular e painel) dadas a este cliente depois da
    última resposta da IA, na ordem em que saíram."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            WITH ultima_ia AS (
                SELECT COALESCE(MAX(created_at), '-infinity'::timestamptz) AS em
                  FROM message_queue
                 WHERE empresa_id = %s AND phone_number = %s
                   AND origem_resposta = 'agente'
                   AND (%s::text IS NULL OR agent_id = %s)
                   AND id < %s
            )
            SELECT normalized_input, response
              FROM message_queue, ultima_ia
             WHERE empresa_id = %s AND phone_number = %s
               AND id < %s
               AND created_at > ultima_ia.em
               AND normalized_input LIKE 'manual:%%'
               AND response IS NOT NULL
               AND response_apagada_at IS NULL
             ORDER BY created_at DESC
             LIMIT %s
            """,
            (
                empresa_id,
                phone_number,
                agent_id,
                agent_id,
                antes_do_id,
                empresa_id,
                phone_number,
                antes_do_id,
                MAX_RESPOSTAS_NO_CONTEXTO,
            ),
        )
        rows = await cur.fetchall()
    itens: list[RespostaHumana] = []
    for normalized_input, response in reversed(rows):
        canal = canal_da_resposta(normalized_input)
        if canal and (response or "").strip():
            itens.append(RespostaHumana(texto=response, canal=canal))
    return itens
