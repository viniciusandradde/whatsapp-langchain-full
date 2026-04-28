"""Cliente assíncrono para envio de mensagens WhatsApp via Twilio.

Usa httpx para chamadas não-bloqueantes à API REST do Twilio (Messages API).
Autenticação outbound via API Key (api_key_sid + api_key_secret), separada
da autenticação inbound (auth_token para validação de assinatura no webhook).

Em desenvolvimento local, o cliente tambem suporta `delivery_mode="mock"`,
que simula o envio outbound sem consumir cota do Twilio.

Uso:
    from whatsapp_langchain.worker.twilio_client import TwilioClient

    client = TwilioClient(
        account_sid="AC...",
        api_key_sid="SK...",
        api_key_secret="...",
        from_number="whatsapp:+14155238886",
    )
    sid = await client.send_message(to="+5511...", body="Olá!")
    await client.send_typing(to="+5511...")
"""

import re
import uuid

import httpx
import structlog

logger = structlog.get_logger()

# URL base da Messages API do Twilio
TWILIO_MESSAGES_URL = (
    "https://api.twilio.com/2010-04-01/Accounts/{account_sid}/Messages.json"
)
TWILIO_MESSAGE_BODY_LIMIT = 1600

# URL do endpoint de typing indicator (Public Beta, out/2025)
# Marca mensagem como lida + exibe "digitando..." por até 25s
TWILIO_TYPING_URL = "https://messaging.twilio.com/v2/Indicators/Typing.json"
TWILIO_MESSAGE_SID_RE = re.compile(r"^[A-Z]{2}[0-9a-fA-F]{32}$")


class TwilioSendError(Exception):
    """Erro ao enviar mensagem via Twilio.

    Encapsula status HTTP e body de erro para facilitar diagnóstico.
    """

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Twilio API error {status_code}: {detail}")


