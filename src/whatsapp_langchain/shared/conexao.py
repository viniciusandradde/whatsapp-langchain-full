"""Helpers de conexão WhatsApp — lookup, CRUD, credenciais cifradas.

Cada `conexao` é uma linha (WABA ou Evolution) ligada a
uma empresa. O webhook resolve `empresa_id` + `default_agent_id` por lookup
no `phone_number_id` (WABA) ou no `instance_name`
(Evolution).

Campos sensíveis (`credentials_encrypted`, `webhook_verify_token`) NUNCA
aparecem em respostas de API — `_mask_sensitive` aplica máscara antes.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.integrations.crypto import (
    decrypt_dict,
    encrypt_dict,
)
from whatsapp_langchain.shared.models import Conexao, ConexaoInput

logger = structlog.get_logger()


_SELECT_COLS = (
    "id, empresa_id, provider, sid, from_number, display_name, "
    "default_agent_id, status, is_default, payload_json, "
    "created_at, updated_at, tipo_atendimento, whatsapp_state, "
    "waba_account_id, waba_phone_id, waba_app_id, waba_account_description, "
    "connection_state, state_message, qr_code, qr_expires_at, "
    "ultimo_health_check_at, ultimo_health_check_ok, webhook_verify_token, "
    "daily_send_cap, warmup_started_at, resposta_agrupamento_segundos, "
    "transcrever_audio_sempre"
)


def _row_to_conexao(row) -> Conexao:
    return Conexao(
        id=row[0],
        empresa_id=row[1],
        provider=row[2],
        sid=row[3],
        from_number=row[4],
        display_name=row[5],
        default_agent_id=row[6],
        status=row[7],
        is_default=row[8],
        payload_json=row[9] or {},
        created_at=row[10],
        updated_at=row[11],
        tipo_atendimento=row[12] or "ia",
        whatsapp_state=row[13],
        waba_account_id=row[14],
        waba_phone_id=row[15],
        waba_app_id=row[16],
        waba_account_description=row[17],
        connection_state=row[18] or "pending",
        state_message=row[19],
        qr_code=row[20],
        qr_expires_at=row[21],
        ultimo_health_check_at=row[22],
        ultimo_health_check_ok=row[23],
        webhook_verify_token=row[24],
        daily_send_cap=row[25],
        warmup_started_at=row[26],
        resposta_agrupamento_segundos=row[27] if row[27] is not None else 8,
        transcrever_audio_sempre=bool(row[28]),
    )


async def list_conexoes(pool: AsyncConnectionPool, empresa_id: int) -> list[Conexao]:
    """Lista as conexões ATIVAS de uma empresa (esconde soft-deleted).

    `status='disabled'` é soft-delete — não aparece pro user. Pra ver
    todas, use `list_conexoes_all`.
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {_SELECT_COLS} FROM conexao
             WHERE empresa_id = %s AND status != 'disabled'
             ORDER BY is_default DESC, display_name NULLS LAST, id ASC
            """,
            (empresa_id,),
        )
        rows = await cur.fetchall()
    return [_row_to_conexao(r) for r in rows]


async def get_conexao_padrao(
    pool: AsyncConnectionPool, empresa_id: int
) -> Conexao | None:
    """Conexão que a empresa usa quando ninguém escolhe (mig 170).

    A marcada como padrão (`is_default`, garantida única pela mig 108) e, na
    falta dela, a ativa mais antiga. Existe para o operador não ter que
    escolher número toda vez que inicia conversa: quem quiser trocar marca
    outra como padrão em /connections.
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {_SELECT_COLS} FROM conexao
             WHERE empresa_id = %s AND status = 'active'
             ORDER BY is_default DESC, id ASC
             LIMIT 1
            """,
            (empresa_id,),
        )
        row = await cur.fetchone()
    return _row_to_conexao(row) if row else None


async def get_conexao_by_id(
    pool: AsyncConnectionPool, conexao_id: int
) -> Conexao | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {_SELECT_COLS} FROM conexao WHERE id = %s", (conexao_id,)
        )
        row = await cur.fetchone()
    return _row_to_conexao(row) if row else None


async def get_conexao_by_from_number(
    pool: AsyncConnectionPool, from_number: str
) -> Conexao | None:
    """Resolve a conexão pelo número de destino (E.164, sem `whatsapp:`).

    Pode retornar None ou primeira match. Após mig 092, UNIQUE é
    (empresa_id, from_number) — então pode haver N rows com mesmo número
    em empresas diferentes. O webhook resolve pela primeira ativa.

    Sprint A.2.3: bypass RLS porque webhook ainda não sabe a empresa
    (descobre via este lookup). Após resolver, caller usa o empresa_id
    da conexão pra setar context nas queries subsequentes.
    """
    from whatsapp_langchain.shared.rls_context import empresa_scope

    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            cur = await conn.execute(
                f"""
                SELECT {_SELECT_COLS} FROM conexao
                 WHERE from_number = %s AND status = 'active'
                 ORDER BY is_default DESC, id ASC
                 LIMIT 1
                """,
                (from_number,),
            )
            row = await cur.fetchone()
    return _row_to_conexao(row) if row else None


async def is_own_connection_number(pool: AsyncConnectionPool, phone: str) -> bool:
    """True se `phone` corresponde ao número de ALGUMA conexão nossa.

    Guard anti-loop: se um inbound chega de um número que é uma das nossas
    próprias conexões (qualquer empresa, qualquer status), é bot-para-bot —
    dois agentes Nexus conversando entre si, não cliente real. O webhook
    deve ignorar pra não entrar em loop infinito (observado prod 2026-05-31:
    vsa-vinicius ↔ vsa-tecnologia trocando despedidas a cada ~23s).

    Considera variantes do 9º dígito BR (`phone_variants`) e NÃO filtra por
    status — a conexão looping pode estar 'disabled' e ainda gerar o ciclo.

    Sprint A.2.3: bypass RLS (webhook ainda não tem empresa no contexto).
    """
    if not phone:
        return False

    from whatsapp_langchain.shared.phone_br import phone_variants
    from whatsapp_langchain.shared.rls_context import empresa_scope

    variants = phone_variants(phone)
    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT 1 FROM conexao WHERE from_number = ANY(%s) LIMIT 1",
                (variants,),
            )
            row = await cur.fetchone()
    return row is not None


async def get_conexao_by_evolution_instance(
    pool: AsyncConnectionPool, instance_name: str
) -> Conexao | None:
    """Resolve conexão Evolution pelo nome da instância.

    Após mig 092, instance_name pode estar em credentials_encrypted ou
    payload_json (compat). Procura nos dois — payload_json primeiro
    pra rows legadas, depois credentials decryptadas.

    PREFERE a conexão `status='active'`: instance_names podem colidir
    (duplicatas legadas disabled). Sem isso, o `LIMIT 1` podia devolver a
    conexão disabled e o webhook era ignorado mesmo com a active certa
    cadastrada (bug observado prod 2026-06-01).

    Sprint A.2.3: bypass RLS (webhook descobre empresa via este lookup).
    """
    from whatsapp_langchain.shared.rls_context import empresa_scope

    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            cur = await conn.execute(
                f"""
                SELECT {_SELECT_COLS} FROM conexao
                 WHERE provider = 'evolution'
                   AND payload_json->>'instance_name' = %s
                 ORDER BY (status = 'active') DESC, id DESC
                 LIMIT 1
                """,
                (instance_name,),
            )
            row = await cur.fetchone()
        if row:
            return _row_to_conexao(row)

        # Fallback: percorre conexões evolution com credentials_encrypted
        # (active primeiro, mesmo critério da query principal).
        async with pool.connection() as conn:
            cur = await conn.execute(
                f"""
                SELECT {_SELECT_COLS}, credentials_encrypted FROM conexao
                 WHERE provider = 'evolution' AND credentials_encrypted IS NOT NULL
                 ORDER BY (status = 'active') DESC, id DESC
                """,
                (),
            )
            rows = await cur.fetchall()
        for r in rows:
            try:
                # `credentials_encrypted` NÃO está em _SELECT_COLS — é anexada
                # nesta query e lida pela ponta. O índice era derivado do
                # tamanho de _SELECT_COLS e caía numa coluna qualquer, então
                # decrypt_dict sempre estourava e o `continue` engolia: este
                # fallback nunca resolveu conexão nenhuma.
                cred = decrypt_dict(r[-1])  # type: ignore[arg-type]
            except Exception:
                continue
            if cred.get("instance_name") == instance_name:
                return _row_to_conexao(r)
    return None


async def get_conexao_by_waba_phone_id(
    pool: AsyncConnectionPool, phone_id: str
) -> Conexao | None:
    """Resolve conexão WABA pelo phone_number_id (do webhook Meta).

    Sprint A.2.3: bypass RLS (webhook descobre empresa via este lookup).
    """
    from whatsapp_langchain.shared.rls_context import empresa_scope

    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            cur = await conn.execute(
                f"""
                SELECT {_SELECT_COLS} FROM conexao
                 WHERE waba_phone_id = %s AND status = 'active'
                 LIMIT 1
                """,
                (phone_id,),
            )
            row = await cur.fetchone()
    return _row_to_conexao(row) if row else None


async def upsert_conexao(
    pool: AsyncConnectionPool, empresa_id: int, data: ConexaoInput
) -> Conexao:
    """Cria/atualiza conexão.

    Após mig 092, UNIQUE é (empresa_id, from_number) — não mais global.

    Sprint conexão padrão: quando `data.is_default=True`, faz batch unset nas
    OUTRAS conexões da mesma empresa ANTES do INSERT, na mesma conexão psycopg
    pra evitar violação do UNIQUE INDEX parcial (mig 108) durante o cutover.
    """
    async with pool.connection() as conn:
        # 1) Pré-condição pra single-default: desliga as outras antes do INSERT.
        #    Sem isso, o UNIQUE INDEX parcial (mig 108) levantaria erro de
        #    integridade quando admin tenta promover uma segunda conexão.
        if data.is_default:
            await conn.execute(
                "UPDATE conexao SET is_default = FALSE, updated_at = NOW() "
                " WHERE empresa_id = %s AND is_default = TRUE "
                "   AND from_number != %s",
                (empresa_id, data.from_number),
            )
        cur = await conn.execute(
            f"""
            INSERT INTO conexao (empresa_id, provider, sid, from_number,
                                 display_name, default_agent_id, status,
                                 is_default, payload_json, tipo_atendimento)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, COALESCE(%s, 'manual'))
            ON CONFLICT (empresa_id, from_number) DO UPDATE SET
                provider = EXCLUDED.provider,
                sid = EXCLUDED.sid,
                display_name = EXCLUDED.display_name,
                default_agent_id = EXCLUDED.default_agent_id,
                status = EXCLUDED.status,
                is_default = EXCLUDED.is_default,
                payload_json = EXCLUDED.payload_json,
                -- NÃO usar EXCLUDED aqui: o VALUES já aplica o COALESCE com
                -- 'manual', então EXCLUDED nunca é NULL e resetaria conexões
                -- existentes pro default a cada reconexão (Evolution/WABA
                -- re-upsertam).
                --
                -- E o comentário não pode citar o marcador de parâmetro: o
                -- psycopg varre o texto INTEIRO da query, comentário incluso.
                -- Com ele aqui eram 12 marcadores para 11 parâmetros, e todo
                -- upsert de conexão morria em ProgrammingError.
                tipo_atendimento = COALESCE(%s, conexao.tipo_atendimento),
                updated_at = NOW()
            RETURNING {_SELECT_COLS}
            """,
            (
                empresa_id,
                data.provider,
                data.sid,
                data.from_number,
                data.display_name,
                data.default_agent_id,
                data.status,
                data.is_default,
                json.dumps(data.payload_json),
                data.tipo_atendimento,
                data.tipo_atendimento,
            ),
        )
        row = await cur.fetchone()
    assert row is not None
    result = _row_to_conexao(row)

    return result


#: Modos de atendimento que invocam o agente e, portanto, exigem um agente da
#: empresa cadastrado (linha em `agente_ia`). `manual` não invoca ninguém.
MODOS_QUE_EXIGEM_AGENTE = ("ia", "hibrido")


async def validar_agente_da_empresa_para_ia(
    pool: AsyncConnectionPool,
    empresa_id: int,
    tipo_atendimento: str | None,
    default_agent_id: str | None,
) -> str | None:
    """Mensagem de erro (pt-BR) se o modo exige agente e não há um cadastrado
    na empresa; `None` se está tudo certo.

    Ligar `tipo_atendimento='ia'` numa conexão cujo `default_agent_id` não tem
    linha em `agente_ia` da empresa fazia o worker cair no **template de
    exemplo do catálogo** (`vsa_tech`, prompt genérico da VSA Tech) — o dono
    ligou a IA "sem agente cadastrado" e o cliente recebeu resposta mesmo
    assim (incidente 2026-08-19). O critério aqui é exatamente o que decide o
    fallback no runtime: se `resolve_agente_runtime` devolve `None`, o worker
    usaria o legacy — então o save é bloqueado. Ver
    `worker/processor.py` (rede de segurança equivalente no runtime).
    """
    if tipo_atendimento not in MODOS_QUE_EXIGEM_AGENTE:
        return None
    # Import tardio evita ciclo (agente.py depende de conexao.py).
    from whatsapp_langchain.shared.agente import resolve_agente_runtime

    runtime = await resolve_agente_runtime(pool, empresa_id, default_agent_id or "")
    if runtime is not None:
        return None
    return (
        "Cadastre e ative um agente da empresa antes de ligar o modo "
        "automático (IA) nesta conexão. O agente de exemplo do catálogo não "
        "responde aos seus clientes."
    )


async def patch_conexao(
    pool: AsyncConnectionPool,
    conexao_id: int,
    *,
    display_name: str | None = None,
    default_agent_id: str | None = None,
    is_default: bool | None = None,
    tipo_atendimento: str | None = None,
    status: str | None = None,
    daily_send_cap: int | None = None,
    warmup_enabled: bool | None = None,
    resposta_agrupamento_segundos: int | None = None,
    transcrever_audio_sempre: bool | None = None,
) -> Conexao | None:
    """UPDATE parcial — só seta colunas não-None.

    Anti-ban: `daily_send_cap` <= 0 limpa o teto (NULL); `warmup_enabled` True
    inicia o aquecimento (preserva a curva se já estava ligado via COALESCE),
    False desliga (warmup_started_at = NULL).

    Agrupamento (mig 144): `resposta_agrupamento_segundos` = 0 é valor VÁLIDO
    (desliga o agrupamento), não "não informado" — por isso o teste é
    `is not None` e não truthiness.
    """
    sets: list[str] = []
    args: list[Any] = []
    if display_name is not None:
        sets.append("display_name = %s")
        args.append(display_name)
    if default_agent_id is not None:
        sets.append("default_agent_id = %s")
        args.append(default_agent_id)
    if is_default is not None:
        sets.append("is_default = %s")
        args.append(is_default)
    if tipo_atendimento is not None:
        sets.append("tipo_atendimento = %s")
        args.append(tipo_atendimento)
    if status is not None and status in ("active", "disabled"):
        sets.append("status = %s")
        args.append(status)
    if daily_send_cap is not None:
        if daily_send_cap <= 0:
            sets.append("daily_send_cap = NULL")
        else:
            sets.append("daily_send_cap = %s")
            args.append(daily_send_cap)
    if warmup_enabled is not None:
        if warmup_enabled:
            sets.append("warmup_started_at = COALESCE(warmup_started_at, NOW())")
        else:
            sets.append("warmup_started_at = NULL")
    if resposta_agrupamento_segundos is not None:
        # Clamp na faixa do CHECK do banco — a UI já valida, mas o endpoint
        # aceita chamada direta e um 500 de constraint não ajuda ninguém.
        sets.append("resposta_agrupamento_segundos = %s")
        args.append(max(0, min(60, resposta_agrupamento_segundos)))

    if transcrever_audio_sempre is not None:
        sets.append("transcrever_audio_sempre = %s")
        args.append(transcrever_audio_sempre)

    if not sets:
        return await get_conexao_by_id(pool, conexao_id)

    sets.append("updated_at = NOW()")
    args.append(conexao_id)
    query = (
        f"UPDATE conexao SET {', '.join(sets)} WHERE id = %s RETURNING {_SELECT_COLS}"
    )
    async with pool.connection() as conn:
        # Sprint conexão padrão: quando promove esta pra is_default=TRUE,
        # desliga as outras da MESMA empresa antes do UPDATE alvo. Sem isso o
        # UNIQUE INDEX parcial (mig 108) rejeita ter 2 defaults na empresa.
        # Mesma conexão psycopg = atômico (autocommit dentro do bloco).
        if is_default is True:
            await conn.execute(
                "UPDATE conexao SET is_default = FALSE, updated_at = NOW() "
                " WHERE id != %s "
                "   AND is_default = TRUE "
                "   AND empresa_id = ("
                "       SELECT empresa_id FROM conexao WHERE id = %s"
                "   )",
                (conexao_id, conexao_id),
            )
        cur = await conn.execute(query, tuple(args))  # type: ignore[arg-type]
        row = await cur.fetchone()
    return _row_to_conexao(row) if row else None


async def set_conexao_status(
    pool: AsyncConnectionPool, conexao_id: int, status: str
) -> None:
    """Atualiza status (active/disabled/error)."""
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE conexao SET status = %s, updated_at = NOW() WHERE id = %s",
            (status, conexao_id),
        )


async def set_conexao_from_number(
    pool: AsyncConnectionPool, conexao_id: int, from_number: str
) -> None:
    """Atualiza o from_number (usado pra trocar o placeholder `evolution:<inst>`
    pelo número real após a sessão conectar). Best-effort: se colidir com o
    UNIQUE (empresa_id, from_number), a exceção sobe pro caller tratar."""
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE conexao SET from_number = %s, updated_at = NOW() WHERE id = %s",
            (from_number, conexao_id),
        )


async def hard_delete_conexao(
    pool: AsyncConnectionPool, conexao_id: int, empresa_id: int
) -> bool:
    """Remove a linha de conexao do banco (exclusão total, sem deixar órfã).

    FKs: message_queue/campanha/captura_lote/grupo/**atendimento** → SET NULL
    (mig 129 desacoplou o atendimento → ele PERSISTE com conexao_id=NULL +
    snapshot do canal); menu_chatbot/waba_template/usuario_conexao/
    conexao_envio_diario → CASCADE. O try/except fica como defesa caso alguma
    outra FK passe a bloquear no futuro (hoje: nenhuma) → caller faz soft-delete.
    WHERE com empresa_id = defesa em profundidade.

    Retorna True se a linha foi removida, False se um FK bloqueou.
    """
    from psycopg.errors import ForeignKeyViolation

    try:
        async with pool.connection() as conn, conn.transaction():
            cur = await conn.execute(
                "DELETE FROM conexao WHERE id = %s AND empresa_id = %s",
                (conexao_id, empresa_id),
            )
            return cur.rowcount > 0
    except ForeignKeyViolation:
        return False


async def set_connection_state(
    pool: AsyncConnectionPool,
    conexao_id: int,
    *,
    state: str,
    message: str | None = None,
) -> None:
    """Atualiza state machine (pending → qr_pending → open/ready/disconnected)."""
    async with pool.connection() as conn:
        await conn.execute(
            """
            UPDATE conexao
               SET connection_state = %s, state_message = %s, updated_at = NOW()
             WHERE id = %s
            """,
            (state, message, conexao_id),
        )


async def set_qr_code(
    pool: AsyncConnectionPool,
    conexao_id: int,
    *,
    qr_base64: str | None,
    expires_at: datetime | None,
    state: str = "qr_pending",
) -> None:
    """Salva QR (Evolution) + TTL pro polling do front.

    `state` permite reusar a mesma coluna `qr_code`/`qr_expires_at` pro código
    de pareamento (`state='pairing_code_pending'`) — só o estado diferencia.
    """
    async with pool.connection() as conn:
        await conn.execute(
            """
            UPDATE conexao
               SET qr_code = %s, qr_expires_at = %s,
                   connection_state = %s, updated_at = NOW()
             WHERE id = %s
            """,
            (qr_base64, expires_at, state, conexao_id),
        )


async def record_health_check(
    pool: AsyncConnectionPool, conexao_id: int, *, ok: bool, message: str | None = None
) -> None:
    """Persiste resultado de POST /api/conexoes/{id}/test."""
    async with pool.connection() as conn:
        await conn.execute(
            """
            UPDATE conexao
               SET ultimo_health_check_at = NOW(),
                   ultimo_health_check_ok = %s,
                   state_message = COALESCE(%s, state_message),
                   updated_at = NOW()
             WHERE id = %s
            """,
            (ok, message, conexao_id),
        )


async def save_credentials(
    pool: AsyncConnectionPool, conexao_id: int, credentials: dict
) -> None:
    """Cifra credentials dict e grava em credentials_encrypted."""
    encrypted = encrypt_dict(credentials)
    async with pool.connection() as conn:
        await conn.execute(
            """
            UPDATE conexao SET credentials_encrypted = %s, updated_at = NOW()
             WHERE id = %s
            """,
            (encrypted, conexao_id),
        )


async def get_credentials_decrypted(
    pool: AsyncConnectionPool, conexao_id: int
) -> dict | None:
    """Decifra credentials. Retorna None se vazio. Pode lançar IntegracaoConfigError."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT credentials_encrypted FROM conexao WHERE id = %s",
            (conexao_id,),
        )
        row = await cur.fetchone()
    if not row or not row[0]:
        return None
    return decrypt_dict(row[0])


async def update_waba_fields(
    pool: AsyncConnectionPool,
    conexao_id: int,
    *,
    waba_account_id: str,
    waba_phone_id: str,
    waba_app_id: str | None = None,
    waba_account_description: str | None = None,
    webhook_verify_token: str | None = None,
    from_number: str | None = None,
) -> None:
    """Salva config WABA específica após embedded signup."""
    async with pool.connection() as conn:
        await conn.execute(
            """
            UPDATE conexao
               SET waba_account_id = %s,
                   waba_phone_id = %s,
                   waba_app_id = COALESCE(%s, waba_app_id),
                   waba_account_description = COALESCE(%s, waba_account_description),
                   webhook_verify_token = COALESCE(%s, webhook_verify_token),
                   from_number = COALESCE(%s, from_number),
                   updated_at = NOW()
             WHERE id = %s
            """,
            (
                waba_account_id,
                waba_phone_id,
                waba_app_id,
                waba_account_description,
                webhook_verify_token,
                from_number,
                conexao_id,
            ),
        )


def mask_sensitive(conexao: Conexao) -> Conexao:
    """Retorna cópia com campos sensíveis mascarados pra exibição."""
    data = conexao.model_dump()
    if data.get("webhook_verify_token"):
        data["webhook_verify_token"] = "••••••••"
    return Conexao(**data)
