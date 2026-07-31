"""Protocolo comum dos clientes de envio outbound.

Define o contrato que os clientes de saída cumprem, sem
introduzir herança. O worker recebe um `dict[provider, OutboundClient]`
e resolve o cliente certo via `Conexao.provider` da mensagem.

Adicionar um novo provider (ex: WABA Cloud direto) é só implementar
`send_message` + `send_typing` com a mesma assinatura — nenhum import
deste módulo é necessário.
"""

from typing import Protocol


class OutboundClient(Protocol):
    """Cliente de envio outbound de mensagens WhatsApp.

    Implementadores: `EvolutionClient`, `WabaClient`.

    `delivery_mode` é exposto pra debugging/observabilidade — o worker
    loga o modo de cada provider no boot.
    """

    delivery_mode: str

    async def send_message(self, to: str, body: str) -> str:
        """Envia mensagem outbound.

        Args:
            to: Número destino em E.164 (ex: `+5511999999999`).
                Implementações que precisam de outro formato (ex: Evolution
                quer só dígitos) normalizam internamente.
            body: Texto da mensagem.

        Returns:
            ID/SID da mensagem enviada — formato depende do provider.
        """
        ...

    async def send_typing(self, to: str, message_id: str | None = None) -> bool:
        """Envia indicador de digitação (best-effort).

        Args:
            to: Número destino em qualquer formato.
            message_id: ID da mensagem inbound sendo respondida — usado
                apenas pelos providers que correlacionam typing com
                mensagem. Providers que não suportam ignoram.

        Returns:
            True se o indicador foi enviado, False caso contrário.
            Nunca levanta exceção — falha no typing não pode derrubar
            o pipeline.
        """
        ...


# Limite de corpo por mensagem no WhatsApp. Herdado do Twilio (1600), mas
# vale para qualquer provider.
MESSAGE_BODY_LIMIT = 1600


def split_message_body(body: str, limit: int = MESSAGE_BODY_LIMIT) -> list[str]:
    """Divide mensagens longas em partes que o WhatsApp aceita.

    Veio do cliente Twilio, que rejeitava corpos acima de 1600 caracteres, e
    ficou porque o limite é do WhatsApp, não do provider — a Evolution usa a
    mesma função. Quebra em limites naturais (parágrafo, linha, espaço) antes
    de recorrer a corte bruto.
    """
    if limit <= 0:
        raise ValueError("limit deve ser maior que zero")

    if len(body) <= limit:
        return [body]

    chunks: list[str] = []
    remaining = body

    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break

        split_at = -1
        for sep in ("\n\n", "\n", " "):
            idx = remaining.rfind(sep, 0, limit + 1)
            if idx > 0:
                split_at = idx
                break

        if split_at <= 0:
            split_at = limit

        chunk = remaining[:split_at].rstrip()
        if not chunk:
            chunk = remaining[:limit]

        chunks.append(chunk)
        remaining = remaining[len(chunk) :].lstrip()

    return chunks
