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
from typing import Any, TypedDict

import httpx
import structlog

from whatsapp_langchain.worker.twilio_client import split_message_body

logger = structlog.get_logger()

EVOLUTION_SEND_TEXT_PATH = "/message/sendText/{instance}"
EVOLUTION_SEND_MEDIA_PATH = "/message/sendMedia/{instance}"
# Nota de voz tem endpoint PRÓPRIO. Mandar áudio por `sendMedia` chega como
# arquivo anexado, com ícone de documento e sem player — não como a bolha de
# áudio do WhatsApp.
EVOLUTION_SEND_AUDIO_PATH = "/message/sendWhatsAppAudio/{instance}"
EVOLUTION_SEND_PRESENCE_PATH = "/chat/sendPresence/{instance}"
# Editar e apagar mensagem já entregue (mig 172).
#
# Os dois contratos foram descobertos batendo na API v2.3.7, não deduzidos — e
# são ASSIMÉTRICOS: editar recebe a chave aninhada em `key`, apagar recebe os
# mesmos três campos soltos no topo. Deduzir "por simetria" daria 400.
#
#   POST   /chat/updateMessage/{instance}
#          {"number": ..., "text": ..., "key": {id, remoteJid, fromMe}}
#   DELETE /chat/deleteMessageForEveryone/{instance}
#          {"id": ..., "remoteJid": ..., "fromMe": true}
#
# Editar depende de a Evolution ter guardado a mensagem no banco DELA
# (`DATABASE_SAVE_DATA_NEW_MESSAGE`): o handler busca a original pra saber se é
# texto ou legenda de mídia, e sem ela devolve "Message not compatible".
# Conferido ligado em dev e produção.
EVOLUTION_UPDATE_MESSAGE_PATH = "/chat/updateMessage/{instance}"
EVOLUTION_DELETE_MESSAGE_PATH = "/chat/deleteMessageForEveryone/{instance}"
# Captura (Task 4) — endpoints REST da Evolution usados server-side.
EVOLUTION_CHECK_NUMBERS_PATH = "/chat/whatsappNumbers/{instance}"
EVOLUTION_FIND_CONTACTS_PATH = "/chat/findContacts/{instance}"
EVOLUTION_FETCH_GROUPS_PATH = "/group/fetchAllGroups/{instance}"
EVOLUTION_GROUP_PARTICIPANTS_PATH = "/group/participants/{instance}"
EVOLUTION_CONNECTION_STATE_PATH = "/instance/connectionState/{instance}"
# Quantos números validar por request em check_numbers (evita payload gigante).
EVOLUTION_CHECK_NUMBERS_CHUNK = 50


class WhatsAppNumber(TypedDict):
    """Resultado de validação de um número (onWhatsApp/exists)."""

    wa_jid: str
    telefone: str | None
    exists: bool


class CapturedContact(TypedDict):
    """Contato cru retornado pelo store da Evolution (antes de normalizar)."""

    wa_jid: str
    push_name: str | None
    name: str | None
    is_business: bool
    verified_name: str | None


class CapturedGroup(TypedDict):
    """Grupo cru retornado por fetchAllGroups."""

    wa_group_id: str
    nome: str | None
    descricao: str | None
    invite_link: str | None
    participantes_count: int
    somos_admin: bool


class CapturedGroupMember(TypedDict):
    """Membro de grupo (wa_jid pode ser @s.whatsapp.net ou @lid)."""

    wa_jid: str
    is_admin: bool


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


def phone_from_jid(jid: str) -> str | None:
    """Extrai telefone E.164 de um JID `@s.whatsapp.net`; None para `@lid`.

    Membros multi-device vêm como `<lid>@lid` sem telefone derivável — nesse
    caso retornamos None (o wa_jid continua sendo a identidade primária).
    """
    if not jid or "@s.whatsapp.net" not in jid:
        return None
    digits = "".join(c for c in jid.split("@", 1)[0] if c.isdigit())
    return f"+{digits}" if digits else None


