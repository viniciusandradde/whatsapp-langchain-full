"""Disparador (Task 1) — geração e verificação de API keys por empresa.

A extensão Chrome do Disparador autentica via uma chave por empresa (NÃO o
`INTERNAL_SERVICE_TOKEN` global, que vazaria no cliente do browser). Cada chave:

- tem formato ``nxs_<empresa_id>_<32hex>`` — o ``empresa_id`` embutido permite
  escopar o lookup no banco sem varrer todos os hashes;
- é guardada apenas como ``sha256(chave)`` em hex (NUNCA o segredo em claro);
- carrega escopos (``capture``/``dispatch``/``templates``), expiração opcional e
  revogação.

Este módulo é puro (sem I/O de banco) para ser testável isoladamente. A
resolução contra o banco + ativação do contexto RLS fica em
``server/dependencies.py::verify_api_key`` (Task 2).
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from psycopg_pool import AsyncConnectionPool

# Prefixo do token. Mantido curto e estável para parsing simples.
KEY_NAMESPACE = "nxs"
# Bytes aleatórios → 32 chars hex. Entropia de 128 bits, suficiente.
_RANDOM_BYTES = 16
# Quantos chars do início do token compõem o `key_prefix` exibível/indexável.
# Cobre "nxs_<eid>_" + 8 chars do aleatório, o bastante para distinguir chaves
# da mesma empresa na UI sem expor material sensível.
_PREFIX_RANDOM_CHARS = 8

# Escopos válidos que uma chave pode conceder.
VALID_SCOPES: frozenset[str] = frozenset({"capture", "dispatch", "templates"})


def hash_api_key(key: str) -> str:
    """Retorna o SHA-256 (hex) da chave. É isto que persistimos, nunca o segredo."""
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def generate_api_key(empresa_id: int) -> tuple[str, str, str]:
    """Gera uma nova API key para a empresa.

    Args:
        empresa_id: ID da empresa dona da chave (embutido no token).

    Returns:
        Tupla ``(chave_plain, key_prefix, key_hash_hex)``:
        - ``chave_plain``: o segredo completo, mostrado ao usuário UMA única vez;
        - ``key_prefix``: trecho inicial para exibição/lookup (não sensível);
        - ``key_hash_hex``: ``sha256`` da chave, para persistir.

    Exemplo:
        >>> plain, prefix, h = generate_api_key(1)
        >>> plain.startswith("nxs_1_")
        True
    """
    if empresa_id <= 0:
        raise ValueError("empresa_id deve ser um inteiro positivo")
    random_part = secrets.token_hex(_RANDOM_BYTES)
    key = f"{KEY_NAMESPACE}_{empresa_id}_{random_part}"
    prefix = f"{KEY_NAMESPACE}_{empresa_id}_{random_part[:_PREFIX_RANDOM_CHARS]}"
    return key, prefix, hash_api_key(key)


def parse_empresa_id(key: str) -> int | None:
    """Extrai o ``empresa_id`` embutido no token, ou ``None`` se malformado.

    Não valida o segredo — apenas faz parse do formato ``nxs_<empresa_id>_<hex>``
    para escopar o lookup no banco. A validação criptográfica é via
    :func:`verify_api_key`.
    """
    if not key:
        return None
    parts = key.split("_")
    if len(parts) != 3 or parts[0] != KEY_NAMESPACE:
        return None
    eid, random_part = parts[1], parts[2]
    if not eid.isdigit() or not random_part:
        return None
    try:
        value = int(eid)
    except ValueError:
        return None
    return value if value > 0 else None


def key_prefix_of(key: str) -> str | None:
    """Deriva o ``key_prefix`` de um token recebido (para lookup indexado)."""
    if parse_empresa_id(key) is None:
        return None
    namespace, eid, random_part = key.split("_")
    return f"{namespace}_{eid}_{random_part[:_PREFIX_RANDOM_CHARS]}"


def verify_api_key(provided: str, stored_hash_hex: str) -> bool:
    """Compara, de forma timing-safe, a chave recebida com o hash persistido.

    Args:
        provided: chave em claro enviada no header Authorization.
        stored_hash_hex: ``key_hash`` (hex) lido do banco.

    Returns:
        True se ``sha256(provided) == stored_hash_hex``, em tempo constante.
    """
    if not provided or not stored_hash_hex:
        return False
    return hmac.compare_digest(hash_api_key(provided), stored_hash_hex)


def normalize_scopes(scopes: list[str] | None) -> list[str]:
    """Filtra/normaliza escopos para o conjunto válido, preservando a ordem.

    Escopos desconhecidos são descartados silenciosamente. Lista vazia/None vira
    o default ``['capture']``.
    """
    if not scopes:
        return ["capture"]
    seen: set[str] = set()
    out: list[str] = []
    for s in scopes:
        s = (s or "").strip().lower()
        if s in VALID_SCOPES and s not in seen:
            seen.add(s)
            out.append(s)
    return out or ["capture"]


def has_scope(granted: list[str] | None, required: str) -> bool:
    """True se a lista de escopos concedidos cobre o escopo exigido."""
    return required in (granted or [])


@dataclass(frozen=True)
class ApiKeyContext:
    """Contexto resolvido de uma API key válida (retornado pela dependency)."""

    empresa_id: int
    key_id: int
    scopes: list[str] = field(default_factory=list)
    rate_limit_per_minute: int = 60


async def resolve_api_key(
    pool: AsyncConnectionPool, token: str
) -> ApiKeyContext | None:
    """Resolve um token de API contra o banco, retornando o contexto ou None.

    Faz o lookup sob ``empresa_scope(None, bypass=True)`` porque no momento da
    request ainda não há contexto RLS (a empresa É descoberta por esta função —
    mesmo padrão de ``get_conexao_by_evolution_instance``). Filtra na query
    apenas chaves ativas (não revogadas e não expiradas) e confirma o hash de
    forma timing-safe. Atualiza ``last_used_at`` best-effort.

    Returns:
        ``ApiKeyContext`` se o token é válido/ativo; ``None`` caso contrário
        (formato inválido, prefixo inexistente, hash divergente, revogada ou
        expirada) — o chamador traduz ``None`` em 401 genérico.
    """
    from whatsapp_langchain.shared.rls_context import empresa_scope

    empresa_id = parse_empresa_id(token)
    prefix = key_prefix_of(token)
    if empresa_id is None or prefix is None:
        return None

    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT id, key_hash, scopes, rate_limit_per_minute
                  FROM empresa_api_key
                 WHERE key_prefix = %s
                   AND empresa_id = %s
                   AND revoked_at IS NULL
                   AND (expires_at IS NULL OR expires_at > NOW())
                """,
                (prefix, empresa_id),
            )
            row = await cur.fetchone()

        if row is None:
            return None
        key_id, key_hash, scopes, rate_limit = row[0], row[1], row[2], row[3]
        if not verify_api_key(token, key_hash):
            return None

        # Atualiza last_used_at best-effort (não derruba a request se falhar).
        try:
            async with pool.connection() as conn:
                await conn.execute(
                    "UPDATE empresa_api_key SET last_used_at = NOW() WHERE id = %s",
                    (key_id,),
                )
                await conn.commit()
        except Exception:  # noqa: BLE001 — telemetria best-effort
            pass

    return ApiKeyContext(
        empresa_id=empresa_id,
        key_id=int(key_id),
        scopes=list(scopes or []),
        rate_limit_per_minute=int(rate_limit or 60),
    )
