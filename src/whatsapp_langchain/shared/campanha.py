"""CRUD + dispatcher de Campanha (E2.D M6.b).

Modelo de execução:
- Cria campanha em `draft` com lista de telefones (rows pendentes).
- Endpoint dispatch agenda asyncio.create_task em background; o handler
  retorna 202 imediatamente.
- Background task itera destinatarios pendentes, envia via OutboundClient
  do provider da Conexao, atualiza status e contadores. Cooldown
  configurável (default 500ms) pra não martelar provider.
- UI faz polling no GET /api/campanhas/{id} pra ver progresso.

Não usa message_queue — campanha é fluxo OUTBOUND puro, não passa pelo
agente. Persiste em `campanha_destinatario` direto.
"""

from __future__ import annotations

import asyncio
import json as _json
import random
import re
from dataclasses import dataclass, field
from datetime import datetime

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.conexao import (
    get_conexao_by_id,
    list_conexoes,
)
from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.outbound import _build_client, send_template_by_id

logger = structlog.get_logger()


# Aceita +5511999999999 ou variações com espaço/parênteses; remove tudo
# que não for dígito e prepende +.
_PHONE_DIGITS = re.compile(r"\D")


def normalize_phone(raw: str) -> str | None:
    """Normaliza telefone pra E.164 minimalista. Retorna None se < 8
    dígitos (provavelmente lixo) ou se já vier vazio."""
    s = (raw or "").strip()
    if not s:
        return None
    digits = _PHONE_DIGITS.sub("", s)
    if len(digits) < 8:
        return None
    return f"+{digits}"


# ---- CRUD campanha ----


@dataclass
class CampanhaSummary:
    id: int
    empresa_id: int
    nome: str
    descricao: str | None
    mensagem: str | None
    conexao_id: int | None
    status: str
    intervalo_ms: int
    max_destinatarios: int
    total_destinatarios: int
    enviados: int
    falhas: int
    started_at: datetime | None
    finished_at: datetime | None
    created_by_user_id: str | None
    created_at: datetime
    updated_at: datetime
    # Sub-fase B+ (padrão profissional) (mig 051)
    modelo_mensagem_id: int | None = None
    scheduled_at: datetime | None = None
    tipo: str = "broadcast"
    filtro_segmento: str | None = None
    filtro_tags: list[str] | None = None
    # Template HSM (mig 113) — broadcast fora da janela 24h
    message_template_id: int | None = None
    template_variaveis: dict = field(default_factory=dict)
    # Mídia (foto) — mig 123. mensagem vira legenda quando há media_url.
    media_url: str | None = None
    media_tipo: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "empresa_id": self.empresa_id,
            "nome": self.nome,
            "descricao": self.descricao,
            "mensagem": self.mensagem,
            "conexao_id": self.conexao_id,
            "status": self.status,
            "intervalo_ms": self.intervalo_ms,
            "max_destinatarios": self.max_destinatarios,
            "total_destinatarios": self.total_destinatarios,
            "enviados": self.enviados,
            "falhas": self.falhas,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "created_by_user_id": self.created_by_user_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            # B+ padrão profissional
            "modelo_mensagem_id": self.modelo_mensagem_id,
            "scheduled_at": (
                self.scheduled_at.isoformat() if self.scheduled_at else None
            ),
            "tipo": self.tipo,
            "filtro_segmento": self.filtro_segmento,
            "filtro_tags": list(self.filtro_tags or []),
            "message_template_id": self.message_template_id,
            "template_variaveis": dict(self.template_variaveis or {}),
            "media_url": self.media_url,
            "media_tipo": self.media_tipo,
        }


_COLS = (
    "id, empresa_id, nome, descricao, mensagem, conexao_id, status, "
    "intervalo_ms, max_destinatarios, total_destinatarios, enviados, falhas, "
    "started_at, finished_at, created_by_user_id, created_at, updated_at, "
    # B+ padrão profissional (mig 051)
    "modelo_mensagem_id, scheduled_at, tipo, filtro_segmento, filtro_tags, "
    # Template HSM (mig 113)
    "message_template_id, template_variaveis, "
    # Mídia (mig 123)
    "media_url, media_tipo"
)


def _row_to_camp(row) -> CampanhaSummary:
    return CampanhaSummary(*row)


