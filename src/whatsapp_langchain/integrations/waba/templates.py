"""Templates HSM WhatsApp (Message Templates).

Submete pra Meta, sincroniza status, envia mensagens template-based, deleta.
Cada template é per-conexão (cada WABA tem sua própria namespace de templates).

Status mapping local → Meta event:
- draft → não submetido ainda
- pending → submetido, esperando review (até 24h)
- approved → APPROVED
- rejected → REJECTED (com motivo_rejeicao preenchido)
- disabled → DISABLED (Meta desativou — geralmente por baixa qualidade)
- paused → PAUSED (Meta pausou — quality_score=RED)
"""

from __future__ import annotations

import re
from typing import Any

import httpx
import structlog

from whatsapp_langchain.shared.config import settings

logger = structlog.get_logger()


WABA_GRAPH_BASE = "https://graph.facebook.com/{version}"


class WabaTemplateError(Exception):
    """Erro ao operar template via Meta Graph API."""

    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"WABA template error {status_code}: {detail}")


_VARIAVEL = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")


def texto_do_template(
    componentes: list[dict[str, Any]] | None, variables: dict[str, str] | None = None
) -> str:
    """O texto que o cliente vê no WhatsApp: cabeçalho, corpo e rodapé, com as
    variáveis (`{{1}}`, `{{nome}}`) já trocadas pelos valores enviados.

    É o que vai para a timeline — antes ficava só `[template nome] no
    variables` e o operador não sabia o que o cliente tinha recebido
    (24/09/2026). Variável sem valor fica como está (`{{2}}`); cabeçalho de
    mídia vira a linha `[imagem]`/`[vídeo]`/`[documento]`. Sem corpo → "".
    """
    valores = {str(k): str(v) for k, v in (variables or {}).items()}

    def _trocar(texto: str) -> str:
        return _VARIAVEL.sub(lambda m: valores.get(m.group(1), m.group(0)), texto)

    partes: dict[str, str] = {}
    for c in componentes or []:
        tipo = (c.get("type") or "").upper()
        if tipo == "HEADER":
            formato = (c.get("format") or "TEXT").upper()
            if formato == "TEXT" and c.get("text"):
                partes["HEADER"] = f"*{_trocar(str(c['text']))}*"
            elif formato in _MIDIA_CABECALHO:
                partes["HEADER"] = _MIDIA_CABECALHO[formato]
        elif tipo in ("BODY", "FOOTER") and c.get("text"):
            partes[tipo] = _trocar(str(c["text"]))
    if "BODY" not in partes:
        return ""
    if "FOOTER" in partes:
        partes["FOOTER"] = f"_{partes['FOOTER']}_"
    return "\n\n".join(partes[k] for k in ("HEADER", "BODY", "FOOTER") if k in partes)


_MIDIA_CABECALHO = {"IMAGE": "[imagem]", "VIDEO": "[vídeo]", "DOCUMENT": "[documento]"}


def _base() -> str:
    return WABA_GRAPH_BASE.format(version=settings.waba_graph_api_version)


async def submit_template(
    access_token: str,
    waba_account_id: str,
    *,
    nome: str,
    categoria: str,
    idioma: str,
    componentes_json: list[dict[str, Any]],
) -> dict[str, Any]:
    """POST /{waba_account_id}/message_templates → submete pra aprovação.

    Retorno: {"id": "<meta_template_id>", "status": "PENDING", "category": "..."}
    """
    url = f"{_base()}/{waba_account_id}/message_templates"
    payload = {
        "name": nome,
        "category": categoria,
        "language": idioma,
        "components": componentes_json,
    }
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code != 200:
            raise WabaTemplateError(resp.status_code, resp.text[:400])
        return resp.json()


async def sync_template_status(
    access_token: str,
    meta_template_id: str,
) -> dict[str, Any]:
    """GET /{meta_template_id} → status atual + quality_score + rejection_reason."""
    url = f"{_base()}/{meta_template_id}"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "fields": (
                    "name,status,category,language,quality_score,"
                    "rejected_reason,components"
                )
            },
        )
        if resp.status_code != 200:
            raise WabaTemplateError(resp.status_code, resp.text[:400])
        return resp.json()


async def list_remote_templates(
    access_token: str,
    waba_account_id: str,
    *,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """GET /{waba_account_id}/message_templates — todos os templates da WABA na Meta."""
    url = f"{_base()}/{waba_account_id}/message_templates"
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "limit": limit,
                "fields": "id,name,status,category,language,components,quality_score",
            },
        )
        if resp.status_code != 200:
            raise WabaTemplateError(resp.status_code, resp.text[:400])
        return resp.json().get("data", [])


async def send_template_message(
    access_token: str,
    phone_id: str,
    *,
    to: str,
    template_name: str,
    language: str,
    variables: dict[str, str] | None = None,
    button_payloads: dict[str, str] | None = None,
) -> str:
    """Envia mensagem usando template aprovado.

    `variables`: substitui {{1}}, {{2}}, ... no BODY (numerado, ordem importa).
    `button_payloads`: opcional, pra botões URL/QUICK_REPLY dinâmicos.

    Retorna message_id (wamid).
    """
    to_clean = "".join(c for c in to.lstrip("+") if c.isdigit())
    url = f"{_base()}/{phone_id}/messages"

    components: list[dict[str, Any]] = []

    if variables:
        # WhatsApp espera array ordenado de parâmetros pro BODY
        ordered_keys = sorted(
            variables.keys(), key=lambda k: int(k) if k.isdigit() else k
        )
        body_params = [
            {"type": "text", "text": str(variables[k])} for k in ordered_keys
        ]
        components.append({"type": "body", "parameters": body_params})

    if button_payloads:
        for idx, (btn_type, value) in enumerate(button_payloads.items()):
            components.append(
                {
                    "type": "button",
                    "sub_type": btn_type,
                    "index": str(idx),
                    "parameters": [{"type": "payload", "payload": value}],
                }
            )

    payload = {
        "messaging_product": "whatsapp",
        "to": to_clean,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {"code": language},
            "components": components,
        },
    }

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        if resp.status_code != 200:
            raise WabaTemplateError(resp.status_code, resp.text[:400])
        msgs = resp.json().get("messages", [])
        return msgs[0]["id"] if msgs else ""


async def delete_template(
    access_token: str,
    waba_account_id: str,
    template_name: str,
) -> bool:
    """DELETE /{waba_account_id}/message_templates?name={name}

    Meta exige passar o nome (não o id) pra delete. Apaga TODAS as línguas
    do template ao mesmo tempo.
    """
    url = f"{_base()}/{waba_account_id}/message_templates"
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.delete(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            params={"name": template_name},
        )
        return resp.status_code == 200
