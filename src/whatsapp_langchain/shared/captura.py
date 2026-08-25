"""Disparador (Task 5) — orquestração e persistência da captura.

Camada compartilhada usada pelos endpoints de captura: upserts idempotentes no
staging (`contato_capturado`/`grupo`/`grupo_membro`), auditoria em
`captura_lote`, e a orquestração que puxa da Evolution e grava.

Pontos de atenção:
* Os background tasks rodam DEPOIS da resposta HTTP — fora do contexto RLS da
  request. Por isso cada um abre seu próprio ``empresa_scope(empresa_id)``.
* Idempotência: ``INSERT ... ON CONFLICT DO UPDATE ... RETURNING (xmax = 0)``
  diz se a linha foi inserida (novo) ou atualizada (``xmax = 0`` ⇒ insert).
* Identidade é ``wa_jid``; telefone é derivado só de ``@s.whatsapp.net``.
"""

from __future__ import annotations

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.cliente import upsert_cliente
from whatsapp_langchain.shared.models import Conexao
from whatsapp_langchain.shared.rls_context import empresa_scope
from whatsapp_langchain.worker.evolution_client import (
    CapturedContact,
    CapturedGroup,
    EvolutionClient,
    phone_from_jid,
)

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Auditoria (captura_lote)
# ---------------------------------------------------------------------------


async def criar_lote(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    origem: str,
    tipo: str,
    conexao_id: int | None = None,
    api_key_id: int | None = None,
    origem_jid: str | None = None,
    user_id: str | None = None,
) -> int:
    """Cria um lote de captura em status 'processando' e devolve o id."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            INSERT INTO captura_lote
                (empresa_id, origem, tipo, conexao_id, api_key_id, origem_jid,
                 status, created_by_user_id)
            VALUES (%s, %s, %s, %s, %s, %s, 'processando', %s)
            RETURNING id
            """,
            (empresa_id, origem, tipo, conexao_id, api_key_id, origem_jid, user_id),
        )
        row = await cur.fetchone()
        await conn.commit()
    assert row is not None
    return int(row[0])


async def finalizar_lote(
    pool: AsyncConnectionPool,
    lote_id: int,
    *,
    status: str,
    recebidos: int = 0,
    novos: int = 0,
    atualizados: int = 0,
    pulados: int = 0,
    erro: str | None = None,
) -> None:
    """Fecha o lote com contadores e status final."""
    async with pool.connection() as conn:
        await conn.execute(
            """
            UPDATE captura_lote
               SET status = %s, total_recebidos = %s, total_novos = %s,
                   total_atualizados = %s, total_pulados_invalido = %s,
                   erro = %s, finished_at = NOW()
             WHERE id = %s
            """,
            (status, recebidos, novos, atualizados, pulados, erro, lote_id),
        )
        await conn.commit()


# ---------------------------------------------------------------------------
# Upserts idempotentes (rodam dentro de um empresa_scope + connection do chamador)
# ---------------------------------------------------------------------------


def _contact_fields(c: CapturedContact) -> dict:
    """Deriva telefone/wa_lid a partir do wa_jid cru da Evolution."""
    jid = c["wa_jid"]
    return {
        "wa_jid": jid,
        "wa_lid": jid if jid.endswith("@lid") else None,
        "telefone": phone_from_jid(jid),
        "push_name": c.get("push_name") or c.get("name"),
        "verified_name": c.get("verified_name"),
        "is_business": bool(c.get("is_business")),
    }


def _descrever_excecao(exc: BaseException) -> str:
    """Mensagem legível de uma exceção — inclusive das que não têm nenhuma.

    `str(httpx.ReadTimeout())` é string VAZIA, e foi assim que o lote 4 de
    produção terminou com status `erro` e o campo `erro` em branco: o operador
    via "falhou" sem uma linha sequer dizendo por quê. Mesmo padrão de
    `worker/processor.py`, que já resolvia isto no caminho da fila.
    """
    return str(exc) or f"{type(exc).__name__}: <sem mensagem>"


