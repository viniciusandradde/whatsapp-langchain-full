"""Chave da OpenRouter por empresa (ADR-007, mig 204).

Padrão (Opção 0): tudo sai pela chave da plataforma (`OPENROUTER_API_KEY`).
Opção A: a empresa traz a própria chave (`origem = propria`).
Opção B: a plataforma cria uma chave exclusiva para ela pela API de gestão
da OpenRouter, com limite de crédito (`origem = provisionada`).

Como a chave chega a quem chama a OpenRouter
--------------------------------------------
Um `ContextVar` por task. Quem abre o escopo da empresa carrega a chave e a
põe no contexto:

- worker: `_processar_mensagem` (uma mensagem = uma task) via
  `chave_da_empresa(pool, empresa_id)`;
- API: `openrouter_chave_middleware` a partir da empresa ativa do RLS;
- rota que age numa empresa diferente da ativa (superadmin editando outra):
  `chave_da_empresa` explícito no handler.

E os pontos de chamada (`llm.create_chat_model`, mídia, OCR, voz, embeddings)
leem `chave_openrouter()`: a da empresa se houver, senão a da plataforma.
A assinatura de `build_graph` (contrato dos agentes) não muda.

Cache de 60 s por processo: a chave é lida do banco no máximo uma vez por
minuto por empresa. Trocar a chave pelo painel limpa o cache do processo da
API; o worker pega em até 60 s.

Chave ilegível (cifra trocada) cai na chave da plataforma com log de erro —
o agente não cala por um problema de configuração da plataforma. Chave
inválida NA OpenRouter não cai: a chamada falha e a empresa é avisada pelo
caminho normal de erro (a plataforma não paga sem saber).
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Final

import structlog
from psycopg_pool import AsyncConnectionPool
from pydantic import SecretStr

from whatsapp_langchain.integrations import openrouter_gestao as gestao
from whatsapp_langchain.integrations.crypto import (
    IntegracaoConfigError,
    decrypt_str,
    encrypt_str,
)
from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.rls_context import empresa_scope

logger = structlog.get_logger()

ORIGEM_PROPRIA = "propria"
ORIGEM_PROVISIONADA = "provisionada"

_chave_var: Final[ContextVar[str | None]] = ContextVar(
    "openrouter_chave_empresa", default=None
)

_CACHE_TTL_S = 60.0
_cache: dict[int, tuple[float, str | None]] = {}


class ChaveNaoGeridaError(Exception):
    """A operação só vale para chave criada pela plataforma (provisionada)."""


# --- leitura no ponto de chamada -------------------------------------------


def chave_openrouter() -> SecretStr | None:
    """Chave a usar AGORA: a da empresa no contexto, senão a da plataforma."""
    propria = _chave_var.get()
    if propria:
        return SecretStr(propria)
    return settings.openrouter_api_key


def chave_openrouter_tts() -> SecretStr | None:
    """Voz: a chave da empresa vale também para o TTS; sem ela, a dedicada da
    plataforma (`OPENROUTER_TTS_API_KEY`) ou a geral."""
    propria = _chave_var.get()
    if propria:
        return SecretStr(propria)
    return settings.resolved_tts_api_key


def chave_e_da_empresa() -> bool:
    """True quando a chamada em curso sai por chave da empresa (não da plataforma)."""
    return bool(_chave_var.get())


@contextmanager
def usar_chave(chave: str | None):
    """Põe (ou tira, com None) a chave da empresa no contexto da task."""
    anterior = _chave_var.get()
    _chave_var.set(chave or None)
    try:
        yield
    finally:
        _chave_var.set(anterior)


def limpar_cache(empresa_id: int | None = None) -> None:
    if empresa_id is None:
        _cache.clear()
    else:
        _cache.pop(empresa_id, None)


async def carregar_chave_empresa(
    pool: AsyncConnectionPool, empresa_id: int
) -> str | None:
    """Chave em claro da empresa (ou None = plataforma), com cache de 60 s."""
    agora = time.monotonic()
    hit = _cache.get(empresa_id)
    if hit is not None and hit[0] > agora:
        return hit[1]
    chave: str | None = None
    try:
        with empresa_scope(None, bypass=True):
            async with pool.connection() as conn:
                cur = await conn.execute(
                    "SELECT openrouter_chave_cifrada FROM empresa WHERE id = %s",
                    (empresa_id,),
                )
                row = await cur.fetchone()
    except Exception as exc:  # noqa: BLE001 — banco fora não pode calar o agente
        logger.warning(
            "openrouter_chave_carregar_falhou", empresa_id=empresa_id, error=str(exc)
        )
        return hit[1] if hit is not None else None
    if row and row[0]:
        try:
            chave = decrypt_str(row[0])
        except IntegracaoConfigError as exc:
            logger.error(
                "openrouter_chave_ilegivel", empresa_id=empresa_id, error=str(exc)
            )
            chave = None
    _cache[empresa_id] = (agora + _CACHE_TTL_S, chave)
    return chave


@asynccontextmanager
async def chave_da_empresa(pool: AsyncConnectionPool, empresa_id: int):
    """Carrega a chave da empresa e a deixa no contexto durante o bloco."""
    chave = await carregar_chave_empresa(pool, empresa_id)
    with usar_chave(chave):
        yield chave


# --- estado e operações (painel) -------------------------------------------


@dataclass(frozen=True)
class StatusChave:
    definida: bool
    origem: str | None
    prefixo: str | None
    definida_em: datetime | None
    limite_usd: float | None
    uso: gestao.InfoChave | None
    uso_erro: str | None
    provisionamento_disponivel: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "definida": self.definida,
            "origem": self.origem,
            "prefixo": self.prefixo,
            "definida_em": self.definida_em.isoformat() if self.definida_em else None,
            "limite_usd": self.limite_usd,
            "uso": self.uso.to_dict() if self.uso else None,
            "uso_erro": self.uso_erro,
            "provisionamento_disponivel": self.provisionamento_disponivel,
        }


@dataclass(frozen=True)
class _Linha:
    id: int
    slug: str
    cifrada: str | None
    prefixo: str | None
    origem: str | None
    hash: str | None
    limite_usd: float | None
    definida_em: datetime | None


async def _ler(pool: AsyncConnectionPool, empresa_id: int) -> _Linha | None:
    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT id, slug, openrouter_chave_cifrada, openrouter_chave_prefixo,
                       openrouter_chave_origem, openrouter_chave_hash,
                       openrouter_chave_limite_usd, openrouter_chave_definida_em
                  FROM empresa WHERE id = %s
                """,
                (empresa_id,),
            )
            row = await cur.fetchone()
    if row is None:
        return None
    return _Linha(
        id=int(row[0]),
        slug=str(row[1]),
        cifrada=row[2],
        prefixo=row[3],
        origem=row[4],
        hash=row[5],
        limite_usd=float(row[6]) if row[6] is not None else None,
        definida_em=row[7],
    )


