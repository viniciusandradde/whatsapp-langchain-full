"""Cliente assíncrono para envio de mensagens WhatsApp via Evolution API.

Evolution API é uma alternativa open-source não-oficial baseada em Baileys.
Usa httpx para chamadas não-bloqueantes ao endpoint REST da instância.
Autenticação por header `apikey` (compartilhada entre inbound e outbound).

Em desenvolvimento local, o cliente também suporta `delivery_mode="mock"`,
que simula o envio outbound sem chamar a API real.

Uso:
    from whatsapp_langchain.worker.evolution_client import EvolutionClient

    client = EvolutionClient(
        api_url="https://evolutionapi.exemplo.com.br",
        api_key="6B46C86D...",
        instance_name="vsa-tecnologia",
    )
    msg_id = await client.send_message(to="+5511...", body="Olá!")
    await client.send_typing(to="+5511...")
"""

import uuid

import httpx
import structlog

from whatsapp_langchain.worker.twilio_client import split_message_body

logger = structlog.get_logger()

EVOLUTION_SEND_TEXT_PATH = "/message/sendText/{instance}"
EVOLUTION_SEND_PRESENCE_PATH = "/chat/sendPresence/{instance}"
# Mesmo limite seguro do Twilio — Evolution não documenta corte rígido,
# mas mantemos splitting universal pra evitar truncamento server-side.
EVOLUTION_MESSAGE_BODY_LIMIT = 1600
# Duração default do indicador de digitação (ms). Curto o suficiente pra
# não travar a UX se o envio outbound atrasar; o WhatsApp para de exibir
# após esse intervalo.
EVOLUTION_TYPING_DELAY_MS = 3000


class EvolutionSendError(Exception):
    """Erro ao enviar mensagem via Evolution API.

    Encapsula status HTTP e body de erro para facilitar diagnóstico.
    """

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"Evolution API error {status_code}: {detail}")


def normalize_to_number(to: str) -> str:
    """Normaliza número destino pra formato Evolution (só dígitos).

    Evolution espera o número no formato `5511999999999` — sem `+`,
    sem prefixo `whatsapp:`. O método aceita qualquer um desses
    formatos comuns no projeto e retorna apenas dígitos.

    Args:
        to: Número em qualquer formato (`+5511...`, `whatsapp:+5511...`).

    Returns:
        Número só com dígitos (ex: `5511999999999`).
    """
    cleaned = to.strip()
    if cleaned.startswith("whatsapp:"):
        cleaned = cleaned[len("whatsapp:") :]
    cleaned = cleaned.lstrip("+")
    return "".join(c for c in cleaned if c.isdigit())


