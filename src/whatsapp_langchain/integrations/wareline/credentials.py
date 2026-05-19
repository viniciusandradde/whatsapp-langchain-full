"""CRUD de credenciais Wareline por empresa, com Fernet pra cripto.

Tabela: `wareline_credentials` (mig 090).

Cripto: campos `password` e `client_secret` cifrados com Fernet
(symmetric, base64). Chave global em `settings.wareline_encryption_key`.

Pattern de uso:
    creds = await get_credentials(pool, empresa_id)
    if creds is None or not creds.ativo:
        raise WarelineConfigError("Wareline não configurado pra empresa X")
    # Usa creds.password / creds.client_secret diretamente — já decifrados
"""

from __future__ import annotations

import structlog
from cryptography.fernet import Fernet, InvalidToken
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.integrations.wareline.errors import (
    WarelineConfigError,
)
from whatsapp_langchain.integrations.wareline.models import WarelineCredentials
from whatsapp_langchain.shared.config import settings

logger = structlog.get_logger()


def _get_fernet() -> Fernet:
    """Lazy + valida chave configurada."""
    key = settings.wareline_encryption_key
    if key is None:
        raise WarelineConfigError(
            "WARELINE_ENCRYPTION_KEY não configurada. Gere com "
            "`python -c 'from cryptography.fernet import Fernet; "
            "print(Fernet.generate_key().decode())'`"
        )
    raw = key.get_secret_value() if hasattr(key, "get_secret_value") else str(key)
    return Fernet(raw.encode() if isinstance(raw, str) else raw)


def encrypt(plaintext: str) -> str:
    """Cifra string em Fernet ciphertext (utf-8 → bytes → base64 token)."""
    return _get_fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(ciphertext: str) -> str:
    """Decifra Fernet ciphertext. Lança WarelineConfigError se corrompido."""
    try:
        return _get_fernet().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise WarelineConfigError(
            "Credencial Wareline corrompida ou WARELINE_ENCRYPTION_KEY "
            "trocada após salvar — reconfigure a integração."
        ) from exc


async def get_credentials(
    pool: AsyncConnectionPool, empresa_id: int
) -> WarelineCredentials | None:
    """Lê credenciais da empresa, decifrando senha+secret.

    Retorna None se empresa não tem row. Lança WarelineConfigError se
    cripto falhar ou config inativa.
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT base_url, pacientes_base_url, username, password_encrypted,
                   client_id, client_secret_encrypted, ativo
              FROM wareline_credentials
             WHERE empresa_id = %s
            """,
            (empresa_id,),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    (
        base_url,
        pacientes_base_url,
        username,
        password_enc,
        client_id,
        client_secret_enc,
        ativo,
    ) = row
    return WarelineCredentials(
        empresa_id=empresa_id,
        base_url=base_url,
        pacientes_base_url=pacientes_base_url,
        username=username,
        password=decrypt(password_enc),
        client_id=client_id,
        client_secret=decrypt(client_secret_enc),
        ativo=ativo,
    )


async def get_credentials_safe_view(
    pool: AsyncConnectionPool, empresa_id: int
) -> dict | None:
    """Versão sem campos sensíveis (pra GET admin retornar pro front)."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT base_url, pacientes_base_url, username, client_id,
                   ativo, ultimo_teste_at, ultimo_teste_ok, ultimo_teste_erro,
                   updated_at
              FROM wareline_credentials
             WHERE empresa_id = %s
            """,
            (empresa_id,),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    return {
        "empresa_id": empresa_id,
        "base_url": row[0],
        "pacientes_base_url": row[1],
        "username": row[2],
        "client_id": row[3],
        "ativo": row[4],
        "ultimo_teste_at": row[5].isoformat() if row[5] else None,
        "ultimo_teste_ok": row[6],
        "ultimo_teste_erro": row[7],
        "updated_at": row[8].isoformat() if row[8] else None,
        # password/client_secret nunca expostos
        "password_set": True,
        "client_secret_set": True,
    }


