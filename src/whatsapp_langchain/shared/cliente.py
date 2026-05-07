"""Helpers de Cliente — UPSERT por (empresa_id, telefone), anotações e tags.

Cada inbound do webhook resolve a empresa via conexão e em seguida garante
um `cliente` cadastrado pra aquela empresa+telefone (`upsert_cliente`). O
nome do cliente vem do ProfileName do Twilio quando ainda não existe — e
nunca é sobrescrito pelo webhook depois (operador edita pela UI).

Tags ficam em `cliente_tag` (PK composta cliente_id+tag, idempotente via
ON CONFLICT DO NOTHING). Anotações ficam em `cliente_anotacao` (append-only).
"""

from __future__ import annotations

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.models import Cliente, ClienteAnotacao

logger = structlog.get_logger()


_SELECT_COLS = (
    "id, empresa_id, telefone, nome, email, doc, status, config, "
    "created_at, updated_at, "
    # Fase 1.A enrich
    "tipo_pessoa, cpf, cnpj, rg, razao_social, nome_fantasia, "
    "data_nascimento, genero, "
    "cep, logradouro, numero, complemento, bairro, cidade, uf, pais, "
    "segmento, lifecycle_stage, score, source, responsavel_user_id, valor_estimado_brl, "
    "instagram, linkedin, facebook, website, email_alternativo, telefone_alternativo, "
    "locale, timezone, avatar_url, last_interaction_at, notes, "
    # Sub-fase B+ paridade ZigChat (mig 046)
    "whatsapp_state, numero_verificado, whatsapp_lid, remote_id, "
    "msg_apos_encerramento, field_1, field_2, field_3, field_4, field_5, "
    "ignora_inatividade, desconsidera_turno"
)


def _row_to_cliente(row, tags: list[str] | None = None) -> Cliente:
    """Mapeia row do SELECT pro Pydantic. Fase 1.A: 32 campos extras."""
    return Cliente(
        id=row[0],
        empresa_id=row[1],
        telefone=row[2],
        nome=row[3],
        email=row[4],
        doc=row[5],
        status=row[6],
        config=row[7] or {},
        created_at=row[8],
        updated_at=row[9],
        tags=tags or [],
        # ----- enrich -----
        tipo_pessoa=row[10],
        cpf=row[11],
        cnpj=row[12],
        rg=row[13],
        razao_social=row[14],
        nome_fantasia=row[15],
        data_nascimento=row[16],
        genero=row[17],
        cep=row[18],
        logradouro=row[19],
        numero=row[20],
        complemento=row[21],
        bairro=row[22],
        cidade=row[23],
        uf=row[24],
        pais=row[25] or "BR",
        segmento=row[26],
        lifecycle_stage=row[27],
        score=row[28],
        source=row[29],
        responsavel_user_id=row[30],
        valor_estimado_brl=float(row[31]) if row[31] is not None else None,
        instagram=row[32],
        linkedin=row[33],
        facebook=row[34],
        website=row[35],
        email_alternativo=row[36],
        telefone_alternativo=row[37],
        locale=row[38] or "pt-BR",
        timezone=row[39] or "America/Sao_Paulo",
        avatar_url=row[40],
        last_interaction_at=row[41],
        notes=row[42],
        # Sub-fase B+ paridade ZigChat (mig 046)
        whatsapp_state=row[43],
        numero_verificado=row[44] or False,
        whatsapp_lid=row[45],
        remote_id=row[46],
        msg_apos_encerramento=row[47],
        field_1=row[48],
        field_2=row[49],
        field_3=row[50],
        field_4=row[51],
        field_5=row[52],
        ignora_inatividade=row[53] or False,
        desconsidera_turno=row[54] or False,
    )


async def upsert_cliente(
    pool: AsyncConnectionPool,
    empresa_id: int,
    telefone: str,
    *,
    nome: str | None = None,
    email: str | None = None,
    doc: str | None = None,
) -> Cliente:
    """Cria/atualiza cliente pela UNIQUE (empresa_id, telefone).

    Política do webhook: nunca sobrescreve nome/email/doc já preenchidos.
    Usa COALESCE para preservar os valores existentes quando os argumentos
    chegam None ou quando a coluna já tem valor.
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            INSERT INTO cliente (empresa_id, telefone, nome, email, doc)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (empresa_id, telefone) DO UPDATE SET
                nome = COALESCE(cliente.nome, EXCLUDED.nome),
                email = COALESCE(cliente.email, EXCLUDED.email),
                doc = COALESCE(cliente.doc, EXCLUDED.doc),
                updated_at = NOW()
            RETURNING {_SELECT_COLS}
            """,
            (empresa_id, telefone, nome, email, doc),
        )
        row = await cur.fetchone()
    assert row is not None
    return _row_to_cliente(row)


