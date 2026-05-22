"""Helpers de PII opt-in por empresa (Sprint D — Hardening 2026-05-22).

Quando `empresa.config.encrypt_pii = true`, campos sensíveis (`cpf`, `cnpj`,
`rg`, `data_nascimento`) na tabela `cliente` são cifrados via Fernet usando
`WARELINE_ENCRYPTION_KEY` (mesma chave do `integrations/crypto.py`).

Por que opt-in?
- Empresas sem requirements LGPD-grade preferem queries diretas (dedup por
  CPF, busca exata) — Fernet é não-determinístico.
- Empresas com (saúde, financeiro, governo) ativam o flag e pagam o overhead.

Estratégia de leitura:
- `read_pii_field(row, field, empresa_encrypt_pii)` retorna decrypt do
  `<field>_encrypted` se setado, senão fallback no plain `<field>`.

Estratégia de escrita:
- `prepare_pii_write(value, empresa_encrypt_pii)` retorna `(plain, encrypted)`
  tuple. Se opt-in on: `(None, encrypt(value))`. Senão: `(value, None)`.

Migração retroativa de dados é manual via script ad-hoc por empresa — não
roda em batch automático porque pode quebrar queries que fazem dedup em CPF
plain (UNIQUE constraint, etc.).
"""

from __future__ import annotations

from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.integrations.crypto import (
    IntegracaoConfigError,
    decrypt_str,
    encrypt_str,
)


async def get_empresa_encrypt_pii(pool: AsyncConnectionPool, empresa_id: int) -> bool:
    """Lê `empresa.config.encrypt_pii` (bool, default false)."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT (config->>'encrypt_pii')::boolean FROM empresa WHERE id = %s",
            (empresa_id,),
        )
        row = await cur.fetchone()
    return bool(row[0]) if row and row[0] is not None else False


def read_pii_field(
    plain_value: str | None,
    encrypted_value: str | None,
) -> str | None:
    """Retorna o valor PII em texto claro.

    Prioridade: encrypted (se setado e decryptable) → plain → None.
    Se decrypt falha (chave trocada / corrompido), retorna None silenciosamente
    para não quebrar listagens — alerta vai pro log via `integrations/crypto`.
    """
    if encrypted_value:
        try:
            return decrypt_str(encrypted_value)
        except IntegracaoConfigError:
            # Chave trocada ou ciphertext corrompido. Fallback no plain.
            return plain_value
    return plain_value


def prepare_pii_write(
    value: str | None, encrypt_enabled: bool
) -> tuple[str | None, str | None]:
    """Retorna `(plain, encrypted)` pra INSERT/UPDATE em `cliente`.

    Se `encrypt_enabled=True` e `value` truthy: `(None, encrypt(value))`.
    Senão: `(value, None)`.
    """
    if not value:
        return (None, None)
    if encrypt_enabled:
        return (None, encrypt_str(value))
    return (value, None)
