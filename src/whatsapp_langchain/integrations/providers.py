"""Catálogo de providers de integração suportados.

Cada provider tem:
- slug, nome, descricao, icone (lucide)
- auth_type: api_key, bearer, basic, oauth2_password, oauth2_client_credentials,
  oauth2_web (legacy), dynamic (custom user-driven)
- campos: lista de FieldSpec que a UI renderiza no form
- base_url_default: pode ser substituído pelo user
- legacy_storage: providers que JÁ existem com storage próprio
  (`wareline_credentials`, `empresa_calendar_config`) — UI mostra como
  read-only redirect pro card legacy

Adicionar provider novo = entrada nova nesse dict. UI auto-atualiza.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

AuthType = Literal[
    "api_key",
    "bearer",
    "basic",
    "oauth2_password",
    "oauth2_client_credentials",
    "oauth2_web",
    "dynamic",  # user escolhe no form (provider custom)
]

FieldType = Literal["text", "password", "url", "select", "textarea", "number"]


class FieldSpec(BaseModel):
    """1 campo do form do provider."""

    name: str
    label: str
    type: FieldType = "text"
    required: bool = True
    placeholder: str | None = None
    default: str | None = None
    help_text: str | None = None
    options: list[str] | None = None  # pra type=select
    sensitive: bool = False  # password/secret — mascarar no GET


class ProviderSpec(BaseModel):
    """Definição de 1 provider no catálogo."""

    slug: str
    nome: str
    descricao: str
    icone: str = "Plug"  # lucide icon name
    auth_type: AuthType
    campos: list[FieldSpec] = Field(default_factory=list)
    base_url_default: str | None = None
    docs_url: str | None = None
    # Quando preenchido, UI mostra link em vez de form (storage separado).
    # Ex: "wareline" → wareline-card.tsx, "google_calendar" → google card.
    legacy_storage: str | None = None


PROVIDERS: dict[str, ProviderSpec] = {
    "wareline": ProviderSpec(
        slug="wareline",
        nome="Wareline ConecteHub",
        descricao="Sistema de agendamento médico (OAuth2 password grant).",
        icone="CalendarCheck",
        auth_type="oauth2_password",
        campos=[
            FieldSpec(name="username", label="Username", required=True),
            FieldSpec(
                name="password",
                label="Senha",
                type="password",
                required=True,
                sensitive=True,
            ),
            FieldSpec(name="client_id", label="Client ID", required=True),
            FieldSpec(
                name="client_secret",
                label="Client Secret",
                type="password",
                required=True,
                sensitive=True,
            ),
        ],
        base_url_default="https://modulos.conectew.com.br",
        legacy_storage="wareline_credentials",
    ),
    "google_calendar": ProviderSpec(
        slug="google_calendar",
        nome="Google Calendar",
        descricao="Agendamento via Google Calendar (OAuth2 Web flow).",
        icone="Calendar",
        auth_type="oauth2_web",
        campos=[],  # OAuth Web é via redirect, sem campos manuais
        legacy_storage="empresa_calendar_config",
    ),
    # Asaas REMOVIDO do catálogo Wareline (2026-05-22).
    # Asaas é integração GLOBAL do SaaS (Chat Nexus → conta Asaas única
    # pra faturar empresas-clientes), não integração POR-EMPRESA. UI
    # dedicada em /billing (Sprint B), config via env vars ASAAS_API_KEY
    # + ASAAS_WEBHOOK_TOKEN. Não faz sentido cada empresa cadastrar API
    # key Asaas própria — quem paga é a empresa pro Chat Nexus.
    "custom": ProviderSpec(
        slug="custom",
        nome="API customizada",
        descricao=(
            "Conecte qualquer API REST genérica. Você fornece URL + tipo de "
            "autenticação. Útil pra integrações pontuais (webhook, BI, etc.) "
            "que ainda não têm provider dedicado."
        ),
        icone="Plug",
        auth_type="dynamic",
        campos=[
            FieldSpec(
                name="base_url",
                label="Base URL",
                type="url",
                required=True,
                placeholder="https://api.exemplo.com.br/v1",
            ),
            FieldSpec(
                name="auth_method",
                label="Tipo de autenticação",
                type="select",
                required=True,
                options=["none", "bearer", "basic", "api_key_header"],
                default="bearer",
            ),
            FieldSpec(
                name="token",
                label="Token / Senha / API Key",
                type="password",
                required=False,
                sensitive=True,
                help_text=(
                    "Bearer: o JWT. Basic: a senha (username separado abaixo). "
                    "API Key: o valor que vai no header."
                ),
            ),
            FieldSpec(
                name="username",
                label="Username (apenas Basic)",
                required=False,
            ),
            FieldSpec(
                name="header_name",
                label="Nome do header (apenas API Key)",
                required=False,
                default="X-API-Key",
            ),
        ],
    ),
}


def get_provider(slug: str) -> ProviderSpec | None:
    """Busca no catálogo. None se desconhecido."""
    return PROVIDERS.get(slug)


def list_providers(include_legacy: bool = True) -> list[ProviderSpec]:
    """Lista providers do catálogo. Quando include_legacy=False, omite
    Wareline+Google Calendar (que têm UI dedicada)."""
    out = list(PROVIDERS.values())
    if not include_legacy:
        out = [p for p in out if p.legacy_storage is None]
    return out


def validate_credentials_dict(
    provider_slug: str, credentials: dict
) -> tuple[bool, str | None]:
    """Valida que `credentials` tem todos os campos required do provider.
    Retorna (ok, mensagem_de_erro)."""
    provider = get_provider(provider_slug)
    if provider is None:
        return False, f"Provider '{provider_slug}' desconhecido."
    missing: list[str] = []
    for field in provider.campos:
        if not field.required:
            continue
        val = credentials.get(field.name)
        if val is None or (isinstance(val, str) and not val.strip()):
            missing.append(field.label)
    if missing:
        return False, f"Campos obrigatórios faltando: {', '.join(missing)}"
    return True, None