class TwilioClient:
    """Cliente assíncrono para envio de mensagens WhatsApp via Twilio.

    Encapsula a autenticação e chamadas HTTP à Messages API do Twilio.
    Usa API Key (api_key_sid + api_key_secret) para autenticação outbound,
    separando de auth_token que é usado apenas para validação de assinatura
    inbound no webhook.

    Args:
        account_sid: Twilio Account SID (identifica a conta).
        api_key_sid: Twilio API Key SID (ex: SKxxxxxxxx).
        api_key_secret: Twilio API Key Secret.
        from_number: Número remetente no formato whatsapp:+XXXXXXXXXXX.

    Exemplo:
        >>> client = TwilioClient("AC...", "SK...", "secret", "whatsapp:+14155238886")
        >>> sid = await client.send_message("+5511999999999", "Olá!")
    """

    def __init__(
        self,
        account_sid: str,
        api_key_sid: str,
        api_key_secret: str,
        from_number: str,
        *,
        delivery_mode: str = "real",
    ):
        if delivery_mode not in {"real", "mock"}:
            raise ValueError(
                "delivery_mode deve ser 'real' ou 'mock', "
                f"recebido: {delivery_mode}"
            )

        if delivery_mode == "real":
            if not account_sid:
                raise ValueError("account_sid não pode ser vazio")
            if not api_key_sid:
                raise ValueError("api_key_sid não pode ser vazio")
            if not api_key_secret:
                raise ValueError("api_key_secret não pode ser vazio")
            if not from_number:
                raise ValueError("from_number não pode ser vazio")
            if not from_number.startswith("whatsapp:+"):
                raise ValueError(
                    "from_number deve iniciar com 'whatsapp:+', "
                    f"recebido: {from_number}"
                )

        self.account_sid = account_sid
        self.api_key_sid = api_key_sid
        self.api_key_secret = api_key_secret
        self.from_number = from_number
        self.delivery_mode = delivery_mode
        self.messages_url = TWILIO_MESSAGES_URL.format(account_sid=account_sid)

    async def send_message(self, to: str, body: str) -> str:
        """Envia mensagem WhatsApp via Twilio Messages API.

        Faz POST para /Messages.json com autenticação Basic Auth
        usando API Key (api_key_sid:api_key_secret).

        Args:
            to: Número destino em E.164 (ex: +5511999999999).
            body: Texto da mensagem a enviar.

        Returns:
            SID da mensagem criada no Twilio (ex: SMxxxxxxxx).

        Raises:
            TwilioSendError: Se a API retornar erro (4xx/5xx).
        """
        chunks = split_message_body(body)
        chunk_count = len(chunks)

        if chunk_count > 1:
            logger.info(
                "twilio_message_chunked",
                to=to,
                original_length=len(body),
                chunk_count=chunk_count,
            )

        if self.delivery_mode == "mock":
            last_sid = ""
            for idx, chunk in enumerate(chunks, start=1):
                last_sid = f"SM{uuid.uuid4().hex}"
                logger.info(
                    "twilio_message_mocked",
                    to=to,
                    sid=last_sid,
                    body_length=len(chunk),
                    chunk_index=idx,
                    chunk_count=chunk_count,
                )
            return last_sid

        last_sid = ""
        async with httpx.AsyncClient() as http:
            for idx, chunk in enumerate(chunks, start=1):
                response = await http.post(
                    self.messages_url,
                    auth=(self.api_key_sid, self.api_key_secret),
                    data={
                        "From": self.from_number,
                        "To": f"whatsapp:{to}",
                        "Body": chunk,
                    },
                    timeout=15.0,
                )

                if not response.is_success:
                    detail = response.text[:500]
                    logger.error(
                        "twilio_send_failed",
                        to=to,
                        status_code=response.status_code,
                        detail=detail,
                        chunk_index=idx,
                        chunk_count=chunk_count,
                        body_length=len(chunk),
                    )
                    raise TwilioSendError(response.status_code, detail)

                data = response.json()
                last_sid = data["sid"]

                logger.info(
                    "twilio_message_sent",
                    to=to,
                    sid=last_sid,
                    status=data.get("status"),
                    body_length=len(chunk),
                    chunk_index=idx,
                    chunk_count=chunk_count,
                )

        return last_sid

    async def send_typing(self, to: str, message_sid: str | None = None) -> bool:
        """Envia indicador de digitação via Twilio (Public Beta, out/2025).

        Usa o endpoint /v2/Indicators/Typing.json com dois parâmetros:
        - messageId: SID da mensagem inbound (SM... ou MM...)
        - channel: "whatsapp"

        Efeitos: marca a mensagem como lida (blue checkmarks) e exibe
        "digitando..." por até 25 segundos no WhatsApp do usuário.

        Args:
            to: Número destino em E.164 (usado apenas para logging).
            message_sid: SID da mensagem inbound sendo respondida.

        Returns:
            True se o indicador foi enviado, False caso contrário.
        """
        if self.delivery_mode == "mock":
            logger.debug("twilio_typing_skipped", to=to, reason="mock_mode")
            return False

        if not message_sid:
            logger.debug("twilio_typing_skipped", to=to, reason="no message_sid")
            return False
        if not TWILIO_MESSAGE_SID_RE.match(message_sid):
            logger.debug(
                "twilio_typing_skipped",
                to=to,
                message_sid=message_sid,
                reason="invalid_message_sid_format",
            )
            return False

        try:
            async with httpx.AsyncClient() as http:
                response = await http.post(
                    TWILIO_TYPING_URL,
                    auth=(self.api_key_sid, self.api_key_secret),
                    data={
                        "messageId": message_sid,
                        "channel": "whatsapp",
                    },
                    timeout=5.0,
                )

            if response.is_success:
                logger.info("twilio_typing_sent", to=to, message_sid=message_sid)
                return True

            logger.warning(
                "twilio_typing_failed",
                to=to,
                message_sid=message_sid,
                status_code=response.status_code,
                detail=response.text[:200],
            )
            return False
        except Exception as exc:
            logger.warning("twilio_typing_error", to=to, error=str(exc))
            return False


def split_message_body(
    body: str, limit: int = TWILIO_MESSAGE_BODY_LIMIT
) -> list[str]:
    """Divide mensagens longas em partes seguras para a API do Twilio.

    O Twilio rejeita corpos acima de 1600 caracteres no WhatsApp. A estratégia
    tenta quebrar em limites naturais (parágrafo, linha, espaço) antes de
    recorrer a corte bruto.
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