async def list_campanhas(pool: AsyncConnectionPool, empresa_id: int) -> list[dict]:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {_COLS} FROM campanha WHERE empresa_id = %s "
            "ORDER BY created_at DESC LIMIT 100",
            (empresa_id,),
        )
        rows = await cur.fetchall()
    return [_row_to_camp(r).to_dict() for r in rows]


async def get_campanha(
    pool: AsyncConnectionPool, empresa_id: int, camp_id: int
) -> dict | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {_COLS} FROM campanha WHERE id = %s AND empresa_id = %s",
            (camp_id, empresa_id),
        )
        row = await cur.fetchone()
    return _row_to_camp(row).to_dict() if row else None


async def create_campanha(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    nome: str,
    descricao: str | None,
    mensagem: str | None,
    conexao_id: int | None,
    intervalo_ms: int,
    max_destinatarios: int,
    telefones_brutos: list[str],
    user_id: str | None,
    # Sub-fase B+ (padrão profissional) (mig 051)
    modelo_mensagem_id: int | None = None,
    scheduled_at: str | None = None,
    tipo: str = "broadcast",
    filtro_segmento: str | None = None,
    filtro_tags: list[str] | None = None,
    # Template HSM (mig 113)
    message_template_id: int | None = None,
    template_variaveis: dict | None = None,
    # Anti-ban configurável (migs 120/121) — jitter + kill-switch
    intervalo_min_ms: int | None = None,
    intervalo_max_ms: int | None = None,
    kill_switch_pct: int | None = None,
    # Mídia (mig 123) — foto/vídeo/doc; mensagem vira legenda
    media_url: str | None = None,
    media_tipo: str | None = None,
) -> dict:
    """Cria campanha + insere destinatários. Telefones inválidos são
    descartados silenciosamente; o caller pode chamar
    `validate_phones` antes pra reportar erros ao user.

    Anti-ban: se `intervalo_min_ms`/`intervalo_max_ms` vierem, definem a faixa
    de jitter aleatório por destinatário; senão caem no `intervalo_ms` legado.
    `kill_switch_pct` aborta a campanha quando a taxa de falha estoura."""
    # Faixa de jitter efetiva (CHECK do banco exige min <= max).
    eff_min = intervalo_min_ms if intervalo_min_ms is not None else intervalo_ms
    eff_max = (
        intervalo_max_ms if intervalo_max_ms is not None else max(intervalo_ms, eff_min)
    )
    if eff_min > eff_max:
        eff_min, eff_max = eff_max, eff_min
    eff_kill = kill_switch_pct if kill_switch_pct is not None else 30
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in telefones_brutos:
        n = normalize_phone(raw)
        if n is None or n in seen:
            continue
        seen.add(n)
        normalized.append(n)

    if not normalized:
        raise ValueError("Nenhum telefone válido na lista")
    if len(normalized) > max_destinatarios:
        raise ValueError(
            f"{len(normalized)} destinatários > limite {max_destinatarios}"
        )

    async with pool.connection() as conn:
        async with conn.transaction():
            cur = await conn.execute(
                f"""
                INSERT INTO campanha
                    (empresa_id, nome, descricao, mensagem, conexao_id,
                     intervalo_ms, max_destinatarios, total_destinatarios,
                     created_by_user_id,
                     modelo_mensagem_id, scheduled_at, tipo,
                     filtro_segmento, filtro_tags,
                     message_template_id, template_variaveis,
                     intervalo_min_ms, intervalo_max_ms, kill_switch_pct,
                     media_url, media_tipo)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s::text[], %s, %s::jsonb, %s, %s, %s, %s, %s)
                RETURNING {_COLS}
                """,
                (
                    empresa_id,
                    nome,
                    descricao,
                    mensagem,
                    conexao_id,
                    intervalo_ms,
                    max_destinatarios,
                    len(normalized),
                    user_id,
                    modelo_mensagem_id,
                    scheduled_at,
                    tipo,
                    filtro_segmento,
                    list(filtro_tags or []) if filtro_tags is not None else None,
                    message_template_id,
                    _json.dumps(template_variaveis or {}),
                    eff_min,
                    eff_max,
                    eff_kill,
                    media_url,
                    media_tipo,
                ),
            )
            row = await cur.fetchone()
            assert row is not None
            camp = _row_to_camp(row)

            # Bulk insert destinatarios
            for phone in normalized:
                await conn.execute(
                    """
                    INSERT INTO campanha_destinatario (campanha_id, telefone)
                    VALUES (%s, %s)
                    ON CONFLICT (campanha_id, telefone) DO NOTHING
                    """,
                    (camp.id, phone),
                )

    logger.info(
        "campanha_created",
        empresa_id=empresa_id,
        camp_id=camp.id,
        total=len(normalized),
    )
    return camp.to_dict()