async def upsert_contato_capturado(
    conn, empresa_id: int, c: CapturedContact, lote_id: int | None, origem: str
) -> bool:
    """Upsert por (empresa_id, wa_jid). Retorna True se inseriu (novo)."""
    f = _contact_fields(c)
    cur = await conn.execute(
        """
        INSERT INTO contato_capturado
            (empresa_id, captura_lote_id, wa_jid, wa_lid, telefone, push_name,
             verified_name, is_business, origem)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (empresa_id, wa_jid) DO UPDATE
           SET push_name = COALESCE(EXCLUDED.push_name, contato_capturado.push_name),
               verified_name =
                   COALESCE(EXCLUDED.verified_name, contato_capturado.verified_name),
               telefone = COALESCE(EXCLUDED.telefone, contato_capturado.telefone),
               is_business = contato_capturado.is_business OR EXCLUDED.is_business,
               visto_ultima_vez_at = NOW()
        RETURNING (xmax = 0) AS inserted
        """,
        (
            empresa_id,
            lote_id,
            f["wa_jid"],
            f["wa_lid"],
            f["telefone"],
            f["push_name"],
            f["verified_name"],
            f["is_business"],
            origem,
        ),
    )
    row = await cur.fetchone()
    return bool(row[0]) if row else False


async def upsert_grupo(
    conn, empresa_id: int, g: CapturedGroup, conexao_id: int | None, origem: str
) -> tuple[int, bool]:
    """Upsert por (empresa_id, wa_group_id). Retorna (grupo_id, inseriu?)."""
    cur = await conn.execute(
        """
        INSERT INTO grupo
            (empresa_id, conexao_id, wa_group_id, nome, descricao, invite_link,
             participantes_count, somos_admin, origem)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (empresa_id, wa_group_id) DO UPDATE
           SET nome = COALESCE(EXCLUDED.nome, grupo.nome),
               descricao = COALESCE(EXCLUDED.descricao, grupo.descricao),
               invite_link = COALESCE(EXCLUDED.invite_link, grupo.invite_link),
               participantes_count = EXCLUDED.participantes_count,
               visto_ultima_vez_at = NOW()
        RETURNING id, (xmax = 0) AS inserted
        """,
        (
            empresa_id,
            conexao_id,
            g["wa_group_id"],
            g.get("nome"),
            g.get("descricao"),
            g.get("invite_link"),
            int(g.get("participantes_count") or 0),
            bool(g.get("somos_admin")),
            origem,
        ),
    )
    row = await cur.fetchone()
    assert row is not None
    return int(row[0]), bool(row[1])


async def upsert_grupo_membro(
    conn, empresa_id: int, grupo_id: int, wa_jid: str, is_admin: bool
) -> bool:
    """Upsert por (grupo_id, wa_jid). Retorna True se inseriu."""
    cur = await conn.execute(
        """
        INSERT INTO grupo_membro (grupo_id, empresa_id, wa_jid, telefone, is_admin)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (grupo_id, wa_jid) DO UPDATE
           SET is_admin = EXCLUDED.is_admin
        RETURNING (xmax = 0) AS inserted
        """,
        (grupo_id, empresa_id, wa_jid, phone_from_jid(wa_jid), is_admin),
    )
    row = await cur.fetchone()
    return bool(row[0]) if row else False


# ---------------------------------------------------------------------------
# Orquestração (background tasks — abrem próprio empresa_scope)
# ---------------------------------------------------------------------------


async def _evolution_client(
    pool: AsyncConnectionPool, conexao: Conexao
) -> EvolutionClient:
    from whatsapp_langchain.shared.outbound import build_outbound_client

    client, _mode = await build_outbound_client(pool, conexao)
    if not isinstance(client, EvolutionClient):
        raise ValueError("Captura server-side só é suportada em conexões Evolution")
    return client