async def save_credentials(
    pool: AsyncConnectionPool,
    *,
    empresa_id: int,
    username: str,
    password: str,
    client_id: str,
    client_secret: str,
    base_url: str | None = None,
    pacientes_base_url: str | None = None,
    ativo: bool = True,
    created_by_user_id: str | None = None,
) -> dict:
    """UPSERT — cria ou atualiza credenciais da empresa."""
    base_url = base_url or "https://modulos.conectew.com.br"
    pacientes_base_url = (
        pacientes_base_url or "https://services.conectew.com.br"
    )
    password_enc = encrypt(password)
    client_secret_enc = encrypt(client_secret)
    async with pool.connection() as conn:
        await conn.execute(
            """
            INSERT INTO wareline_credentials (
                empresa_id, base_url, pacientes_base_url,
                username, password_encrypted, client_id,
                client_secret_encrypted, ativo, created_by_user_id
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (empresa_id) DO UPDATE SET
                base_url = EXCLUDED.base_url,
                pacientes_base_url = EXCLUDED.pacientes_base_url,
                username = EXCLUDED.username,
                password_encrypted = EXCLUDED.password_encrypted,
                client_id = EXCLUDED.client_id,
                client_secret_encrypted = EXCLUDED.client_secret_encrypted,
                ativo = EXCLUDED.ativo,
                updated_at = NOW()
            """,
            (
                empresa_id,
                base_url,
                pacientes_base_url,
                username,
                password_enc,
                client_id,
                client_secret_enc,
                ativo,
                created_by_user_id,
            ),
        )
        # Limpa cache de token quando trocou credenciais
        await conn.execute(
            "DELETE FROM wareline_token_cache WHERE empresa_id = %s",
            (empresa_id,),
        )
        await conn.commit()
    logger.info("wareline_credentials_saved", empresa_id=empresa_id)
    view = await get_credentials_safe_view(pool, empresa_id)
    assert view is not None
    return view


async def update_credentials_partial(
    pool: AsyncConnectionPool,
    *,
    empresa_id: int,
    password: str | None = None,
    client_secret: str | None = None,
    username: str | None = None,
    client_id: str | None = None,
    base_url: str | None = None,
    pacientes_base_url: str | None = None,
    ativo: bool | None = None,
) -> dict | None:
    """UPDATE parcial — só campos fornecidos. Útil quando user só edita
    nome/url sem mexer em senha (pattern do form: senha em branco = não troca)."""
    sets: list[str] = []
    args: list = []
    if password is not None:
        sets.append("password_encrypted = %s")
        args.append(encrypt(password))
    if client_secret is not None:
        sets.append("client_secret_encrypted = %s")
        args.append(encrypt(client_secret))
    if username is not None:
        sets.append("username = %s")
        args.append(username)
    if client_id is not None:
        sets.append("client_id = %s")
        args.append(client_id)
    if base_url is not None:
        sets.append("base_url = %s")
        args.append(base_url)
    if pacientes_base_url is not None:
        sets.append("pacientes_base_url = %s")
        args.append(pacientes_base_url)
    if ativo is not None:
        sets.append("ativo = %s")
        args.append(ativo)
    if not sets:
        return await get_credentials_safe_view(pool, empresa_id)
    sets.append("updated_at = NOW()")
    args.append(empresa_id)
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            UPDATE wareline_credentials SET {', '.join(sets)}
             WHERE empresa_id = %s
             RETURNING empresa_id
            """,  # type: ignore[arg-type]
            tuple(args),
        )
        row = await cur.fetchone()
        if row and (password is not None or client_secret is not None):
            await conn.execute(
                "DELETE FROM wareline_token_cache WHERE empresa_id = %s",
                (empresa_id,),
            )
        await conn.commit()
    if row is None:
        return None
    return await get_credentials_safe_view(pool, empresa_id)


async def delete_credentials(
    pool: AsyncConnectionPool, empresa_id: int
) -> bool:
    """Hard delete (cascade limpa token_cache via FK)."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            "DELETE FROM wareline_credentials WHERE empresa_id = %s "
            "RETURNING empresa_id",
            (empresa_id,),
        )
        row = await cur.fetchone()
        await conn.commit()
    return row is not None


async def record_test_result(
    pool: AsyncConnectionPool,
    *,
    empresa_id: int,
    ok: bool,
    mensagem: str | None,
) -> None:
    """Atualiza ultimo_teste_* depois de POST /testar."""
    async with pool.connection() as conn:
        await conn.execute(
            """
            UPDATE wareline_credentials
               SET ultimo_teste_at = NOW(),
                   ultimo_teste_ok = %s,
                   ultimo_teste_erro = %s,
                   updated_at = NOW()
             WHERE empresa_id = %s
            """,
            (ok, mensagem if not ok else None, empresa_id),
        )
        await conn.commit()