async def list_destinatarios(
    pool: AsyncConnectionPool, camp_id: int, *, limit: int = 200
) -> list[dict]:
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT id, telefone, status, mensagem_id_externo, erro, sent_at
              FROM campanha_destinatario
             WHERE campanha_id = %s
             ORDER BY id
             LIMIT %s
            """,
            (camp_id, limit),
        )
        rows = await cur.fetchall()
    return [
        {
            "id": r[0],
            "telefone": r[1],
            "status": r[2],
            "mensagem_id_externo": r[3],
            "erro": r[4],
            "sent_at": r[5].isoformat() if r[5] else None,
        }
        for r in rows
    ]


async def abort_campanha(
    pool: AsyncConnectionPool, empresa_id: int, camp_id: int
) -> bool:
    """Marca campanha como aborted. Background task detecta no próximo
    loop e para o envio."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            UPDATE campanha
               SET status = 'aborted', finished_at = NOW(), updated_at = NOW()
             WHERE id = %s AND empresa_id = %s
               AND status IN ('draft', 'running')
            """,
            (camp_id, empresa_id),
        )
        await conn.commit()
        return (cur.rowcount or 0) > 0


# ---- Dispatcher background ----


def _apply_tokens(
    text: str, cliente_nome: str | None, variaveis: dict | None = None
) -> str:
    """Substitui tokens `{{chave}}` e `[chave]` num texto.

    Contexto: `nome` (primeiro nome do cliente) + as `variaveis` por
    destinatário (vindas do CSV). Personalização central do disparo.
    """
    primeiro = (cliente_nome or "").strip().split(" ")[0] if cliente_nome else ""
    ctx: dict[str, str] = {"nome": primeiro}
    if variaveis:
        ctx.update({str(k): str(v) for k, v in variaveis.items()})
    out = text or ""
    for ck, cv in ctx.items():
        out = out.replace("{{" + ck + "}}", cv).replace("[" + ck + "]", cv)
    return out


def _resolve_template_vars(
    base: dict | None, cliente_nome: str | None, variaveis: dict | None = None
) -> dict[str, str]:
    """Resolve as variáveis posicionais do template HSM por destinatário.

    Cada valor do template (ex: "Olá {{nome}}") tem seus tokens substituídos
    pelo contexto do destinatário (nome + `variaveis` do CSV).
    """
    return {
        str(k): _apply_tokens(str(v), cliente_nome, variaveis)
        for k, v in (base or {}).items()
    }


def _jitter_delay_s(min_ms: int | None, max_ms: int | None) -> float:
    """Sorteia um atraso (s) entre min e max ms — jitter anti-ban.

    Tolera min>max (troca), valores None/0 (retorna 0). Cadência aleatória
    imita comportamento humano e dilui o padrão detectável de bot.
    """
    lo = min_ms or 0
    hi = max_ms or 0
    if hi < lo:
        lo, hi = hi, lo
    if hi <= 0:
        return 0.0
    return random.uniform(lo, hi) / 1000.0


# Mínimo de tentativas antes do kill-switch poder agir (evita abortar por uma
# falha isolada no começo).
KILL_SWITCH_MIN_AMOSTRA = 20


def _should_kill_switch(
    enviados: int,
    falhas: int,
    pct: int | None,
    *,
    min_amostra: int = KILL_SWITCH_MIN_AMOSTRA,
) -> bool:
    """True se a taxa de falha estourou o limite (sinal de lista ruim/ban).

    Só age depois de uma amostra mínima de tentativas. ``pct`` None/<=0 desliga.
    """
    if not pct or pct <= 0:
        return False
    tentados = enviados + falhas
    if tentados < min_amostra:
        return False
    return (falhas / tentados) * 100 > pct


async def _dispatch_loop(
    pool: AsyncConnectionPool, empresa_id: int, camp_id: int
) -> None:
    """Loop de envio executado em asyncio.create_task.

    Lê telefones pendentes em batches de 50, envia 1 a 1 com cooldown.
    Re-checa status da campanha a cada item — se virou 'aborted',
    para imediatamente (deixa pendentes como 'pendente').
    """
    log = logger.bind(camp_id=camp_id, empresa_id=empresa_id)
    log.info("campanha_dispatch_started")

    camp = await get_campanha(pool, empresa_id, camp_id)
    if camp is None or camp["status"] != "draft":
        log.warning("campanha_dispatch_invalid_state", status=camp and camp["status"])
        return

    # Resolve conexão: se não especificada, primeira ativa
    conexao_id = camp["conexao_id"]
    if conexao_id is None:
        conexoes = await list_conexoes(pool, empresa_id)  # já retorna só ativas
        if not conexoes:
            await _mark_finished(pool, camp_id, "aborted", reason="sem conexão ativa")
            log.error("campanha_no_active_conexao")
            return
        conexao = conexoes[0]
    else:
        conexao = await get_conexao_by_id(pool, conexao_id)
        if conexao is None or conexao.empresa_id != empresa_id:
            await _mark_finished(pool, camp_id, "aborted", reason="conexão inválida")
            log.error("campanha_invalid_conexao", conexao_id=conexao_id)
            return

    template_id = camp.get("message_template_id")
    media_url = camp.get("media_url")
    media_tipo = camp.get("media_tipo") or "image"
    # Evolution busca a mídia por URL pública — resolve path relativo
    # (/uploads/disparador/..) para absoluto via public_base_url.
    if media_url and media_url.startswith("/"):
        base = (settings.public_base_url or "").rstrip("/")
        if base:
            media_url = f"{base}{media_url}"
        else:
            log.warning("campanha_media_sem_public_base_url", media_url=media_url)
    if not template_id and not media_url and not (camp.get("mensagem") or "").strip():
        await _mark_finished(pool, camp_id, "aborted", reason="sem conteúdo")
        log.error("campanha_sem_conteudo")
        return

    client, _mode = await _build_client(pool, conexao)

    # Faixa de jitter anti-ban (fallback pro intervalo_ms fixo legado).
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT intervalo_min_ms, intervalo_max_ms, kill_switch_pct "
            "FROM campanha WHERE id = %s",
            (camp_id,),
        )
        jrow = await cur.fetchone()
    fixo = camp["intervalo_ms"]
    min_ms = (jrow[0] if jrow else None) or fixo
    max_ms = (jrow[1] if jrow else None) or fixo
    kill_pct = jrow[2] if jrow else None

    # Marca como running
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE campanha SET status='running', started_at=NOW(), updated_at=NOW() "
            "WHERE id = %s AND status='draft'",
            (camp_id,),
        )
        await conn.commit()

    while True:
        # Recheca abort a cada batch
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT status FROM campanha WHERE id = %s",
                (camp_id,),
            )
            srow = await cur.fetchone()
        if srow is None or srow[0] != "running":
            log.info("campanha_dispatch_stopped", status=srow and srow[0])
            return

        # Pega próximo lote de pendentes
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT cd.id, cd.telefone, c.nome, cd.variaveis
                  FROM campanha_destinatario cd
                  LEFT JOIN cliente c ON c.id = cd.cliente_id
                 WHERE cd.campanha_id = %s AND cd.status = 'pendente'
                 ORDER BY cd.id
                 LIMIT 50
                """,
                (camp_id,),
            )
            batch = await cur.fetchall()

        if not batch:
            # Tudo enviado — marca done (ou partial se houve falhas)
            async with pool.connection() as conn:
                cur = await conn.execute(
                    "SELECT enviados, falhas, total_destinatarios "
                    "FROM campanha WHERE id = %s",
                    (camp_id,),
                )
                stats = await cur.fetchone()
            if stats is None:
                return
            envs, falhas, total = stats
            new_status = "done" if envs == total else "partial"
            await _mark_finished(pool, camp_id, new_status)
            log.info(
                "campanha_dispatch_finished",
                status=new_status,
                enviados=envs,
                falhas=falhas,
            )
            return

        for dest_id, phone, cliente_nome, variaveis in batch:
            try:
                if template_id:
                    res = await send_template_by_id(
                        pool,
                        conexao_id=conexao.id,
                        empresa_id=empresa_id,
                        to=phone,
                        template_id=template_id,
                        variables=_resolve_template_vars(
                            camp.get("template_variaveis"), cliente_nome, variaveis
                        ),
                    )
                    provider_msg_id = res["provider_message_id"]
                elif media_url:
                    # Disparo com mídia (foto): legenda = texto da campanha.
                    legenda = _apply_tokens(
                        camp.get("mensagem") or "", cliente_nome, variaveis
                    )
                    send_media = getattr(client, "send_media", None)
                    if send_media is None:
                        raise RuntimeError(
                            "Conexão não suporta envio de mídia (use Evolution)."
                        )
                    provider_msg_id = await send_media(
                        phone,
                        media_url,
                        mediatype=media_tipo,
                        caption=legenda or None,
                    )
                else:
                    provider_msg_id = await client.send_message(
                        phone,
                        _apply_tokens(
                            camp.get("mensagem") or "", cliente_nome, variaveis
                        ),
                    )
                async with pool.connection() as conn:
                    await conn.execute(
                        """
                        UPDATE campanha_destinatario
                           SET status='enviado', mensagem_id_externo=%s, sent_at=NOW()
                         WHERE id = %s
                        """,
                        (provider_msg_id, dest_id),
                    )
                    await conn.execute(
                        "UPDATE campanha SET enviados = enviados + 1, "
                        "updated_at=NOW() WHERE id = %s",
                        (camp_id,),
                    )
                    await conn.commit()
            except Exception as e:  # noqa: BLE001 — gravamos a falha
                err = str(e)[:500]
                async with pool.connection() as conn:
                    await conn.execute(
                        """
                        UPDATE campanha_destinatario
                           SET status='falhou', erro=%s, sent_at=NOW()
                         WHERE id = %s
                        """,
                        (err, dest_id),
                    )
                    await conn.execute(
                        "UPDATE campanha SET falhas = falhas + 1, "
                        "updated_at=NOW() WHERE id = %s",
                        (camp_id,),
                    )
                    await conn.commit()
                log.warning(
                    "campanha_send_failed", dest_id=dest_id, phone=phone, error=err
                )

            delay_s = _jitter_delay_s(min_ms, max_ms)
            if delay_s > 0:
                await asyncio.sleep(delay_s)

        # Kill-switch: aborta se a taxa de falha estourar o limite (lista ruim
        # / número comprometido). Checa por batch pra reagir cedo.
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT enviados, falhas FROM campanha WHERE id = %s",
                (camp_id,),
            )
            krow = await cur.fetchone()
        if krow and _should_kill_switch(krow[0], krow[1], kill_pct):
            await _mark_finished(
                pool,
                camp_id,
                "aborted",
                reason=f"kill-switch: falhas {krow[1]}/{krow[0] + krow[1]} > {kill_pct}%",
            )
            log.warning(
                "campanha_kill_switch", enviados=krow[0], falhas=krow[1], pct=kill_pct
            )
            return


