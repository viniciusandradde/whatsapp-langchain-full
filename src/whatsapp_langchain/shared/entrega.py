"""Estado de entrega das mensagens enviadas pela Cloud API (mig 203).

A Meta aceita o envio (devolve o wamid) e só DEPOIS avisa, por webhook, se a
mensagem foi entregue, lida ou falhou. Este módulo liga os dois lados:

- `registrar_envio` guarda o wamid na linha da `message_queue` que o enviou;
- `ClienteQueRegistraEnvio` faz isso para o worker sem tocar nos ~30 pontos
  de envio do `processor.py` — embrulha o cliente WABA num lugar só;
- `aplicar_status` grava o aviso na linha (o estado só avança; `failed`
  prevalece) e devolve o id da linha;
- `motivo_da_falha` traduz o código da Meta para uma frase que o operador
  entende.
"""

from __future__ import annotations

from typing import Any

import structlog
from psycopg_pool import AsyncConnectionPool

logger = structlog.get_logger()

# Códigos mais comuns da Cloud API → frase para o operador. Fonte: Meta,
# "Error codes" da WhatsApp Cloud API. Código fora da lista cai no título
# que a própria Meta mandou.
_MOTIVOS: dict[int, str] = {
    131047: "Passaram mais de 24 horas desde a última mensagem do cliente. Só um modelo aprovado reabre a conversa",
    131026: "O número não pode receber a mensagem (sem WhatsApp, versão antiga ou bloqueou a empresa)",
    131049: "A Meta segurou a mensagem para não saturar o cliente com mensagens de marketing",
    131050: "O cliente pediu para não receber mensagens de marketing desta empresa",
    131051: "Tipo de mensagem não suportado",
    131052: "Não foi possível baixar a mídia enviada pelo cliente",
    131053: "Não foi possível enviar a mídia",
    131056: "Muitas mensagens para o mesmo número em pouco tempo. Aguarde e tente de novo",
    131031: "A conta do WhatsApp da empresa está bloqueada",
    131042: "Problema com a forma de pagamento da conta na Meta",
    131045: "O número da empresa não está registrado na Meta",
    130472: "O número do cliente está num experimento da Meta e não recebeu a mensagem",
    130429: "Limite de envios por segundo atingido",
    131000: "Falha na Meta ao enviar. Tente de novo",
    132000: "A quantidade de variáveis não bate com o modelo",
    132001: "O modelo não existe ou não está aprovado neste idioma",
    132005: "O texto do modelo com as variáveis ficou longo demais",
    132007: "O conteúdo do modelo viola as regras da Meta",
    132012: "Formato de variável do modelo inválido",
    132015: "O modelo está pausado pela Meta por baixa qualidade",
    132016: "O modelo foi desativado pela Meta",
    133010: "O número da empresa não está registrado na Meta",
}

# Ordem do estado de entrega: só avança. `failed` fica fora — prevalece.
_ORDEM = {"sent": 1, "delivered": 2, "read": 3}


def motivo_da_falha(codigo: int | None, titulo: str | None, detalhe: str | None) -> str:
    """Frase legível + código (para o suporte achar na documentação da Meta)."""
    base = _MOTIVOS.get(codigo or -1) or (titulo or detalhe or "Falha na entrega")
    return f"{base} (código {codigo})" if codigo else base


async def registrar_envio(
    pool: AsyncConnectionPool, message_queue_id: int, wamid: str
) -> None:
    """Acrescenta o wamid à linha que o enviou (idempotente)."""
    if not wamid:
        return
    async with pool.connection() as conn:
        await conn.execute(
            """
            UPDATE message_queue
               SET response_message_ids = CASE
                       WHEN response_message_ids IS NULL THEN ARRAY[%s]
                       WHEN %s = ANY(response_message_ids) THEN response_message_ids
                       ELSE array_append(response_message_ids, %s)
                   END
             WHERE id = %s
            """,
            (wamid, wamid, wamid, message_queue_id),
        )


async def aplicar_status(
    pool: AsyncConnectionPool,
    *,
    conexao_id: int,
    wamid: str,
    status: str,
    erro: str | None = None,
) -> int | None:
    """Grava o aviso da Meta na linha que enviou `wamid` (só desta conexão).

    Estado só avança (`sent` → `delivered` → `read`); `failed` prevalece e
    não é sobrescrito por aviso posterior de outra parte da mesma resposta.
    Devolve o id da linha, ou None se nenhuma linha avançou (wamid de envio
    antigo, de campanha sem conversa, ou aviso fora de ordem).
    """
    if status == "failed":
        guarda = ""
    else:
        guarda = (
            " AND (entrega_status IS NULL OR (entrega_status <> 'failed'"
            " AND CASE entrega_status WHEN 'sent' THEN 1 WHEN 'delivered' THEN 2"
            " WHEN 'read' THEN 3 ELSE 0 END < %s))"
        )
    params: list[Any] = [
        status,
        erro if status == "failed" else None,
        conexao_id,
        wamid,
    ]
    if guarda:
        params.append(_ORDEM[status])
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            UPDATE message_queue
               SET entrega_status = %s,
                   entrega_erro = %s,
                   entrega_em = NOW()
             WHERE conexao_id = %s
               AND %s = ANY(response_message_ids){guarda}
            RETURNING id
            """,  # type: ignore[arg-type]
            tuple(params),
        )
        row = await cur.fetchone()
    return int(row[0]) if row else None


class ClienteQueRegistraEnvio:
    """Invólucro do cliente WABA do worker: guarda o wamid de cada envio.

    O worker envia por dezenas de caminhos (IA, menu, CSAT, coleta,
    workflow…); embrulhar o cliente num lugar só
    (`processor._resolve_outbound_client`) cobre todos. Registrar é
    best-effort: falha ao gravar nunca derruba um envio que já saiu.
    Qualquer outro atributo passa direto ao cliente de verdade — inclusive
    `send_audio`/`send_media`, que o worker procura por `getattr`.
    """

    def __init__(self, cliente: Any, pool: AsyncConnectionPool, message_queue_id: int):
        self._cliente = cliente
        self._pool = pool
        self._message_queue_id = message_queue_id
        # Parte do Protocol `OutboundClient` (o boot loga o modo).
        self.delivery_mode: str = getattr(cliente, "delivery_mode", "real")

    async def send_message(self, to: str, body: str) -> str:
        wamid = await self._cliente.send_message(to, body)
        try:
            await registrar_envio(self._pool, self._message_queue_id, wamid)
        except Exception as exc:  # noqa: BLE001 — o envio já saiu
            logger.warning(
                "entrega_registro_falhou",
                message_queue_id=self._message_queue_id,
                error=str(exc),
            )
        return wamid

    async def send_typing(self, to: str, message_id: str | None = None) -> bool:
        return await self._cliente.send_typing(to, message_id)

    def __getattr__(self, nome: str) -> Any:
        return getattr(self._cliente, nome)
