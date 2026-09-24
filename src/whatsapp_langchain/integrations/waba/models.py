"""Schemas Pydantic da Meta Graph API (WABA Cloud)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class WabaPhoneNumber(BaseModel):
    """Um número WhatsApp dentro de uma WABA account."""

    id: str
    display_phone_number: str = Field(alias="display_phone_number")
    verified_name: str | None = None
    quality_rating: str | None = None  # GREEN/YELLOW/RED
    code_verification_status: str | None = None  # VERIFIED/NOT_VERIFIED


class WabaAccount(BaseModel):
    """WhatsApp Business Account (1 user pode ter N)."""

    id: str
    name: str
    timezone_id: str | None = None
    message_template_namespace: str | None = None
    phone_numbers: list[WabaPhoneNumber] = Field(default_factory=list)


class WabaCredentials(BaseModel):
    """Credenciais cifradas armazenadas em `conexao.credentials_encrypted`."""

    access_token: str  # System User token (long-lived)
    waba_account_id: str
    phone_id: str
    app_id: str | None = None
    account_description: str | None = None


class WabaEmbeddedSignupResult(BaseModel):
    """Resultado da troca code → token + listagem de accounts."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int | None = None
    accounts: list[WabaAccount]


class WabaInboundMessage(BaseModel):
    """Mensagem inbound normalizada (saída do parser de webhook)."""

    waba_phone_id: str  # phone_number_id da Meta
    from_number: str  # E.164
    message_id: str
    timestamp: datetime
    type: str  # text | image | audio | video | document | location | interactive
    text: str | None = None
    media_id: str | None = None  # pra download via /media/{id}
    media_mime_type: str | None = None
    media_caption: str | None = None
    # Só documento traz nome (`document.filename`). É o que escolhe o parser e
    # o que a resposta cita quando o conteúdo não pôde ser lido (mig 164).
    media_filename: str | None = None
    # Nome do perfil (`value.contacts[].profile.name`) — vai pro upsert_cliente.
    profile_name: str | None = None
    raw: dict[str, Any]  # payload completo pra fallback


class WabaTemplateComponent(BaseModel):
    """Um componente do template (HEADER/BODY/FOOTER/BUTTONS)."""

    type: str  # HEADER | BODY | FOOTER | BUTTONS
    format: str | None = None  # HEADER.format: TEXT/IMAGE/VIDEO/DOCUMENT
    text: str | None = None
    example: dict[str, Any] | None = None  # {"body_text": [["valor1"]]}
    buttons: list[dict[str, Any]] | None = None


class WabaTemplateInput(BaseModel):
    """Input pra criar/submeter template."""

    nome: str  # snake_case lowercase
    categoria: str  # UTILITY | AUTHENTICATION | MARKETING
    idioma: str = "pt_BR"
    componentes_json: list[dict[str, Any]]


class WabaTemplateRecord(BaseModel):
    """Row de waba_template, retornada pelos endpoints admin."""

    id: int
    empresa_id: int
    conexao_id: int
    nome: str
    categoria: str
    idioma: str
    componentes_json: list[dict[str, Any]]
    status: str  # draft | pending | approved | rejected | disabled | paused
    meta_template_id: str | None = None
    meta_quality_score: str | None = None
    motivo_rejeicao: str | None = None
    ultimo_sync_at: datetime | None = None
    created_at: datetime
    updated_at: datetime
    created_by_user_id: str | None = None
    # Sprint message templates — multi-provider (mig 109)
    provider: str = "waba"
    #: Coluna órfã desde a mig 153 — nada escreve mais aqui. Mantida porque
    #: as rotas leem a tupla por posição; DROP fica pra migration própria.
    content_sid: str | None = None


class WabaStatus(BaseModel):
    """Aviso de entrega de uma mensagem que a Cloud API enviou.

    Vem no campo `messages`, em `value.statuses[]`: `sent`, `delivered`,
    `read` ou `failed`. No `failed`, `errors[0]` traz o código e o motivo.
    """

    waba_phone_id: str
    message_id: str  # wamid da mensagem ENVIADA
    status: str  # sent | delivered | read | failed
    recipient_id: str | None = None
    erro_codigo: int | None = None
    erro_titulo: str | None = None
    erro_detalhe: str | None = None


class WabaEcho(BaseModel):
    """Mensagem que a empresa enviou pelo WhatsApp Business do CELULAR.

    Campo `smb_message_echoes` (Coexistence). `from` = número da empresa,
    `to` = cliente. Só dispara para o que saiu do app/dispositivo companheiro,
    nunca para o que a Cloud API enviou.
    """

    waba_phone_id: str
    to_number: str  # E.164 do cliente
    message_id: str
    timestamp: datetime
    type: str  # text | image | video | document | audio | sticker | revoke | edit | …
    text: str | None = None  # corpo do texto ou legenda da mídia


class WabaHistoricoMensagem(BaseModel):
    """Uma mensagem de uma conversa do histórico (campo `history`)."""

    message_id: str
    timestamp: datetime
    type: str
    text: str | None = None
    da_empresa: bool  # `from` == número da empresa → enviada pela empresa


class WabaHistoricoConversa(BaseModel):
    waba_phone_id: str
    cliente_number: str  # E.164 (`threads[].id`)
    mensagens: list[WabaHistoricoMensagem] = Field(default_factory=list)


class WabaHistoricoLote(BaseModel):
    """Um item de `history[]` — um pedaço (chunk) da sincronização."""

    waba_phone_id: str
    phase: int | None = None
    chunk_order: int | None = None
    progress: int | None = None
    conversas: list[WabaHistoricoConversa] = Field(default_factory=list)
    #: Códigos de erro do item (ex.: 2593109 = histórico recusado no app).
    erros: list[int] = Field(default_factory=list)


class WabaContato(BaseModel):
    """Contato do WhatsApp Business (campo `smb_app_state_sync`)."""

    waba_phone_id: str
    phone_number: str  # E.164
    nome: str | None = None
    action: str  # add | remove | …


class WabaAccountUpdate(BaseModel):
    """Evento `account_update` (ex.: PARTNER_REMOVED)."""

    waba_account_id: str  # `entry.id`
    event: str
    phone_number: str | None = None
    reason: str | None = None
    initiated_by: str | None = None