async def _mark_finished(
    pool: AsyncConnectionPool, camp_id: int, status: str, *, reason: str | None = None
) -> None:
    async with pool.connection() as conn:
        await conn.execute(
            """
            UPDATE campanha
               SET status = %s, finished_at = NOW(), updated_at = NOW(),
                   aborted_reason = COALESCE(%s, aborted_reason),
                   descricao = COALESCE(descricao, '') || COALESCE(%s, '')
             WHERE id = %s
            """,
            (
                status,
                reason,
                f"\n[motivo: {reason}]" if reason else None,
                camp_id,
            ),
        )
        await conn.commit()


# Refs fortes pras tasks de dispatch — sem isso o GC pode coletar a task no
# meio da campanha (o event loop só guarda referência fraca; asyncio docs).
_BG_TASKS: set[asyncio.Task] = set()


def schedule_dispatch(
    pool: AsyncConnectionPool, empresa_id: int, camp_id: int
) -> asyncio.Task:
    """Agenda dispatch em background via asyncio.create_task. Retorna
    a Task pra logging — endpoint não precisa await."""
    task = asyncio.create_task(_dispatch_loop(pool, empresa_id, camp_id))
    _BG_TASKS.add(task)

    def _on_done(t: asyncio.Task) -> None:
        _BG_TASKS.discard(t)
        if t.exception() is not None:
            logger.error("campanha_dispatch_task_crashed", error=str(t.exception()))

    task.add_done_callback(_on_done)
    return task