async def capturar_contatos_evolution(
    pool: AsyncConnectionPool, empresa_id: int, conexao: Conexao, lote_id: int
) -> None:
    """Puxa contatos da Evolution e faz upsert no staging (background task)."""
    novos = atualizados = 0
    try:
        client = await _evolution_client(pool, conexao)
        contatos = await client.fetch_contacts()
        with empresa_scope(empresa_id):
            async with pool.connection() as conn:
                for c in contatos:
                    inserted = await upsert_contato_capturado(
                        conn, empresa_id, c, lote_id, "evolution_server"
                    )
                    novos += int(inserted)
                    atualizados += int(not inserted)
                await conn.commit()
        await finalizar_lote(
            pool,
            lote_id,
            status="concluido",
            recebidos=len(contatos),
            novos=novos,
            atualizados=atualizados,
        )
        logger.info(
            "captura_contatos_ok",
            empresa_id=empresa_id,
            lote_id=lote_id,
            novos=novos,
            atualizados=atualizados,
        )
    except Exception as exc:  # noqa: BLE001 — registra falha no lote
        motivo = _descrever_excecao(exc)
        logger.error("captura_contatos_erro", lote_id=lote_id, error=motivo)
        await finalizar_lote(pool, lote_id, status="erro", erro=motivo[:500])


async def capturar_grupos_evolution(
    pool: AsyncConnectionPool,
    empresa_id: int,
    conexao: Conexao,
    lote_id: int,
    com_membros: bool = True,
) -> None:
    """Puxa grupos (e opcionalmente membros) da Evolution (background task)."""
    grupos_novos = membros_novos = 0
    parcial = False
    try:
        client = await _evolution_client(pool, conexao)
        grupos = await client.fetch_groups(get_participants=com_membros)
        with empresa_scope(empresa_id):
            for g in grupos:
                async with pool.connection() as conn:
                    grupo_id, inserted = await upsert_grupo(
                        conn, empresa_id, g, conexao.id, "evolution_server"
                    )
                    grupos_novos += int(inserted)
                    await conn.commit()
                if not com_membros:
                    continue
                try:
                    membros = await client.fetch_group_participants(g["wa_group_id"])
                except Exception as exc:  # noqa: BLE001 — grupo isolado pode falhar
                    logger.warning(
                        "captura_membros_grupo_falhou",
                        grupo=g["wa_group_id"],
                        error=_descrever_excecao(exc),
                    )
                    parcial = True
                    continue
                async with pool.connection() as conn:
                    for m in membros:
                        ins = await upsert_grupo_membro(
                            conn, empresa_id, grupo_id, m["wa_jid"], m["is_admin"]
                        )
                        membros_novos += int(ins)
                    await conn.commit()
        await finalizar_lote(
            pool,
            lote_id,
            status="parcial" if parcial else "concluido",
            recebidos=len(grupos),
            novos=grupos_novos + membros_novos,
        )
        logger.info(
            "captura_grupos_ok",
            empresa_id=empresa_id,
            lote_id=lote_id,
            grupos=len(grupos),
            membros_novos=membros_novos,
        )
    except Exception as exc:  # noqa: BLE001
        motivo = _descrever_excecao(exc)
        logger.error("captura_grupos_erro", lote_id=lote_id, error=motivo)
        await finalizar_lote(pool, lote_id, status="erro", erro=motivo[:500])


# ---------------------------------------------------------------------------
# Leitura + promoção
# ---------------------------------------------------------------------------


