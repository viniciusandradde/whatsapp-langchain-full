"""Transcrição de áudio para o OPERADOR (mig 169).

Independente do agente IA: o preprocess do worker transcreve para montar o
input do agente (`normalized_input`), mas conexão em modo manual, whitelist,
menu e workflow retornam antes dele — o áudio nunca vira texto pra quem
atende pelo painel. Este módulo preenche `message_queue.transcricao`, que a
timeline exibe, e é usado pelo botão "Transcrever" (sob demanda) e pelo
gancho automático do worker (`conexao.transcrever_audio_sempre`).
"""

from __future__ import annotations

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.midia_processing import (
    download_media,
    transcribe_audio_bytes,
)

logger = structlog.get_logger()


class MensagemSemAudioError(ValueError):
    """A mensagem não tem áudio inbound para transcrever."""


async def transcrever_mensagem(
    pool: AsyncConnectionPool,
    message_id: int,
    *,
    empresa_id: int | None = None,
    atendimento_id: int | None = None,
    model: str | None = None,
) -> str:
    """Transcreve (uma vez) o áudio da mensagem e persiste em `transcricao`.

    Idempotente: se a coluna já está preenchida, devolve o texto salvo sem
    nova chamada de LLM. `empresa_id`/`atendimento_id` restringem o lookup
    quando a chamada vem da API (o pool roda como a aplicação — o filtro no
    WHERE é o que garante o escopo do tenant, não RLS).
    """
    where = ["id = %s"]
    args: list[object] = [message_id]
    if empresa_id is not None:
        where.append("empresa_id = %s")
        args.append(empresa_id)
    if atendimento_id is not None:
        where.append("atendimento_id = %s")
        args.append(atendimento_id)

    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT media_url, media_type, transcricao, empresa_id
              FROM message_queue
             WHERE {" AND ".join(where)}
            """,  # type: ignore[arg-type]  # noqa: S608 — colunas fixas; valores via placeholder
            tuple(args),
        )
        row = await cur.fetchone()

    if row is None:
        raise MensagemSemAudioError("Mensagem não encontrada.")
    media_url, media_type, existente, empresa_da_linha = row
    if existente is not None:
        return existente
    if not media_url or not (media_type or "").startswith("audio/"):
        raise MensagemSemAudioError("Esta mensagem não tem áudio para transcrever.")

    media_bytes, mime_real = await download_media(media_url)
    # Custo visível à governança: esta transcrição era um POST cru ao
    # OpenRouter que não aparecia em ia_execucao nem somava no ia_budget
    # (mig 161) — gasto invisível ao teto da empresa. O gancho automático do
    # worker não passa `empresa_id`, então usamos o da própria linha.
    texto = await transcribe_audio_bytes(
        media_bytes,
        mime_real or media_type,
        model=model,
        pool=pool,
        empresa_id=empresa_id if empresa_id is not None else empresa_da_linha,
    )

    async with pool.connection() as conn:
        # `transcricao IS NULL` no WHERE: se duas transcrições correram em
        # paralelo (botão + gancho automático), a primeira vence e a segunda
        # não sobrescreve — o texto exibido não "pisca" entre variantes.
        await conn.execute(
            """
            UPDATE message_queue
               SET transcricao = %s
             WHERE id = %s AND transcricao IS NULL
            """,
            (texto, message_id),
        )
        cur = await conn.execute(
            "SELECT transcricao FROM message_queue WHERE id = %s",
            (message_id,),
        )
        row = await cur.fetchone()

    final = row[0] if row and row[0] is not None else texto
    logger.info(
        "transcricao_audio_persistida",
        message_id=message_id,
        chars=len(final),
    )
    return final