async def _gravar(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    chave: str | None,
    origem: str | None,
    hash_: str | None,
    limite_usd: float | None,
) -> None:
    cifrada = encrypt_str(chave) if chave else None
    prefixo = gestao.mascarar(chave) if chave else None
    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            await conn.execute(
                """
                UPDATE empresa
                   SET openrouter_chave_cifrada = %s,
                       openrouter_chave_prefixo = %s,
                       openrouter_chave_origem = %s,
                       openrouter_chave_hash = %s,
                       openrouter_chave_limite_usd = %s,
                       openrouter_chave_definida_em = CASE WHEN %s THEN NOW() ELSE NULL END,
                       updated_at = NOW()
                 WHERE id = %s
                """,
                (
                    cifrada,
                    prefixo,
                    origem,
                    hash_,
                    limite_usd,
                    chave is not None,
                    empresa_id,
                ),
            )
            await conn.commit()
    limpar_cache(empresa_id)


async def _auditar(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    user_id: str | None,
    acao: str,
    diff: dict[str, Any],
    request: Any = None,
) -> None:
    from whatsapp_langchain.shared.audit import record_audit

    await record_audit(
        pool,
        empresa_id=empresa_id,
        user_id=user_id,
        action=acao,
        entity_type="empresa",
        entity_id=str(empresa_id),
        payload_diff=diff,
        request=request,
    )