async def get_cliente_by_id(
    pool: AsyncConnectionPool, cliente_id: int
) -> Cliente | None:
    """Carrega cliente + tags em duas queries (PK + agrega de tags)."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {_SELECT_COLS} FROM cliente WHERE id = %s",
            (cliente_id,),
        )
        row = await cur.fetchone()
        if not row:
            return None
        cur = await conn.execute(
            "SELECT tag FROM cliente_tag WHERE cliente_id = %s ORDER BY tag ASC",
            (cliente_id,),
        )
        tag_rows = await cur.fetchall()
    return _row_to_cliente(row, tags=[r[0] for r in tag_rows])


async def update_cliente_partial(
    pool: AsyncConnectionPool,
    empresa_id: int,
    cliente_id: int,
    *,
    # Legacy + tools agente
    nome: str | None = None,
    email: str | None = None,
    doc: str | None = None,
    # Fase 1.A enrich — todos opcionais
    tipo_pessoa: str | None = None,
    cpf: str | None = None,
    cnpj: str | None = None,
    rg: str | None = None,
    razao_social: str | None = None,
    nome_fantasia: str | None = None,
    data_nascimento: str | None = None,  # ISO date string
    genero: str | None = None,
    cep: str | None = None,
    logradouro: str | None = None,
    numero: str | None = None,
    complemento: str | None = None,
    bairro: str | None = None,
    cidade: str | None = None,
    uf: str | None = None,
    pais: str | None = None,
    segmento: str | None = None,
    lifecycle_stage: str | None = None,
    score: int | None = None,
    source: str | None = None,
    responsavel_user_id: str | None = None,
    valor_estimado_brl: float | None = None,
    instagram: str | None = None,
    linkedin: str | None = None,
    facebook: str | None = None,
    website: str | None = None,
    email_alternativo: str | None = None,
    telefone_alternativo: str | None = None,
    locale: str | None = None,
    timezone: str | None = None,
    avatar_url: str | None = None,
    notes: str | None = None,
    # Sub-fase B+ paridade ZigChat (mig 046)
    whatsapp_state: str | None = None,
    numero_verificado: bool | None = None,
    whatsapp_lid: str | None = None,
    remote_id: str | None = None,
    msg_apos_encerramento: str | None = None,
    field_1: str | None = None,
    field_2: str | None = None,
    field_3: str | None = None,
    field_4: str | None = None,
    field_5: str | None = None,
    ignora_inatividade: bool | None = None,
    desconsidera_turno: bool | None = None,
) -> Cliente | None:
    """Update parcial — só campos não-None são tocados (M5.b.1 + Fase 1.A).

    Usado por:
    - Tools do agente (nome/email/doc) — comportamento original
    - PUT /api/clientes/{id} — todos os campos da ficha enriquecida
    """
    sets: list[str] = []
    params: list = []

    def _add(field: str, value):
        if value is not None:
            sets.append(f"{field} = %s")
            params.append(value)

    _add("nome", nome)
    _add("email", email)
    _add("doc", doc)
    _add("tipo_pessoa", tipo_pessoa)
    _add("cpf", cpf)
    _add("cnpj", cnpj)
    _add("rg", rg)
    _add("razao_social", razao_social)
    _add("nome_fantasia", nome_fantasia)
    _add("data_nascimento", data_nascimento)
    _add("genero", genero)
    _add("cep", cep)
    _add("logradouro", logradouro)
    _add("numero", numero)
    _add("complemento", complemento)
    _add("bairro", bairro)
    _add("cidade", cidade)
    _add("uf", uf)
    _add("pais", pais)
    _add("segmento", segmento)
    _add("lifecycle_stage", lifecycle_stage)
    _add("score", score)
    _add("source", source)
    _add("responsavel_user_id", responsavel_user_id)
    _add("valor_estimado_brl", valor_estimado_brl)
    _add("instagram", instagram)
    _add("linkedin", linkedin)
    _add("facebook", facebook)
    _add("website", website)
    _add("email_alternativo", email_alternativo)
    _add("telefone_alternativo", telefone_alternativo)
    _add("locale", locale)
    _add("timezone", timezone)
    _add("avatar_url", avatar_url)
    _add("notes", notes)
    # Sub-fase B+ paridade ZigChat (mig 046)
    _add("whatsapp_state", whatsapp_state)
    _add("numero_verificado", numero_verificado)
    _add("whatsapp_lid", whatsapp_lid)
    _add("remote_id", remote_id)
    _add("msg_apos_encerramento", msg_apos_encerramento)
    _add("field_1", field_1)
    _add("field_2", field_2)
    _add("field_3", field_3)
    _add("field_4", field_4)
    _add("field_5", field_5)
    _add("ignora_inatividade", ignora_inatividade)
    _add("desconsidera_turno", desconsidera_turno)

    if not sets:
        return await get_cliente_by_id(pool, cliente_id)
    sets.append("updated_at = NOW()")
    params.extend([cliente_id, empresa_id])
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            UPDATE cliente SET {", ".join(sets)}
             WHERE id = %s AND empresa_id = %s
            RETURNING {_SELECT_COLS}
            """,  # type: ignore[arg-type]
            tuple(params),
        )
        row = await cur.fetchone()
    if row is None:
        return None
    # Re-lê tags pra retornar lista atualizada.
    return await get_cliente_by_id(pool, cliente_id)