def _contact_jid(c: dict) -> str:
    """Resolve o JID do WhatsApp de um contato da Evolution v2.

    O `/chat/findContacts` retorna registros da tabela Contact, onde `id` é o
    **cuid interno da Evolution** (ex: `cmq866i4j1wzjpn4x...`), NÃO o JID. O JID
    real fica em `remoteJid` (`5511...@s.whatsapp.net` ou `<lid>@lid`). Alguns
    builds expõem o número em `number`. Ordem: remoteJid → number → id (só se
    parecer JID). O cuid puro é descartado (não dá telefone).
    """
    remote = c.get("remoteJid") or c.get("jid")
    if remote and "@" in str(remote):
        return str(remote)
    number = c.get("number")
    if number:
        digits = "".join(ch for ch in str(number) if ch.isdigit())
        if digits:
            return f"{digits}@s.whatsapp.net"
    raw_id = str(c.get("id") or "")
    return raw_id if "@" in raw_id else ""


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
        self.update_message_url = (
            f"{self.api_url}"
            f"{EVOLUTION_UPDATE_MESSAGE_PATH.format(instance=instance_name)}"
            if api_url
            else ""
        )
        self.delete_message_url = (
            f"{self.api_url}"
            f"{EVOLUTION_DELETE_MESSAGE_PATH.format(instance=instance_name)}"
            if api_url
            else ""
        )

    async def editar_mensagem(
        self, to: str, provider_message_id: str, texto: str
    ) -> None:
        """Edita no WhatsApp do cliente uma mensagem já entregue (mig 172).

        Fora do Protocol `OutboundClient` de propósito: só a Evolution faz isso.
        A WABA recusa com "Method not available on WhatsApp Business API" (lido
        no binário v2.3.7), então quem chama usa `getattr` — mesmo padrão já
        adotado pra `send_audio` em `shared/outbound.py`.

        Quem decide se PODE editar é `shared/atendimento.avaliar_alteracao_resposta`
        (janela de 15 min, origem manual, provedor). Aqui só executa.

        Raises:
            EvolutionSendError: 4xx/5xx. O caso mais comum é 400 "Message not
                compatible", que significa que a Evolution não achou a mensagem
                original no banco dela — não que o texto novo seja inválido.
        """
        await self._alterar_mensagem(
            url=self.update_message_url,
            metodo="POST",
            # A chave vai ANINHADA aqui, e solta no apagar. Não é descuido:
            # é o contrato da API, verificado batendo nela.
            corpo={
                "number": normalize_to_number(to),
                "text": texto,
                "key": self._chave(to, provider_message_id),
            },
            evento="evolution_message_edited",
            to=to,
        )

    async def apagar_mensagem(self, to: str, provider_message_id: str) -> None:
        """Apaga para todos uma mensagem já entregue (mig 172).

        Mesmas ressalvas de `editar_mensagem`. A janela do WhatsApp aqui é bem
        maior (~2 dias contra 15 min), e quem corta é a camada de regra.
        """
        await self._alterar_mensagem(
            url=self.delete_message_url,
            metodo="DELETE",
            corpo=self._chave(to, provider_message_id),
            evento="evolution_message_deleted",
            to=to,
        )

    def _chave(self, to: str, provider_message_id: str) -> dict[str, Any]:
        """A tripla que identifica a mensagem no WhatsApp.

        `fromMe` é sempre True: só editamos/apagamos o que NÓS enviamos —
        mexer em mensagem do cliente não existe no WhatsApp.
        """
        return {
            "id": provider_message_id,
            "remoteJid": f"{normalize_to_number(to)}@s.whatsapp.net",
            "fromMe": True,
        }

    async def _alterar_mensagem(
        self,
        *,
        url: str,
        metodo: str,
        corpo: dict[str, Any],
        evento: str,
        to: str,
    ) -> None:
        """Tronco comum de editar e apagar: só mudam método, URL e corpo."""
        if self.delivery_mode == "mock":
            logger.info(f"{evento}_mocked", to=to, instance=self.instance_name)
            return

        async with httpx.AsyncClient() as http:
            response = await http.request(
                metodo,
                url,
                headers={"apikey": self.api_key},
                json=corpo,
                timeout=15.0,
            )

        if not response.is_success:
            detail = response.text[:500]
            logger.error(
                f"{evento}_failed",
                to=to,
                instance=self.instance_name,
                status_code=response.status_code,
                detail=detail,
            )
            raise EvolutionSendError(response.status_code, detail)

        logger.info(evento, to=to, instance=self.instance_name)

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

    async def send_media(
        self,
        to: str,
        media_url: str,
        *,
        mediatype: str = "image",
        caption: str | None = None,
        filename: str | None = None,
    ) -> str:
        """Envia mídia (imagem/vídeo/documento) via Evolution `/message/sendMedia`.

        `media_url` deve ser uma URL pública (o servidor Evolution busca o
        arquivo) OU base64. `caption` é a legenda. Retorna o id da mensagem;
        em mock mode retorna `mock-evo-media-<uuid>`.
        """
        normalized_to = normalize_to_number(to)
        if self.delivery_mode == "mock":
            mid = f"mock-evo-media-{uuid.uuid4().hex}"
            logger.info(
                "evolution_media_mocked",
                to=normalized_to,
                instance=self.instance_name,
                mediatype=mediatype,
                media_url=media_url[:80],
            )
            return mid

        payload: dict[str, str] = {
            "number": normalized_to,
            "mediatype": mediatype,
            "media": media_url,
        }
        if caption:
            payload["caption"] = caption
        if filename:
            payload["fileName"] = filename

        url = f"{self.api_url}{EVOLUTION_SEND_MEDIA_PATH.format(instance=self.instance_name)}"
        async with httpx.AsyncClient() as http:
            response = await http.post(
                url,
                headers={"apikey": self.api_key},
                json=payload,
                timeout=60.0,
            )
        if not response.is_success:
            detail = response.text[:500]
            logger.error(
                "evolution_media_failed",
                to=normalized_to,
                instance=self.instance_name,
                status_code=response.status_code,
                detail=detail,
                mediatype=mediatype,
            )
            raise EvolutionSendError(response.status_code, detail)
        data = response.json()
        key = data.get("key") or data.get("data", {}).get("key", {})
        mid = key.get("id", "") if isinstance(key, dict) else ""
        logger.info(
            "evolution_media_sent",
            to=normalized_to,
            instance=self.instance_name,
            message_id=mid,
            mediatype=mediatype,
        )
        return mid

    async def send_audio(self, to: str, audio: str) -> str:
        """Envia nota de voz via Evolution `/message/sendWhatsAppAudio`.

        Endpoint separado de `send_media` de propósito: o WhatsApp distingue
        "áudio anexado" de "nota de voz" (PTT), e só o segundo chega com a
        bolha de player e a forma de onda. Áudio mandado por `sendMedia`
        aparece como documento.

        `audio` aceita URL pública ou base64 — o app manda base64, porque o
        arquivo nasce no celular do operador e não tem URL.

        O formato precisa ser OGG/Opus: é o que o WhatsApp aceita como nota de
        voz. Quem grava é o app, e ele grava nesse formato.
        """
        normalized_to = normalize_to_number(to)
        if self.delivery_mode == "mock":
            mid = f"mock-evo-audio-{uuid.uuid4().hex}"
            logger.info(
                "evolution_audio_mocked",
                to=normalized_to,
                instance=self.instance_name,
            )
            return mid

        url = f"{self.api_url}{EVOLUTION_SEND_AUDIO_PATH.format(instance=self.instance_name)}"
        async with httpx.AsyncClient() as http:
            response = await http.post(
                url,
                headers={"apikey": self.api_key},
                json={"number": normalized_to, "audio": audio},
                timeout=60.0,
            )
        if not response.is_success:
            detail = response.text[:500]
            logger.error(
                "evolution_audio_failed",
                to=normalized_to,
                instance=self.instance_name,
                status_code=response.status_code,
                detail=detail,
            )
            raise EvolutionSendError(response.status_code, detail)
        data = response.json()
        key = data.get("key") or data.get("data", {}).get("key", {})
        mid = key.get("id", "") if isinstance(key, dict) else ""
        logger.info(
            "evolution_audio_sent",
            to=normalized_to,
            instance=self.instance_name,
            message_id=mid,
        )
        return mid

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
                # Evolution v2.3.x mudou o contrato: presence/delay vão no
                # nível raiz do body, não dentro de `options`. Versões
                # anteriores aceitavam ambos os formatos.
                response = await http.post(
                    self.send_presence_url,
                    headers={"apikey": self.api_key},
                    json={
                        "number": normalized_to,
                        "delay": EVOLUTION_TYPING_DELAY_MS,
                        "presence": "composing",
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

    # ------------------------------------------------------------------
    # Captura server-side (Task 4) — leitura do store da Evolution.
    # ------------------------------------------------------------------

    def _capture_url(self, path: str) -> str:
        return f"{self.api_url}{path.format(instance=self.instance_name)}"

    async def check_numbers(
        self, phones: list[str], chunk_size: int = EVOLUTION_CHECK_NUMBERS_CHUNK
    ) -> list[WhatsAppNumber]:
        """Valida quais números têm WhatsApp (onWhatsApp/exists), em lotes.

        Usado pelo resolver do disparo (Task 6) pra marcar inválidos ANTES de
        enviar — disparar pra muitos números mortos acelera ban. Em mock, assume
        que todos existem (não bloqueia testes locais).
        """
        if self.delivery_mode == "mock":
            return [
                WhatsAppNumber(
                    wa_jid=f"{normalize_to_number(p)}@s.whatsapp.net",
                    telefone=f"+{normalize_to_number(p)}",
                    exists=True,
                )
                for p in phones
            ]
        out: list[WhatsAppNumber] = []
        async with httpx.AsyncClient() as http:
            for i in range(0, len(phones), chunk_size):
                chunk = [normalize_to_number(p) for p in phones[i : i + chunk_size]]
                resp = await http.post(
                    self._capture_url(EVOLUTION_CHECK_NUMBERS_PATH),
                    headers={"apikey": self.api_key},
                    json={"numbers": chunk},
                    timeout=30.0,
                )
                if not resp.is_success:
                    raise EvolutionSendError(resp.status_code, resp.text[:500])
                for item in resp.json() or []:
                    jid = item.get("jid") or ""
                    out.append(
                        WhatsAppNumber(
                            wa_jid=jid,
                            telefone=item.get("number") or phone_from_jid(jid),
                            exists=bool(item.get("exists")),
                        )
                    )
        return out

    async def fetch_contacts(self) -> list[CapturedContact]:
        """Lista contatos do store (POST /chat/findContacts). Mock → []."""
        if self.delivery_mode == "mock":
            return []
        async with httpx.AsyncClient() as http:
            resp = await http.post(
                self._capture_url(EVOLUTION_FIND_CONTACTS_PATH),
                headers={"apikey": self.api_key},
                json={},
                timeout=60.0,
            )
            if not resp.is_success:
                raise EvolutionSendError(resp.status_code, resp.text[:500])
            data = resp.json() or []
        out: list[CapturedContact] = []
        for c in data:
            jid = _contact_jid(c)
            if not jid:
                continue
            verified = c.get("verifiedName")
            out.append(
                CapturedContact(
                    wa_jid=jid,
                    push_name=c.get("pushName"),
                    name=c.get("name"),
                    is_business=verified is not None,
                    verified_name=verified,
                )
            )
        return out

    async def fetch_groups(self, get_participants: bool = True) -> list[CapturedGroup]:
        """Lista grupos (GET /group/fetchAllGroups). Mock → []."""
        if self.delivery_mode == "mock":
            return []
        params = {"getParticipants": "true" if get_participants else "false"}
        async with httpx.AsyncClient() as http:
            resp = await http.get(
                self._capture_url(EVOLUTION_FETCH_GROUPS_PATH),
                headers={"apikey": self.api_key},
                params=params,
                timeout=60.0,
            )
            if not resp.is_success:
                raise EvolutionSendError(resp.status_code, resp.text[:500])
            data = resp.json() or []
        out: list[CapturedGroup] = []
        for g in data:
            jid = g.get("id") or ""
            if not jid:
                continue
            parts = g.get("participants") or []
            invite_code = g.get("inviteCode")
            out.append(
                CapturedGroup(
                    wa_group_id=jid,
                    nome=g.get("subject"),
                    descricao=g.get("desc") or g.get("description"),
                    invite_link=(
                        f"https://chat.whatsapp.com/{invite_code}"
                        if invite_code
                        else None
                    ),
                    participantes_count=int(g.get("size") or len(parts)),
                    somos_admin=False,
                )
            )
        return out

    async def fetch_group_participants(
        self, group_jid: str
    ) -> list[CapturedGroupMember]:
        """Lista membros de um grupo (GET /group/participants). Mock → []."""
        if self.delivery_mode == "mock":
            return []
        async with httpx.AsyncClient() as http:
            resp = await http.get(
                self._capture_url(EVOLUTION_GROUP_PARTICIPANTS_PATH),
                headers={"apikey": self.api_key},
                params={"groupJid": group_jid},
                timeout=60.0,
            )
            if not resp.is_success:
                raise EvolutionSendError(resp.status_code, resp.text[:500])
            data = resp.json()
        parts = data.get("participants") if isinstance(data, dict) else data
        out: list[CapturedGroupMember] = []
        for p in parts or []:
            jid = p.get("id") or ""
            if not jid:
                continue
            out.append(
                CapturedGroupMember(
                    wa_jid=jid,
                    is_admin=p.get("admin") in ("admin", "superadmin"),
                )
            )
        return out

    async def health(self) -> dict:
        """Estado da conexão (GET /instance/connectionState). Mock → aberto."""
        if self.delivery_mode == "mock":
            return {"state": "open", "mock": True}
        async with httpx.AsyncClient() as http:
            resp = await http.get(
                self._capture_url(EVOLUTION_CONNECTION_STATE_PATH),
                headers={"apikey": self.api_key},
                timeout=10.0,
            )
            if not resp.is_success:
                raise EvolutionSendError(resp.status_code, resp.text[:500])
            return resp.json()