async def get_lote(
    pool: AsyncConnectionPool, empresa_id: int, lote_id: int
) -> dict | None:
    """Status + contadores de um lote (pra polling no painel)."""
    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT id, tipo, origem, status, total_recebidos, total_novos,
                       total_atualizados, total_pulados_invalido, erro,
                       created_at, finished_at
                  FROM captura_lote WHERE id = %s AND empresa_id = %s
                """,
                (lote_id, empresa_id),
            )
            row = await cur.fetchone()
    if row is None:
        return None
    keys = [
        "id",
        "tipo",
        "origem",
        "status",
        "total_recebidos",
        "total_novos",
        "total_atualizados",
        "total_pulados_invalido",
        "erro",
        "created_at",
        "finished_at",
    ]
    return dict(zip(keys, row, strict=True))


async def listar_contatos(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    limit: int = 200,
    offset: int = 0,
    q: str | None = None,
) -> list[dict]:
    """Lista contatos capturados da empresa (browser do painel).

    `q` filtra por nome ou telefone. Sem ele, achar um contato específico numa
    base de ~20 mil significava paginar até topar com ele — o painel não tinha
    como oferecer busca honesta, porque filtrar só a página carregada acharia
    1 em cada 99.

    O termo é normalizado pra dígitos quando o operador digita telefone: ele
    cola "+55 62 98592-3866" e a coluna guarda "5562985923866".
    """
    filtro = ""
    params: list[object] = [empresa_id]
    if q and q.strip():
        termo = q.strip()
        digitos = "".join(c for c in termo if c.isdigit())
        filtro = " AND (push_name ILIKE %s OR telefone ILIKE %s)"
        params.extend([f"%{termo}%", f"%{digitos or termo}%"])
    params.extend([limit, offset])

    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            cur = await conn.execute(
                f"""
                SELECT id, wa_jid, telefone, push_name, is_business, origem,
                       cliente_id, promovido_at, created_at
                  FROM contato_capturado WHERE empresa_id = %s{filtro}
                 ORDER BY created_at DESC LIMIT %s OFFSET %s
                """,
                tuple(params),
            )
            rows = await cur.fetchall()
    keys = [
        "id",
        "wa_jid",
        "telefone",
        "push_name",
        "is_business",
        "origem",
        "cliente_id",
        "promovido_at",
        "created_at",
    ]
    return [dict(zip(keys, r, strict=True)) for r in rows]


async def listar_grupos(pool: AsyncConnectionPool, empresa_id: int) -> list[dict]:
    """Lista grupos capturados da empresa."""
    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT id, wa_group_id, nome, tipo, participantes_count,
                       invite_link, created_at
                  FROM grupo WHERE empresa_id = %s ORDER BY created_at DESC
                """,
                (empresa_id,),
            )
            rows = await cur.fetchall()
    keys = [
        "id",
        "wa_group_id",
        "nome",
        "tipo",
        "participantes_count",
        "invite_link",
        "created_at",
    ]
    return [dict(zip(keys, r, strict=True)) for r in rows]