async def _apagar_gerida_best_effort(hash_: str, *, empresa_id: int) -> bool:
    try:
        await gestao.apagar_chave_gerida(hash_)
        return True
    except gestao.OpenRouterGestaoError as exc:
        logger.warning(
            "openrouter_chave_gerida_nao_apagada", empresa_id=empresa_id, error=str(exc)
        )
        return False


def _status_de(
    linha: _Linha | None, *, uso: gestao.InfoChave | None, uso_erro: str | None
) -> StatusChave:
    definida = bool(linha and linha.cifrada)
    return StatusChave(
        definida=definida,
        origem=linha.origem if definida and linha else None,
        prefixo=linha.prefixo if definida and linha else None,
        definida_em=linha.definida_em if definida and linha else None,
        limite_usd=linha.limite_usd if definida and linha else None,
        uso=uso,
        uso_erro=uso_erro,
        provisionamento_disponivel=gestao.provisionamento_configurado(),
    )


async def status_chave(
    pool: AsyncConnectionPool, empresa_id: int, *, consultar_uso: bool = True
) -> StatusChave | None:
    """Estado para o painel. Nunca devolve a chave. `None` = empresa não existe."""
    linha = await _ler(pool, empresa_id)
    if linha is None:
        return None
    uso: gestao.InfoChave | None = None
    uso_erro: str | None = None
    if linha.cifrada and consultar_uso:
        try:
            if (
                linha.origem == ORIGEM_PROVISIONADA
                and linha.hash
                and gestao.provisionamento_configurado()
            ):
                uso = await gestao.consultar_chave_gerida(linha.hash)
            else:
                uso = await gestao.consultar_chave(decrypt_str(linha.cifrada))
        except gestao.ChaveInvalidaError:
            uso_erro = "A OpenRouter não reconhece mais esta chave. Troque ou remova."
        except gestao.OpenRouterGestaoError:
            uso_erro = "Não foi possível consultar o uso na OpenRouter agora."
        except IntegracaoConfigError:
            uso_erro = "A chave guardada não pôde ser lida. Defina de novo."
    return _status_de(linha, uso=uso, uso_erro=uso_erro)


async def definir_chave_propria(
    pool: AsyncConnectionPool,
    empresa_id: int,
    chave: str,
    *,
    user_id: str | None,
    request: Any = None,
) -> StatusChave | None:
    """Opção A: valida a chave na OpenRouter e grava cifrada.

    Se a empresa tinha chave provisionada, ela é apagada na OpenRouter
    (best-effort) para não ficar órfã gastando o limite da plataforma.
    Levanta `ChaveInvalidaError` / `OpenRouterGestaoError`.
    """
    chave = chave.strip()
    linha = await _ler(pool, empresa_id)
    if linha is None:
        return None
    info = await gestao.consultar_chave(chave)
    await _gravar(
        pool,
        empresa_id,
        chave=chave,
        origem=ORIGEM_PROPRIA,
        hash_=None,
        limite_usd=info.limite_usd,
    )
    if linha.origem == ORIGEM_PROVISIONADA and linha.hash:
        await _apagar_gerida_best_effort(linha.hash, empresa_id=empresa_id)
    await _auditar(
        pool,
        empresa_id,
        user_id=user_id,
        acao="openrouter.chave_definida",
        diff={
            "origem": {"before": linha.origem, "after": ORIGEM_PROPRIA},
            "prefixo": {"before": linha.prefixo, "after": gestao.mascarar(chave)},
        },
        request=request,
    )
    logger.info(
        "openrouter_chave_definida",
        empresa_id=empresa_id,
        origem=ORIGEM_PROPRIA,
        prefixo=gestao.mascarar(chave),
    )
    return _status_de(await _ler(pool, empresa_id), uso=info, uso_erro=None)


