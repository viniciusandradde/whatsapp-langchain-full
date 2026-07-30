"""Whitelist de números — bypass total da IA por número (escopo: empresa).

Números cadastrados pelo painel (/whitelist) não recebem NENHUMA resposta
automática do worker — o gate em `worker/processor.py::process_message` checa
`is_whitelisted` e marca a mensagem como done sem invocar workflow/menu/agente.
As mensagens seguem registradas (atendimento na fila humana). Mig 133.
"""

from __future__ import annotations

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.campanha import normalize_phone
from whatsapp_langchain.shared.rls_context import empresa_scope

logger = structlog.get_logger()


def candidatos_lookup(telefone: str) -> list[str]:
    """Variantes E.164 do número pro lookup na whitelist.

    JIDs antigos da Evolution chegam sem o nono dígito BR
    (+55 DDD XXXXXXXX) enquanto o cadastro no painel costuma vir com
    (+55 DDD 9XXXXXXXX) — sem as variantes o match falharia silencioso e a
    IA responderia pro contato whitelistado. Gera:

    - o número normalizado; e, quando BR mobile,
    - a variante com/sem o `9` após o DDD.

    Não-BR (sem prefixo 55 ou tamanho não-mobile): só o normalizado.
    Lista pequena (1-2 itens) — vai num `telefone = ANY(%s)` que ainda usa
    o índice (empresa_id, telefone).
    """
    norm = normalize_phone(telefone)
    if not norm:
        return []
    candidatos = [norm]
    digits = norm.lstrip("+")
    if digits.startswith("55"):
        resto = digits[2:]  # DDD + assinante
        # 55 + DDD(2) + 9 + 8 dígitos = 13 → variante sem o 9
        if len(resto) == 11 and resto[2] == "9":
            candidatos.append(f"+55{resto[:2]}{resto[3:]}")
        # 55 + DDD(2) + 8 dígitos = 12 → variante com o 9 (celular antigo)
        elif len(resto) == 10:
            candidatos.append(f"+55{resto[:2]}9{resto[2:]}")
    return candidatos


async def is_whitelisted(
    pool: AsyncConnectionPool, empresa_id: int, telefone: str
) -> bool:
    """True se o número está na whitelist da empresa (1 SELECT indexado)."""
    candidatos = candidatos_lookup(telefone)
    if not candidatos:
        return False
    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT 1 FROM whitelist_numero
                 WHERE empresa_id = %s AND telefone = ANY(%s)
                 LIMIT 1
                """,
                (empresa_id, candidatos),
            )
            row = await cur.fetchone()
    return row is not None


async def filtrar_whitelistados(
    pool: AsyncConnectionPool, empresa_id: int, telefones: list[str]
) -> set[str]:
    """Quais destes telefones estão na whitelist — UMA query para a lista toda.

    Versão em lote de [is_whitelisted], para a listagem de atendimentos: chamar a
    versão unitária por linha faria 50 SELECTs para desenhar uma página.

    Devolve os telefones **como vieram** (não normalizados), para o chamador
    conseguir casar com a linha de origem. O casamento interno usa as variantes
    com/sem o nono dígito BR de `candidatos_lookup` — sem isso o mesmo número
    escrito das duas formas não bate.
    """
    if not telefones:
        return set()

    # candidato normalizado -> telefones originais que o geraram
    por_candidato: dict[str, list[str]] = {}
    for tel in telefones:
        for cand in candidatos_lookup(tel):
            por_candidato.setdefault(cand, []).append(tel)
    if not por_candidato:
        return set()

    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT telefone FROM whitelist_numero
                 WHERE empresa_id = %s AND telefone = ANY(%s)
                """,
                (empresa_id, list(por_candidato)),
            )
            achados = await cur.fetchall()

    return {tel for (cand,) in achados for tel in por_candidato.get(cand, [])}


async def registrar_whitelist(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    telefone: str,
    nome: str | None = None,
    created_by_user_id: str | None = None,
) -> dict:
    """Cadastra um número na whitelist. Grava o E.164 normalizado como veio
    (a equivalência do nono dígito resolve no lookup, não na gravação).

    Raises:
        ValueError: telefone inválido (normalize_phone → None).
        UniqueViolation (propaga): número já cadastrado — router mapeia 409.
    """
    norm = normalize_phone(telefone)
    if not norm:
        raise ValueError(f"telefone inválido: {telefone!r}")
    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                INSERT INTO whitelist_numero
                    (empresa_id, telefone, nome, created_by_user_id)
                VALUES (%s, %s, %s, %s)
                RETURNING id, telefone, nome, created_by_user_id, created_at
                """,
                (empresa_id, norm, nome, created_by_user_id),
            )
            row = await cur.fetchone()
            await conn.commit()
    assert row is not None
    logger.info("whitelist_registrado", empresa_id=empresa_id, whitelist_id=row[0])
    keys = ["id", "telefone", "nome", "created_by_user_id", "created_at"]
    return dict(zip(keys, row, strict=True))


async def listar_whitelist(
    pool: AsyncConnectionPool, empresa_id: int, *, limit: int = 500
) -> list[dict]:
    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT id, telefone, nome, created_by_user_id, created_at
                  FROM whitelist_numero WHERE empresa_id = %s
                 ORDER BY created_at DESC LIMIT %s
                """,
                (empresa_id, limit),
            )
            rows = await cur.fetchall()
    keys = ["id", "telefone", "nome", "created_by_user_id", "created_at"]
    return [dict(zip(keys, r, strict=True)) for r in rows]


async def atualizar_whitelist(
    pool: AsyncConnectionPool,
    empresa_id: int,
    whitelist_id: int,
    *,
    nome: str | None,
) -> dict | None:
    """Atualiza o apelido. Telefone não é editável — errou o número, deleta
    e recria (evita re-normalização e mantém o histórico simples)."""
    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                UPDATE whitelist_numero SET nome = %s
                 WHERE id = %s AND empresa_id = %s
                RETURNING id, telefone, nome, created_by_user_id, created_at
                """,
                (nome, whitelist_id, empresa_id),
            )
            row = await cur.fetchone()
            await conn.commit()
    if row is None:
        return None
    keys = ["id", "telefone", "nome", "created_by_user_id", "created_at"]
    return dict(zip(keys, row, strict=True))


async def remover_whitelist(
    pool: AsyncConnectionPool, empresa_id: int, whitelist_id: int
) -> bool:
    """Remove um número da whitelist (IA volta a responder). Retorna se removeu."""
    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            cur = await conn.execute(
                "DELETE FROM whitelist_numero WHERE id = %s AND empresa_id = %s",
                (whitelist_id, empresa_id),
            )
            await conn.commit()
            return cur.rowcount > 0