async def get_cliente_by_telefone(
    pool: AsyncConnectionPool, empresa_id: int, telefone: str
) -> Cliente | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {_SELECT_COLS} FROM cliente
             WHERE empresa_id = %s AND telefone = %s
            """,
            (empresa_id, telefone),
        )
        row = await cur.fetchone()
    return _row_to_cliente(row) if row else None


async def list_clientes(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[Cliente]:
    """Lista clientes da empresa, ordenados por updated_at DESC.

    `search` filtra por substring case-insensitive em nome ou telefone.
    """
    params: list = [empresa_id]
    where = "WHERE empresa_id = %s"
    if search:
        where += " AND (nome ILIKE %s OR telefone ILIKE %s)"
        like = f"%{search}%"
        params.extend([like, like])
    params.extend([limit, offset])
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {_SELECT_COLS} FROM cliente
            {where}
            ORDER BY updated_at DESC, id DESC
            LIMIT %s OFFSET %s
            """,  # type: ignore[arg-type]
            tuple(params),
        )
        rows = await cur.fetchall()
    return [_row_to_cliente(r) for r in rows]


async def add_anotacao(
    pool: AsyncConnectionPool,
    cliente_id: int,
    user_id: str,
    conteudo: str,
) -> ClienteAnotacao:
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            INSERT INTO cliente_anotacao (cliente_id, user_id, conteudo)
            VALUES (%s, %s, %s)
            RETURNING id, cliente_id, user_id, conteudo, created_at
            """,
            (cliente_id, user_id, conteudo),
        )
        row = await cur.fetchone()
    assert row is not None
    return ClienteAnotacao(
        id=row[0],
        cliente_id=row[1],
        user_id=row[2],
        conteudo=row[3],
        created_at=row[4],
    )


async def list_anotacoes(
    pool: AsyncConnectionPool,
    cliente_id: int,
    *,
    limit: int | None = None,
) -> list[ClienteAnotacao]:
    """Anotações do cliente em ordem DESC. `limit` opcional pra tools do agente."""
    sql = """
        SELECT id, cliente_id, user_id, conteudo, created_at
          FROM cliente_anotacao
         WHERE cliente_id = %s
         ORDER BY created_at DESC, id DESC
    """
    params: tuple = (cliente_id,)
    if limit is not None:
        sql += " LIMIT %s"
        params = (cliente_id, int(limit))
    async with pool.connection() as conn:
        cur = await conn.execute(sql, params)
        rows = await cur.fetchall()
    return [
        ClienteAnotacao(
            id=r[0],
            cliente_id=r[1],
            user_id=r[2],
            conteudo=r[3],
            created_at=r[4],
        )
        for r in rows
    ]


async def add_tag(pool: AsyncConnectionPool, cliente_id: int, tag: str) -> None:
    """Adiciona tag (idempotente — não duplica par cliente_id+tag)."""
    async with pool.connection() as conn:
        await conn.execute(
            """
            INSERT INTO cliente_tag (cliente_id, tag)
            VALUES (%s, %s)
            ON CONFLICT (cliente_id, tag) DO NOTHING
            """,
            (cliente_id, tag),
        )


async def remove_tag(pool: AsyncConnectionPool, cliente_id: int, tag: str) -> None:
    async with pool.connection() as conn:
        await conn.execute(
            "DELETE FROM cliente_tag WHERE cliente_id = %s AND tag = %s",
            (cliente_id, tag),
        )
