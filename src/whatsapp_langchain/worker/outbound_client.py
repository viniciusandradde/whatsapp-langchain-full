"""Protocolo comum dos clientes de envio outbound.

Define o contrato que `TwilioClient` e `EvolutionClient` cumprem, sem
introduzir herança. O worker recebe um `dict[provider, OutboundClient]`
e resolve o cliente certo via `Conexao.provider` da mensagem.

Adicionar um novo provider (ex: WABA Cloud direto) é só implementar
`send_message` + `send_typing` com a mesma assinatura — nenhum import
deste módulo é necessário.
"""

from typing import Protocol


class OutboundClient(Protocol):
    """Cliente de envio outbound de mensagens WhatsApp.

    Implementadores: `TwilioClient`, `EvolutionClient`.

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
                mensagem (ex: Twilio). Outros ignoram.

        Returns:
            True se o indicador foi enviado, False caso contrário.
            Nunca levanta exceção — falha no typing não pode derrubar
            o pipeline.
        """
        ...