async def promover_contatos(
    pool: AsyncConnectionPool, empresa_id: int, contato_ids: list[int]
) -> int:
    """Promove contatos do staging para o CRM `cliente` (só os com telefone).

    Faz `upsert_cliente` e marca `cliente_id`/`promovido_at`. Contatos só-LID
    (sem telefone) são pulados — `cliente` exige telefone.

    Returns:
        Quantidade efetivamente promovida.
    """
    promovidos = 0
    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT id, telefone, push_name FROM contato_capturado
                 WHERE empresa_id = %s AND id = ANY(%s)
                   AND telefone IS NOT NULL AND cliente_id IS NULL
                """,
                (empresa_id, contato_ids),
            )
            rows = await cur.fetchall()
    for contato_id, telefone, push_name in rows:
        cliente = await upsert_cliente(
            pool, empresa_id, telefone, nome=push_name or None
        )
        with empresa_scope(empresa_id):
            async with pool.connection() as conn:
                await conn.execute(
                    """
                    UPDATE contato_capturado
                       SET cliente_id = %s, promovido_at = NOW()
                     WHERE id = %s AND empresa_id = %s
                    """,
                    (cliente.id, contato_id, empresa_id),
                )
                await conn.commit()
        promovidos += 1
    return promovidos


async def contar_contatos(
    pool: AsyncConnectionPool, empresa_id: int, *, q: str | None = None
) -> dict:
    """Totais de contatos capturados da empresa (pra UI mostrar 'X de N').

    Returns: {total, promoviveis} — promoviveis = com telefone e ainda não
    promovidos ao CRM (alvo do 'Promover todos').

    `q` usa o MESMO filtro de `listar_contatos`: com busca ativa, o total tem
    que ser o do resultado, senão a paginação promete páginas que não existem.
    """
    filtro = ""
    params: list[object] = [empresa_id]
    if q and q.strip():
        termo = q.strip()
        digitos = "".join(c for c in termo if c.isdigit())
        filtro = " AND (push_name ILIKE %s OR telefone ILIKE %s)"
        params.extend([f"%{termo}%", f"%{digitos or termo}%"])

    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            cur = await conn.execute(
                f"""
                SELECT COUNT(*) AS total,
                       COUNT(*) FILTER (
                         WHERE telefone IS NOT NULL AND cliente_id IS NULL
                       ) AS promoviveis
                  FROM contato_capturado WHERE empresa_id = %s{filtro}
                """,
                tuple(params),
            )
            row = await cur.fetchone() or (0, 0)
    return {"total": int(row[0]), "promoviveis": int(row[1])}


async def promover_todos_contatos(pool: AsyncConnectionPool, empresa_id: int) -> int:
    """Promove TODOS os contatos elegíveis (com telefone, ainda não promovidos)
    ao CRM — server-side, sem depender da lista carregada na UI (que era capada
    em 200). Reusa `promover_contatos` em lotes pra não segurar transação longa.
    """
    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT id FROM contato_capturado
                 WHERE empresa_id = %s
                   AND telefone IS NOT NULL AND cliente_id IS NULL
                 ORDER BY id
                """,
                (empresa_id,),
            )
            ids = [int(r[0]) for r in await cur.fetchall()]
    promovidos = 0
    for i in range(0, len(ids), 500):
        promovidos += await promover_contatos(pool, empresa_id, ids[i : i + 500])
    return promovidos


async def despromover_contatos(
    pool: AsyncConnectionPool, empresa_id: int, contato_ids: list[int]
) -> dict:
    """Desfaz a promoção: desvincula o contato do CRM e apaga o `cliente`.

    SEGURANÇA: a FK `atendimento.cliente_id` é CASCADE — apagar um cliente com
    atendimento apagaria o histórico de conversa. Por isso só removemos do CRM
    clientes SEM atendimento; os que já têm conversa são apenas desvinculados
    do staging (continuam no CRM) e reportados em `mantidos_com_atendimento`.

    Returns:
        {"removidos": int, "mantidos_com_atendimento": int}
    """
    removidos = 0
    mantidos = 0
    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT id, cliente_id FROM contato_capturado
                 WHERE empresa_id = %s AND id = ANY(%s) AND cliente_id IS NOT NULL
                """,
                (empresa_id, contato_ids),
            )
            rows = await cur.fetchall()
            for contato_id, cliente_id in rows:
                # desvincula o staging (volta a ser selecionável)
                await conn.execute(
                    """
                    UPDATE contato_capturado
                       SET cliente_id = NULL, promovido_at = NULL
                     WHERE id = %s AND empresa_id = %s
                    """,
                    (contato_id, empresa_id),
                )
                at = await conn.execute(
                    "SELECT 1 FROM atendimento WHERE cliente_id = %s LIMIT 1",
                    (cliente_id,),
                )
                if await at.fetchone() is None:
                    # sem histórico → seguro apagar do CRM
                    await conn.execute(
                        "DELETE FROM cliente WHERE id = %s AND empresa_id = %s",
                        (cliente_id, empresa_id),
                    )
                    removidos += 1
                else:
                    mantidos += 1
            await conn.commit()
    return {"removidos": removidos, "mantidos_com_atendimento": mantidos}
