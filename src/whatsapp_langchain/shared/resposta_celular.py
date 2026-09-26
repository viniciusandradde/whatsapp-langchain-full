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
from datetime import UTC, datetime, timedelta
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


#: Sem atendimento na linha (legado), só respostas deste período contam.
JANELA_SEM_ATENDIMENTO: Final = timedelta(hours=24)


async def respostas_humanas_recentes(
    pool: AsyncConnectionPool,
    *,
    empresa_id: int,
    phone_number: str,
    agent_id: str | None,
    antes_do_id: int,
    atendimento_id: int | None,
) -> list[RespostaHumana]:
    """Respostas humanas (celular e painel) dadas a este cliente depois da
    última resposta da IA, na ordem em que saíram.

    Só do atendimento ATUAL: sem esse recorte, uma conversa nova herdava o que
    o operador escreveu numa conversa encerrada dias antes (em produção, 26/09:
    o aviso "Você foi transferido para o setor…" de 9 dias atrás fez o agente
    dizer a um "Olá" que o atendimento já tinha sido encaminhado). Linha sem
    atendimento (legado) cai na janela de `JANELA_SEM_ATENDIMENTO`.
    """
    if atendimento_id is not None:
        recorte = "atendimento_id = %s"
        param_recorte: object = atendimento_id
    else:
        recorte = "created_at > NOW() - %s"
        param_recorte = JANELA_SEM_ATENDIMENTO
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            WITH ultima_ia AS (
                SELECT COALESCE(MAX(created_at), '-infinity'::timestamptz) AS em
                  FROM message_queue
                 WHERE empresa_id = %s AND phone_number = %s
                   AND origem_resposta = 'agente'
                   AND (%s::text IS NULL OR agent_id = %s)
                   AND id < %s
                   AND {recorte}
            )
            SELECT normalized_input, response
              FROM message_queue, ultima_ia
             WHERE empresa_id = %s AND phone_number = %s
               AND id < %s
               AND {recorte}
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
                param_recorte,
                empresa_id,
                phone_number,
                antes_do_id,
                param_recorte,
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


# --- retorno da IA por tempo (PR B da ADR-008) --------------------------------

#: Mensagem do cliente mais velha que isto não é reprocessada: responder
#: depois de um dia soa como robô atrasado.
IDADE_MAXIMA_REPROCESSO: Final = timedelta(hours=24)
#: Opções oferecidas no painel (minutos). NULL = só "Devolver à IA".
OPCOES_RETORNO_MINUTOS: Final = (30, 60, 120, 240, 1440)


def deve_retornar(
    *,
    ultima_celular_em: datetime | None,
    ultima_cliente_em: datetime | None,
    minutos: int | None,
    agora: datetime,
) -> bool:
    """A IA volta sozinha quando a conexão tem prazo, o dono não responde pelo
    celular há pelo menos esse prazo, o cliente escreveu DEPOIS da última
    resposta do dono e essa mensagem do cliente ainda é recente."""
    if not minutos or ultima_celular_em is None or ultima_cliente_em is None:
        return False
    if ultima_cliente_em <= ultima_celular_em:
        return False
    if agora - ultima_celular_em < timedelta(minutes=minutos):
        return False
    return agora - ultima_cliente_em <= IDADE_MAXIMA_REPROCESSO


async def retornar_ia_por_tempo(
    pool: AsyncConnectionPool, *, agora: datetime | None = None
) -> int:
    """Devolve à IA as conversas pausadas pelo celular que venceram o prazo da
    conexão e reprocessa a última mensagem do cliente. Devolve quantas
    conversas voltaram.

    A devolução é um UPDATE condicional ao dono AINDA ser `HUMANO_CELULAR`:
    é a trava entre as réplicas do worker (só uma recebe a linha de volta) e
    impede tirar a conversa de um operador que a assumiu pelo painel entre a
    leitura dos candidatos e a devolução. A mensagem é reenfileirada na mesma
    transação, só se ainda carregar o marcador de handoff.
    """
    from whatsapp_langchain.shared.rls_context import empresa_scope

    agora = agora or datetime.now(UTC)
    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT a.id, a.empresa_id, c.celular_retorno_ia_minutos,
                       (SELECT max(m.created_at) FROM message_queue m
                         WHERE m.atendimento_id = a.id AND m.origem_resposta = 'celular'),
                       ult.id, ult.created_at
                  FROM atendimento a
                  JOIN conexao c ON c.id = a.conexao_id
                  LEFT JOIN LATERAL (
                        SELECT m.id, m.created_at FROM message_queue m
                         WHERE m.atendimento_id = a.id
                           AND m.response LIKE '[handoff humano%%'
                         ORDER BY m.id DESC LIMIT 1
                  ) ult ON TRUE
                 WHERE a.status = 'em_andamento'
                   AND a.assigned_to_user_id = %s
                   AND c.celular_retorno_ia_minutos IS NOT NULL
                """,
                (HUMANO_CELULAR,),
            )
            candidatos = await cur.fetchall()
    voltaram = 0
    for atd_id, empresa_id, minutos, ult_cel, ult_cli_id, ult_cli_em in candidatos:
        if not deve_retornar(
            ultima_celular_em=ult_cel,
            ultima_cliente_em=ult_cli_em,
            minutos=minutos,
            agora=agora,
        ):
            continue
        with empresa_scope(empresa_id=empresa_id):
            async with pool.connection() as conn:
                cur = await conn.execute(
                    """
                    UPDATE atendimento
                       SET assigned_to_user_id = NULL, status = 'aguardando',
                           updated_at = NOW()
                     WHERE id = %s AND status = 'em_andamento'
                       AND assigned_to_user_id = %s
                    RETURNING id
                    """,
                    (atd_id, HUMANO_CELULAR),
                )
                if await cur.fetchone() is None:
                    continue
                await conn.execute(
                    """
                    UPDATE message_queue
                       SET status = 'queued', response = NULL, error = NULL,
                           attempts = 0, lease_until = NULL, processed_at = NULL,
                           process_after = NOW(), updated_at = NOW()
                     WHERE id = %s AND atendimento_id = %s
                       AND response LIKE '[handoff humano%%'
                    """,
                    (ult_cli_id, atd_id),
                )
                await conn.commit()
        voltaram += 1
        logger.info(
            "resposta_celular_ia_retornou",
            atendimento_id=atd_id,
            empresa_id=empresa_id,
            minutos=minutos,
            reprocessada=ult_cli_id,
        )
    return voltaram
