"""Cliente HTTP da OpenRouter para CHAVES (ADR-007).

Dois conjuntos de chamadas, com credenciais diferentes:

- `consultar_chave(chave)` — `GET /api/v1/key` autenticado com a PRÓPRIA
  chave a conferir. Valida uma chave que a empresa trouxe (Opção A) e devolve
  rótulo, limite e uso. Chave inválida → `ChaveInvalidaError`.
- `criar_chave` / `consultar_chave_gerida` / `atualizar_chave_gerida` /
  `apagar_chave_gerida` — API de gestão (`/api/v1/keys`), autenticada com a
  chave de provisionamento da plataforma (`OPENROUTER_PROVISIONING_KEY`).
  A chave criada só vem UMA vez na resposta (`key`); depois só o `hash`.

Nada aqui loga a chave: os logs levam só o prefixo mascarado. As respostas
da OpenRouter são lidas com tolerância (`data` presente ou não) porque a
documentação da API de gestão muda com frequência.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from whatsapp_langchain.shared.config import settings

logger = structlog.get_logger()

_TIMEOUT = 20.0


class OpenRouterGestaoError(Exception):
    """Falha de rede ou resposta inesperada da OpenRouter."""


class ChaveInvalidaError(OpenRouterGestaoError):
    """A OpenRouter recusou a chave (401/403) ou ela não tem o formato esperado."""


class ProvisionamentoNaoConfiguradoError(OpenRouterGestaoError):
    """`OPENROUTER_PROVISIONING_KEY` não está configurada na plataforma."""


@dataclass(frozen=True)
class InfoChave:
    """O que a OpenRouter conta sobre uma chave (sem a chave)."""

    label: str | None
    limite_usd: float | None
    limite_restante_usd: float | None
    uso_usd: float
    uso_mes_usd: float | None
    gratuita: bool
    desativada: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "limite_usd": self.limite_usd,
            "limite_restante_usd": self.limite_restante_usd,
            "uso_usd": self.uso_usd,
            "uso_mes_usd": self.uso_mes_usd,
            "gratuita": self.gratuita,
            "desativada": self.desativada,
        }


@dataclass(frozen=True)
class ChaveCriada:
    chave: str
    hash: str
    nome: str
    limite_usd: float | None


def mascarar(chave: str) -> str:
    """`sk-or-v1-abc…`: o bastante para reconhecer, nunca para usar."""
    chave = (chave or "").strip()
    if len(chave) <= 16:
        return "…"
    return f"{chave[:12]}…"


def formato_plausivel(chave: str) -> bool:
    """Chaves da OpenRouter começam com `sk-or-`. Barra colagem errada (token
    da Meta, chave da OpenAI) ANTES de gastar uma chamada de rede."""
    c = (chave or "").strip()
    return c.startswith("sk-or-") and 20 <= len(c) <= 200 and " " not in c


def _base() -> str:
    return settings.openrouter_base_url.rstrip("/")


def _num(v: Any) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _info_de(data: dict[str, Any]) -> InfoChave:
    return InfoChave(
        label=data.get("label") or data.get("name"),
        limite_usd=_num(data.get("limit")),
        limite_restante_usd=_num(data.get("limit_remaining")),
        uso_usd=_num(data.get("usage")) or 0.0,
        uso_mes_usd=_num(data.get("usage_monthly")),
        gratuita=bool(data.get("is_free_tier", False)),
        desativada=bool(data.get("disabled", False)),
    )


def _dados(corpo: Any) -> dict[str, Any]:
    if isinstance(corpo, dict):
        inner = corpo.get("data")
        if isinstance(inner, dict):
            return inner
        return corpo
    return {}


async def consultar_chave(chave: str, *, timeout: float = _TIMEOUT) -> InfoChave:
    """`GET /key` com a própria chave: prova que ela existe e está ativa."""
    if not formato_plausivel(chave):
        raise ChaveInvalidaError(
            "A chave não tem o formato da OpenRouter (começa com sk-or-)."
        )
    headers = {"Authorization": f"Bearer {chave.strip()}"}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(f"{_base()}/key", headers=headers)
    except (httpx.HTTPError, OSError) as exc:
        raise OpenRouterGestaoError(
            "Não foi possível falar com a OpenRouter agora."
        ) from exc
    if resp.status_code in (401, 403):
        raise ChaveInvalidaError("A OpenRouter não reconheceu esta chave.")
    if resp.status_code != 200:
        logger.warning(
            "openrouter_consultar_chave_falhou",
            status=resp.status_code,
            prefixo=mascarar(chave),
        )
        raise OpenRouterGestaoError(
            f"A OpenRouter respondeu {resp.status_code} ao conferir a chave."
        )
    try:
        corpo = resp.json()
    except ValueError as exc:
        raise OpenRouterGestaoError("Resposta inesperada da OpenRouter.") from exc
    return _info_de(_dados(corpo))


# --- API de gestão (chave de provisionamento da plataforma) ---------------


def provisionamento_configurado() -> bool:
    return settings.openrouter_provisioning_key is not None


def _headers_gestao() -> dict[str, str]:
    chave = settings.openrouter_provisioning_key
    if chave is None:
        raise ProvisionamentoNaoConfiguradoError(
            "O provisionamento de chaves não está configurado na plataforma."
        )
    return {
        "Authorization": f"Bearer {chave.get_secret_value()}",
        "Content-Type": "application/json",
    }


async def _gestao(
    metodo: str, caminho: str, *, json: dict[str, Any] | None = None
) -> tuple[int, Any]:
    headers = _headers_gestao()
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.request(
                metodo, f"{_base()}/keys{caminho}", headers=headers, json=json
            )
    except (httpx.HTTPError, OSError) as exc:
        raise OpenRouterGestaoError(
            "Não foi possível falar com a OpenRouter agora."
        ) from exc
    corpo: Any = None
    if resp.content:
        try:
            corpo = resp.json()
        except ValueError:
            corpo = None
    return resp.status_code, corpo


def _checar(status: int, corpo: Any, *, acao: str) -> None:
    if 200 <= status < 300:
        return
    if status in (401, 403):
        raise ProvisionamentoNaoConfiguradoError(
            "A OpenRouter recusou a chave de gestão da plataforma."
        )
    detalhe = ""
    if isinstance(corpo, dict):
        err = corpo.get("error")
        if isinstance(err, dict):
            detalhe = str(err.get("message") or "")[:200]
        elif isinstance(err, str):
            detalhe = err[:200]
    logger.warning(
        "openrouter_gestao_falhou", acao=acao, status=status, detalhe=detalhe
    )
    raise OpenRouterGestaoError(f"A OpenRouter respondeu {status} ao {acao}.")


async def criar_chave(*, nome: str, limite_usd: float | None) -> ChaveCriada:
    """`POST /keys`. A chave em claro só existe nesta resposta."""
    corpo_req: dict[str, Any] = {"name": nome}
    if limite_usd is not None:
        corpo_req["limit"] = float(limite_usd)
    status, corpo = await _gestao("POST", "", json=corpo_req)
    _checar(status, corpo, acao="criar a chave")
    data = _dados(corpo)
    chave = None
    if isinstance(corpo, dict):
        chave = corpo.get("key") or data.get("key")
    hash_ = data.get("hash")
    if not chave or not hash_:
        logger.error(
            "openrouter_criar_chave_resposta_incompleta", campos=sorted(data.keys())
        )
        raise OpenRouterGestaoError(
            "A OpenRouter criou a chave mas não devolveu o que era esperado."
        )
    return ChaveCriada(
        chave=str(chave),
        hash=str(hash_),
        nome=str(data.get("name") or nome),
        limite_usd=_num(data.get("limit")) if "limit" in data else limite_usd,
    )


async def consultar_chave_gerida(hash_: str) -> InfoChave:
    status, corpo = await _gestao("GET", f"/{hash_}")
    _checar(status, corpo, acao="consultar a chave")
    return _info_de(_dados(corpo))


async def atualizar_chave_gerida(
    hash_: str, *, limite_usd: float | None, desativada: bool | None = None
) -> InfoChave:
    """`PATCH /keys/{hash}`. `limite_usd=None` tira o limite."""
    corpo_req: dict[str, Any] = {
        "limit": float(limite_usd) if limite_usd is not None else None
    }
    if desativada is not None:
        corpo_req["disabled"] = desativada
    status, corpo = await _gestao("PATCH", f"/{hash_}", json=corpo_req)
    _checar(status, corpo, acao="alterar a chave")
    return _info_de(_dados(corpo))


async def apagar_chave_gerida(hash_: str) -> bool:
    """`DELETE /keys/{hash}`. 404 conta como já apagada (idempotente)."""
    status, corpo = await _gestao("DELETE", f"/{hash_}")
    if status == 404:
        return True
    _checar(status, corpo, acao="apagar a chave")
    return True