async def remover_chave(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    user_id: str | None,
    request: Any = None,
) -> tuple[StatusChave | None, bool | None]:
    """Volta a empresa para a chave da plataforma.

    Devolve `(status, apagada_na_openrouter)`: `None` quando não havia chave
    gerida para apagar; `False` quando a OpenRouter não respondeu (a chave
    local some mesmo assim — o que importa é parar de usá-la).
    """
    linha = await _ler(pool, empresa_id)
    if linha is None:
        return None, None
    if not linha.cifrada:
        return _status_de(linha, uso=None, uso_erro=None), None
    apagada: bool | None = None
    if linha.origem == ORIGEM_PROVISIONADA and linha.hash:
        apagada = await _apagar_gerida_best_effort(linha.hash, empresa_id=empresa_id)
    await _gravar(
        pool, empresa_id, chave=None, origem=None, hash_=None, limite_usd=None
    )
    await _auditar(
        pool,
        empresa_id,
        user_id=user_id,
        acao="openrouter.chave_removida",
        diff={
            "origem": {"before": linha.origem, "after": None},
            "prefixo": {"before": linha.prefixo, "after": None},
            "apagada_na_openrouter": {"before": None, "after": apagada},
        },
        request=request,
    )
    logger.info("openrouter_chave_removida", empresa_id=empresa_id, origem=linha.origem)
    return _status_de(await _ler(pool, empresa_id), uso=None, uso_erro=None), apagada


async def provisionar_chave(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    limite_usd: float | None,
    user_id: str | None,
    request: Any = None,
) -> StatusChave | None:
    """Opção B: cria uma chave exclusiva para a empresa pela API de gestão.

    Com chave provisionada anterior, é ROTAÇÃO: a nova entra primeiro, a
    antiga é apagada depois (best-effort) — nunca há janela sem chave.
    Levanta `ProvisionamentoNaoConfiguradoError` / `OpenRouterGestaoError`.
    """
    linha = await _ler(pool, empresa_id)
    if linha is None:
        return None
    nome = f"chatnexus-{empresa_id}-{linha.slug}"[:80]
    criada = await gestao.criar_chave(nome=nome, limite_usd=limite_usd)
    await _gravar(
        pool,
        empresa_id,
        chave=criada.chave,
        origem=ORIGEM_PROVISIONADA,
        hash_=criada.hash,
        limite_usd=criada.limite_usd,
    )
    rotacionada = False
    if linha.origem == ORIGEM_PROVISIONADA and linha.hash and linha.hash != criada.hash:
        rotacionada = True
        await _apagar_gerida_best_effort(linha.hash, empresa_id=empresa_id)
    await _auditar(
        pool,
        empresa_id,
        user_id=user_id,
        acao="openrouter.chave_provisionada",
        diff={
            "origem": {"before": linha.origem, "after": ORIGEM_PROVISIONADA},
            "prefixo": {
                "before": linha.prefixo,
                "after": gestao.mascarar(criada.chave),
            },
            "limite_usd": {"before": linha.limite_usd, "after": criada.limite_usd},
            "rotacionada": {"before": None, "after": rotacionada},
        },
        request=request,
    )
    logger.info(
        "openrouter_chave_provisionada",
        empresa_id=empresa_id,
        prefixo=gestao.mascarar(criada.chave),
        limite_usd=criada.limite_usd,
        rotacionada=rotacionada,
    )
    uso: gestao.InfoChave | None = None
    try:
        uso = await gestao.consultar_chave_gerida(criada.hash)
    except gestao.OpenRouterGestaoError:
        uso = None
    return _status_de(await _ler(pool, empresa_id), uso=uso, uso_erro=None)


async def definir_limite(
    pool: AsyncConnectionPool,
    empresa_id: int,
    limite_usd: float | None,
    *,
    user_id: str | None,
    request: Any = None,
) -> StatusChave | None:
    """Muda o limite de crédito de uma chave provisionada (None = sem limite)."""
    linha = await _ler(pool, empresa_id)
    if linha is None:
        return None
    if not (linha.cifrada and linha.origem == ORIGEM_PROVISIONADA and linha.hash):
        raise ChaveNaoGeridaError(
            "Só uma chave criada pela plataforma tem o limite ajustado por aqui."
        )
    info = await gestao.atualizar_chave_gerida(linha.hash, limite_usd=limite_usd)
    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            await conn.execute(
                "UPDATE empresa SET openrouter_chave_limite_usd = %s, updated_at = NOW() WHERE id = %s",
                (limite_usd, empresa_id),
            )
            await conn.commit()
    await _auditar(
        pool,
        empresa_id,
        user_id=user_id,
        acao="openrouter.chave_limite_alterado",
        diff={"limite_usd": {"before": linha.limite_usd, "after": limite_usd}},
        request=request,
    )
    return _status_de(await _ler(pool, empresa_id), uso=info, uso_erro=None)