class EvolutionClient:
    """Cliente assíncrono para envio de mensagens WhatsApp via Evolution API.

    Multi-instância: cada `EvolutionClient` é vinculado a uma instância
    específica (ex: `vsa-tecnologia`). Para empresas com múltiplas
    instâncias, instanciar um cliente por instância — o worker resolve
    via `conexao.payload_json.instance_name`.

    Args:
        api_url: Base URL da Evolution API (sem trailing slash).
        api_key: Chave global da Evolution (header `apikey`).
        instance_name: Nome da instância dentro da Evolution.
        delivery_mode: `real` (HTTP de fato) ou `mock` (log only).

    Exemplo:
        >>> client = EvolutionClient(
        ...     "https://evolutionapi.exemplo.com.br",
        ...     "6B46C86D...",
        ...     "vsa-tecnologia",
        ... )
        >>> msg_id = await client.send_message("+5511999999999", "Olá!")
    """

    def __init__(
        self,
        api_url: str,
        api_key: str,
        instance_name: str,
        *,
        delivery_mode: str = "real",
    ):
        if delivery_mode not in {"real", "mock"}:
            raise ValueError(
                f"delivery_mode deve ser 'real' ou 'mock', recebido: {delivery_mode}"
            )

        if delivery_mode == "real":
            if not api_url:
                raise ValueError("api_url não pode ser vazio")
            if not api_key:
                raise ValueError("api_key não pode ser vazio")
            if not instance_name:
                raise ValueError("instance_name não pode ser vazio")

        self.api_url = api_url.rstrip("/") if api_url else ""
        self.api_key = api_key
        self.instance_name = instance_name
        self.delivery_mode = delivery_mode
        self.send_text_url = (
            f"{self.api_url}{EVOLUTION_SEND_TEXT_PATH.format(instance=instance_name)}"
            if api_url
            else ""
        )
        self.send_presence_url = (
            f"{self.api_url}"
            f"{EVOLUTION_SEND_PRESENCE_PATH.format(instance=instance_name)}"
            if api_url
            else ""
        )

    async def send_message(self, to: str, body: str) -> str:
        """Envia mensagem WhatsApp via Evolution API.

        Faz POST para `/message/sendText/{instance}` com header `apikey`
        e body JSON `{"number": <só-dígitos>, "text": <chunk>}`.

        Args:
            to: Número destino em qualquer formato (E.164, whatsapp:+...).
            body: Texto da mensagem a enviar.

        Returns:
            ID da última mensagem retornado pela Evolution
            (`data.key.id` ou `key.id` no payload de resposta).
            Em mock mode retorna `mock-evo-<uuid>`.

        Raises:
            EvolutionSendError: Se a API retornar erro (4xx/5xx).
        """
        normalized_to = normalize_to_number(to)
        chunks = split_message_body(body, limit=EVOLUTION_MESSAGE_BODY_LIMIT)
        chunk_count = len(chunks)

        if chunk_count > 1:
            logger.info(
                "evolution_message_chunked",
                to=normalized_to,
                instance=self.instance_name,
                original_length=len(body),
                chunk_count=chunk_count,
            )

        if self.delivery_mode == "mock":
            last_id = ""
            for idx, chunk in enumerate(chunks, start=1):
                last_id = f"mock-evo-{uuid.uuid4().hex}"
                logger.info(
                    "evolution_message_mocked",
                    to=normalized_to,
                    instance=self.instance_name,
                    message_id=last_id,
                    body_length=len(chunk),
                    chunk_index=idx,
                    chunk_count=chunk_count,
                )
            return last_id

        last_id = ""
        async with httpx.AsyncClient() as http:
            for idx, chunk in enumerate(chunks, start=1):
                response = await http.post(
                    self.send_text_url,
                    headers={"apikey": self.api_key},
                    json={"number": normalized_to, "text": chunk},
                    timeout=15.0,
                )

                if not response.is_success:
                    detail = response.text[:500]
                    logger.error(
                        "evolution_send_failed",
                        to=normalized_to,
                        instance=self.instance_name,
                        status_code=response.status_code,
                        detail=detail,
                        chunk_index=idx,
                        chunk_count=chunk_count,
                        body_length=len(chunk),
                    )
                    raise EvolutionSendError(response.status_code, detail)

                data = response.json()
                # Evolution retorna `key.id` no nível raiz ou em `data.key.id`
                key = data.get("key") or data.get("data", {}).get("key", {})
                last_id = key.get("id", "") if isinstance(key, dict) else ""

                logger.info(
                    "evolution_message_sent",
                    to=normalized_to,
                    instance=self.instance_name,
                    message_id=last_id,
                    status=data.get("status"),
                    body_length=len(chunk),
                    chunk_index=idx,
                    chunk_count=chunk_count,
                )

        return last_id

    async def send_typing(self, to: str, message_id: str | None = None) -> bool:
        """Envia indicador de digitação via Evolution API (best-effort).

        Faz POST para `/chat/sendPresence/{instance}` com body
        `{"number": <só-dígitos>, "presence": "composing"}`. Falha
        nunca levanta exceção — typing é decoração, não pode derrubar
        o pipeline.

        Args:
            to: Número destino em qualquer formato.
            message_id: Ignorado (Evolution não correlaciona presence
                com mensagem específica; aceito pra compatibilidade
                com o protocolo `OutboundClient`).

        Returns:
            True se o indicador foi enviado, False caso contrário.
        """
        if self.delivery_mode == "mock":
            logger.debug(
                "evolution_typing_skipped",
                to=to,
                instance=self.instance_name,
                reason="mock_mode",
            )
            return False

        normalized_to = normalize_to_number(to)
        try:
            async with httpx.AsyncClient() as http:
                response = await http.post(
                    self.send_presence_url,
                    headers={"apikey": self.api_key},
                    json={
                        "number": normalized_to,
                        "options": {
                            "delay": EVOLUTION_TYPING_DELAY_MS,
                            "presence": "composing",
                            "number": normalized_to,
                        },
                    },
                    timeout=5.0,
                )

            if response.is_success:
                logger.info(
                    "evolution_typing_sent",
                    to=normalized_to,
                    instance=self.instance_name,
                )
                return True

            logger.warning(
                "evolution_typing_failed",
                to=normalized_to,
                instance=self.instance_name,
                status_code=response.status_code,
                detail=response.text[:200],
            )
            return False
        except Exception as exc:
            logger.warning(
                "evolution_typing_error",
                to=normalized_to,
                instance=self.instance_name,
                error=str(exc),
            )
            return False
