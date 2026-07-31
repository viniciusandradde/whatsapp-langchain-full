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
from typing import Any

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.conexao import (
    get_conexao_by_id,
    list_conexoes,
)
from whatsapp_langchain.shared.conexao_quota import (
    incr_uso_hoje,
    quota_status,
)
from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.outbound import _build_client, send_template_by_id
from whatsapp_langchain.shared.rls_context import empresa_scope

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


# Piso de intervalo mínimo (ms) entre envios de MÍDIA — anti-ban. Mídia em
# ritmo de texto foi o que escalou o ban da campanha 9 (ver
# docs/DISPARO_MASSA_BEST_PRACTICES.md). 8s é conservador pra canal não-oficial.
_MEDIA_MIN_INTERVAL_MS = 8000


def _piso_midia(min_ms: int, max_ms: int, tem_midia: bool) -> tuple[int, int]:
    """Aplica o piso anti-ban de intervalo quando a campanha tem mídia.

    Texto fica como configurado; mídia força `min_ms >= _MEDIA_MIN_INTERVAL_MS`
    (e ajusta `max_ms` pra não ficar abaixo do novo mínimo)."""
    if tem_midia and min_ms < _MEDIA_MIN_INTERVAL_MS:
        min_ms = _MEDIA_MIN_INTERVAL_MS
        max_ms = max(max_ms, min_ms)
    return min_ms, max_ms


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
    # Origem do envio (mig 125): 'backend' (Evolution/WABA) | 'extensao' (in-browser)
    origem_envio: str = "backend"
    # Pausa longa periódica anti-ban (mig 127): 0 = desligado
    pausa_a_cada: int = 0
    pausa_segundos: int = 0
    # Pool de rotação de números (mig 130): dispatcher alterna entre eles.
    # None/vazio = usa conexao_id (single).
    conexao_ids: list[int] | None = None

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
            "origem_envio": self.origem_envio,
            "pausa_a_cada": self.pausa_a_cada,
            "pausa_segundos": self.pausa_segundos,
            "conexao_ids": list(self.conexao_ids or []),
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
    "media_url, media_tipo, "
    # Origem do envio (mig 125)
    "origem_envio, "
    # Pausa periódica anti-ban (mig 127)
    "pausa_a_cada, pausa_segundos, "
    # Pool de rotação de números (mig 130)
    "conexao_ids"
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
    # Agendamento (mig 124) — quando True + scheduled_at, nasce 'scheduled'
    agendar: bool = False,
    # Origem do envio (mig 125): 'extensao' → nasce 'running' (browser envia)
    origem_envio: str = "backend",
    # Pausa longa periódica anti-ban (mig 127) — 0 = desligado
    pausa_a_cada: int | None = None,
    pausa_segundos: int | None = None,
    # Pool de rotação de números (mig 130) — dispatcher alterna entre eles
    conexao_ids: list[int] | None = None,
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
    eff_pausa_cada = max(0, pausa_a_cada) if pausa_a_cada is not None else 0
    eff_pausa_seg = max(0, pausa_segundos) if pausa_segundos is not None else 0
    # Pool de rotação (mig 130): dedup preservando ordem. Se vier pool, o
    # conexao_id (legado/single) vira o 1º do pool — compat com reads.
    eff_pool: list[int] | None = None
    if conexao_ids:
        eff_pool = list(dict.fromkeys(int(c) for c in conexao_ids))
        if conexao_id is None:
            conexao_id = eff_pool[0]
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

    # Nasce 'scheduled' quando agendada (poller dispara no horário); senão draft.
    if origem_envio == "extensao":
        # Browser (WPPConnect) faz o envio + reporta acks; backend não dispara.
        status_inicial = "running"
    else:
        status_inicial = "scheduled" if (agendar and scheduled_at) else "draft"

    async with pool.connection() as conn:
        async with conn.transaction():
            cur = await conn.execute(
                f"""
                INSERT INTO campanha
                    (empresa_id, nome, descricao, mensagem, conexao_id,
                     intervalo_ms, max_destinatarios, total_destinatarios,
                     created_by_user_id, status,
                     modelo_mensagem_id, scheduled_at, tipo,
                     filtro_segmento, filtro_tags,
                     message_template_id, template_variaveis,
                     intervalo_min_ms, intervalo_max_ms, kill_switch_pct,
                     media_url, media_tipo, origem_envio,
                     pausa_a_cada, pausa_segundos, conexao_ids)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s::text[], %s, %s::jsonb, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s::bigint[])
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
                    status_inicial,
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
                    origem_envio,
                    eff_pausa_cada,
                    eff_pausa_seg,
                    eff_pool,
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


async def aplicar_report_ext(
    pool: AsyncConnectionPool, empresa_id: int, camp_id: int, items: list[dict]
) -> dict:
    """Aplica o reporte de envio in-browser (extensão) numa campanha
    `origem_envio='extensao'`. Cada item: {telefone, status('enviado'|'falhou'),
    erro?, wamid?}. Atualiza `campanha_destinatario` por (campanha_id, telefone),
    recalcula contadores e finaliza a campanha quando não há mais pendentes.

    Returns: {aplicados, enviados, falhas, total, status}.
    """
    aplicados = 0
    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            # guard: campanha existe, é da empresa e é da extensão
            cur = await conn.execute(
                "SELECT origem_envio FROM campanha WHERE id = %s AND empresa_id = %s",
                (camp_id, empresa_id),
            )
            row = await cur.fetchone()
            if row is None:
                raise ValueError("Campanha não encontrada")
            if row[0] != "extensao":
                raise ValueError("Report só vale pra campanha origem_envio='extensao'")

            for it in items:
                tel = normalize_phone(str(it.get("telefone") or ""))
                st = it.get("status")
                if tel is None or st not in ("enviado", "falhou"):
                    continue
                cur = await conn.execute(
                    """
                    UPDATE campanha_destinatario
                       SET status = %s, erro = %s, mensagem_id_externo = %s,
                           sent_at = NOW()
                     WHERE campanha_id = %s AND telefone = %s
                       AND status = 'pendente'
                    RETURNING id
                    """,
                    (
                        st,
                        (str(it.get("erro"))[:500] if it.get("erro") else None),
                        it.get("wamid"),
                        camp_id,
                        tel,
                    ),
                )
                if await cur.fetchone() is not None:
                    aplicados += 1

            # recalcula contadores + finaliza se acabou
            cur = await conn.execute(
                """
                UPDATE campanha SET
                    enviados = (SELECT count(*) FROM campanha_destinatario
                                 WHERE campanha_id = %s AND status = 'enviado'),
                    falhas   = (SELECT count(*) FROM campanha_destinatario
                                 WHERE campanha_id = %s AND status = 'falhou'),
                    updated_at = NOW(),
                    status = CASE
                       WHEN (SELECT count(*) FROM campanha_destinatario
                              WHERE campanha_id = %s AND status = 'pendente') = 0
                       THEN (CASE WHEN (SELECT count(*) FROM campanha_destinatario
                                         WHERE campanha_id = %s AND status = 'falhou') > 0
                                  THEN 'partial' ELSE 'done' END)
                       ELSE status END,
                    finished_at = CASE
                       WHEN (SELECT count(*) FROM campanha_destinatario
                              WHERE campanha_id = %s AND status = 'pendente') = 0
                       THEN NOW() ELSE finished_at END
                 WHERE id = %s
                RETURNING enviados, falhas, total_destinatarios, status
                """,
                (camp_id, camp_id, camp_id, camp_id, camp_id, camp_id),
            )
            r = await cur.fetchone()
            await conn.commit()
    return {
        "aplicados": aplicados,
        "enviados": r[0] if r else 0,
        "falhas": r[1] if r else 0,
        "total": r[2] if r else 0,
        "status": r[3] if r else None,
    }


# Campanha só pode ser editada / ter destinatários mexidos antes de rodar.
_EDITAVEL = ("draft", "scheduled")
_CAMPOS_EDITAVEIS = frozenset(
    {
        "nome",
        "descricao",
        "mensagem",
        "conexao_id",
        "intervalo_min_ms",
        "intervalo_max_ms",
        "kill_switch_pct",
        "scheduled_at",
        "status",
        "media_url",
        "media_tipo",
        "pausa_a_cada",
        "pausa_segundos",
    }
)


async def _status_editavel(conn, empresa_id: int, camp_id: int) -> str:
    """Retorna o status se a campanha existe e é editável; senão raise."""
    cur = await conn.execute(
        "SELECT status FROM campanha WHERE id = %s AND empresa_id = %s",
        (camp_id, empresa_id),
    )
    row = await cur.fetchone()
    if row is None:
        raise ValueError("Campanha não encontrada")
    if row[0] not in _EDITAVEL:
        raise ValueError(
            f"Campanha em '{row[0]}' não pode ser alterada (só rascunho/agendada)."
        )
    return row[0]


async def update_campanha(
    pool: AsyncConnectionPool, empresa_id: int, camp_id: int, campos: dict
) -> dict | None:
    """Atualiza campos de uma campanha em rascunho/agendada. `campos` é filtrado
    pela whitelist `_CAMPOS_EDITAVEIS`. Rejeita se a campanha já rodou."""
    campos = {k: v for k, v in campos.items() if k in _CAMPOS_EDITAVEIS}
    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            await _status_editavel(conn, empresa_id, camp_id)
            if campos:
                sets = ", ".join(f"{k} = %s" for k in campos) + ", updated_at = NOW()"
                params = [*campos.values(), camp_id, empresa_id]
                await conn.execute(
                    f"UPDATE campanha SET {sets} WHERE id = %s AND empresa_id = %s",  # type: ignore[arg-type]  # noqa: S608 — chaves vêm da whitelist
                    tuple(params),
                )
                await conn.commit()
    return await get_campanha(pool, empresa_id, camp_id)


async def add_destinatarios(
    pool: AsyncConnectionPool, empresa_id: int, camp_id: int, telefones: list[str]
) -> dict:
    """Adiciona telefones a uma campanha editável (normaliza + dedupe). Recalcula
    total_destinatarios. Retorna {novos, total}."""
    novos = 0
    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            await _status_editavel(conn, empresa_id, camp_id)
            seen: set[str] = set()
            for raw in telefones:
                n = normalize_phone(raw)
                if n is None or n in seen:
                    continue
                seen.add(n)
                cur = await conn.execute(
                    "INSERT INTO campanha_destinatario (campanha_id, telefone)"
                    " VALUES (%s, %s) ON CONFLICT (campanha_id, telefone) DO NOTHING"
                    " RETURNING id",
                    (camp_id, n),
                )
                if await cur.fetchone() is not None:
                    novos += 1
            cur = await conn.execute(
                "UPDATE campanha SET total_destinatarios ="
                " (SELECT count(*) FROM campanha_destinatario WHERE campanha_id = %s),"
                " updated_at = NOW() WHERE id = %s RETURNING total_destinatarios",
                (camp_id, camp_id),
            )
            row = await cur.fetchone()
            await conn.commit()
    return {"novos": novos, "total": row[0] if row else 0}


async def clonar_campanha(
    pool: AsyncConnectionPool, empresa_id: int, camp_id: int
) -> dict:
    """Clona uma campanha como NOVO rascunho ("{nome} (cópia)"), copiando
    mensagem/mídia/anti-ban/template/conexão + todos os destinatários (resetados
    pra 'pendente'). A original fica intacta — usado pra reenviar."""
    src = await get_campanha(pool, empresa_id, camp_id)
    if src is None:
        raise ValueError("Campanha não encontrada")
    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            async with conn.transaction():
                cur = await conn.execute(
                    f"""
                    INSERT INTO campanha
                        (empresa_id, nome, descricao, mensagem, conexao_id,
                         intervalo_ms, max_destinatarios, total_destinatarios,
                         created_by_user_id, status,
                         modelo_mensagem_id, tipo,
                         message_template_id, template_variaveis,
                         intervalo_min_ms, intervalo_max_ms, kill_switch_pct,
                         media_url, media_tipo, pausa_a_cada, pausa_segundos,
                         conexao_ids)
                    SELECT empresa_id, nome || ' (cópia)', descricao, mensagem,
                         conexao_id, intervalo_ms, max_destinatarios,
                         (SELECT count(*) FROM campanha_destinatario
                           WHERE campanha_id = %s),
                         created_by_user_id, 'draft',
                         modelo_mensagem_id, tipo,
                         message_template_id, template_variaveis,
                         intervalo_min_ms, intervalo_max_ms, kill_switch_pct,
                         media_url, media_tipo, pausa_a_cada, pausa_segundos,
                         conexao_ids
                    FROM campanha WHERE id = %s AND empresa_id = %s
                    RETURNING {_COLS}
                    """,
                    (camp_id, camp_id, empresa_id),
                )
                row = await cur.fetchone()
                assert row is not None
                novo = _row_to_camp(row)
                await conn.execute(
                    "INSERT INTO campanha_destinatario (campanha_id, telefone, variaveis)"
                    " SELECT %s, telefone, variaveis FROM campanha_destinatario"
                    " WHERE campanha_id = %s",
                    (novo.id, camp_id),
                )
                # NÃO chamar conn.commit() aqui — o `async with conn.transaction()`
                # commita ao sair (psycopg proíbe commit explícito dentro dele).
    logger.info("campanha_clonada", origem=camp_id, nova=novo.id)
    return novo.to_dict()


async def remove_destinatario(
    pool: AsyncConnectionPool, empresa_id: int, camp_id: int, dest_id: int
) -> dict:
    """Remove um destinatário de uma campanha editável. Recalcula total."""
    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            await _status_editavel(conn, empresa_id, camp_id)
            cur = await conn.execute(
                "DELETE FROM campanha_destinatario WHERE id = %s AND campanha_id = %s"
                " RETURNING id",
                (dest_id, camp_id),
            )
            removido = await cur.fetchone() is not None
            cur = await conn.execute(
                "UPDATE campanha SET total_destinatarios ="
                " (SELECT count(*) FROM campanha_destinatario WHERE campanha_id = %s),"
                " updated_at = NOW() WHERE id = %s RETURNING total_destinatarios",
                (camp_id, camp_id),
            )
            row = await cur.fetchone()
            await conn.commit()
    return {"removido": removido, "total": row[0] if row else 0}


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


async def _send_com_retry(fn, *, log, phone, tentativas: int = 3):
    """Retry anti-ban de um envio. "Connection Closed" / 5xx / timeout da
    Evolution são TRANSITÓRIOS (a sessão Baileys oscila) — re-tenta com backoff
    curto antes de desistir, em vez de queimar o destinatário como falha."""
    ultimo: Exception | None = None
    for i in range(tentativas):
        try:
            return await fn()
        except Exception as e:  # noqa: BLE001 — re-tenta e re-levanta no fim
            ultimo = e
            if i < tentativas - 1:
                log.warning(
                    "campanha_send_retry",
                    phone=phone,
                    tentativa=i + 1,
                    error=str(e)[:200],
                )
                await asyncio.sleep(1.5 * (i + 1))
    raise ultimo if ultimo else RuntimeError("falha no envio")


def _proxima_conexao(
    pool_ids: list[int], restante: dict[int, int | None], rr: int
) -> tuple[int, int] | None:
    """Round-robin: a partir do índice `rr`, escolhe a próxima conexão do pool
    com capacidade (restante None=ilimitado, ou > 0). Retorna
    `(conexao_id, novo_rr)` ou None se TODAS estão sem capacidade (teto batido)."""
    n = len(pool_ids)
    for k in range(n):
        idx = (rr + k) % n
        cid = pool_ids[idx]
        r = restante.get(cid)
        if r is None or r > 0:
            return cid, (idx + 1) % n
    return None


async def _dispatch_loop(
    pool: AsyncConnectionPool,
    empresa_id: int,
    camp_id: int,
    *,
    ja_running: bool = False,
) -> None:
    """Loop de envio executado em asyncio.create_task.

    Lê telefones pendentes em batches de 50, envia 1 a 1 com cooldown.
    Re-checa status da campanha a cada item — se virou 'aborted',
    para imediatamente (deixa pendentes como 'pendente').

    `ja_running=True`: a campanha já foi transicionada pra 'running' pelo poller
    de agendamento (claim atômico) — pula a guarda de 'draft' e a transição.
    """
    log = logger.bind(camp_id=camp_id, empresa_id=empresa_id)
    log.info("campanha_dispatch_started")

    camp = await get_campanha(pool, empresa_id, camp_id)
    estado_ok = "running" if ja_running else "draft"
    if camp is None or camp["status"] != estado_ok:
        log.warning("campanha_dispatch_invalid_state", status=camp and camp["status"])
        return

    # Resolve o POOL de conexões (mig 130): o dispatcher rotaciona entre elas.
    # `conexao_ids` não-vazio = pool; senão `conexao_id` (single); senão a 1ª ativa.
    raw_pool = camp.get("conexao_ids") or (
        [camp["conexao_id"]] if camp.get("conexao_id") else []
    )
    if not raw_pool:
        ativas = await list_conexoes(pool, empresa_id)  # já retorna só ativas
        if not ativas:
            await _mark_finished(pool, camp_id, "aborted", reason="sem conexão ativa")
            log.error("campanha_no_active_conexao")
            return
        raw_pool = [ativas[0].id]
    conexoes_pool = []
    for cid in raw_pool:
        cx = await get_conexao_by_id(pool, cid)
        if cx is not None and cx.empresa_id == empresa_id and cx.status == "active":
            conexoes_pool.append(cx)
    if not conexoes_pool:
        await _mark_finished(pool, camp_id, "aborted", reason="conexão inválida")
        log.error("campanha_invalid_conexao", pool=raw_pool)
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

    # Um client por conexão do pool + gate de saúde POR conexão (anti-ban):
    # conexão com sessão ≠ open sai do rodízio (não martela sessão caindo).
    # Canal oficial (WABA) não tem health() → fica.
    clients: dict[int, Any] = {}
    saudaveis = []
    for cx in conexoes_pool:
        cli, _mode = await _build_client(pool, cx)
        _health = getattr(cli, "health", None)
        if _health is not None:
            try:
                h = await _health()
                estado = (h or {}).get("state") or (h or {}).get("instance", {}).get(
                    "state"
                )
                if estado and estado != "open":
                    log.warning(
                        "campanha_conexao_fora_do_pool",
                        conexao_id=cx.id,
                        estado=estado,
                    )
                    continue
            except Exception as e:  # noqa: BLE001 — health indisponível não bloqueia
                log.warning(
                    "campanha_health_check_falhou", conexao_id=cx.id, error=str(e)
                )
        clients[cx.id] = cli
        saudaveis.append(cx)
    if not saudaveis:
        await _mark_finished(
            pool, camp_id, "aborted", reason="nenhuma conexão com sessão conectada"
        )
        log.error("campanha_pool_sem_sessao_aberta")
        return
    pool_ids = [cx.id for cx in saudaveis]

    # Faixa de jitter anti-ban (fallback pro intervalo_ms fixo legado).
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT intervalo_min_ms, intervalo_max_ms, kill_switch_pct, "
            "pausa_a_cada, pausa_segundos "
            "FROM campanha WHERE id = %s",
            (camp_id,),
        )
        jrow = await cur.fetchone()
    fixo = camp["intervalo_ms"]
    min_ms = (jrow[0] if jrow else None) or fixo
    max_ms = (jrow[1] if jrow else None) or fixo
    kill_pct = jrow[2] if jrow else None
    pausa_cada = (jrow[3] if jrow else 0) or 0
    pausa_seg = (jrow[4] if jrow else 0) or 0

    # Piso de intervalo pra MÍDIA (anti-ban): blast de mídia em ritmo de texto
    # (3-8s) foi o que escalou o ban da campanha 9. Mídia força um intervalo
    # mínimo maior — texto fica como configurado.
    _min_orig = min_ms
    min_ms, max_ms = _piso_midia(min_ms, max_ms, bool(media_url))
    if min_ms != _min_orig:
        log.info("campanha_piso_midia_aplicado", de=_min_orig, para=min_ms)

    # Teto diário / aquecimento (anti-ban) POR conexão do pool: cada número tem
    # seu teto/aquecimento; quem zera sai do rodízio. Todas zeradas → reagenda
    # pro dia seguinte (warm-up). restante None = ilimitado.
    restante: dict[int, int | None] = {}
    quota_motivo: dict[int, str | None] = {}
    for cx in saudaveis:
        q = await quota_status(pool, cx)
        restante[cx.id] = q.restante
        quota_motivo[cx.id] = q.motivo
        if q.cap is not None:
            log.info(
                "campanha_teto_diario",
                conexao_id=cx.id,
                cap=q.cap,
                usados=q.usados,
                motivo=q.motivo,
            )

    # Marca como running (quando agendada, o poller já fez o claim → pula).
    if not ja_running:
        async with pool.connection() as conn:
            await conn.execute(
                "UPDATE campanha SET status='running', started_at=NOW(), updated_at=NOW() "
                "WHERE id = %s AND status='draft'",
                (camp_id,),
            )
            await conn.commit()

    # Conta envios já feitos (enviados+falhas) pra alinhar a pausa periódica
    # mesmo quando a campanha é retomada (agendada/reagendada) no meio.
    processados = camp["enviados"] + camp["falhas"]
    rr = 0  # índice do round-robin do pool de conexões

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
            # Round-robin anti-ban: próxima conexão do pool com capacidade.
            escolha = _proxima_conexao(pool_ids, restante, rr)
            if escolha is None:
                # TODAS as conexões bateram o teto diário → reagenda o restante
                # pro dia seguinte (warm-up). Deixa os pendentes como 'pendente'.
                motivo = next((m for m in quota_motivo.values() if m), "teto diário")
                await _reagendar_warmup(pool, camp_id, 0, motivo)
                log.info("campanha_teto_diario_atingido", pool=pool_ids, motivo=motivo)
                return
            cid, rr = escolha
            cur_conexao = next(cx for cx in saudaveis if cx.id == cid)
            cur_client = clients[cid]
            try:
                # Factory do envio amarrada à conexão escolhida (mesma no retry).
                async def _do_send(
                    phone=phone,
                    cn=cliente_nome,
                    v=variaveis,
                    _cx=cur_conexao,
                    _cli=cur_client,
                ):
                    if template_id:
                        res = await send_template_by_id(
                            pool,
                            conexao_id=_cx.id,
                            empresa_id=empresa_id,
                            to=phone,
                            template_id=template_id,
                            variables=_resolve_template_vars(
                                camp.get("template_variaveis"), cn, v
                            ),
                        )
                        return res["provider_message_id"]
                    if media_url:
                        send_media = getattr(_cli, "send_media", None)
                        if send_media is None:
                            raise RuntimeError(
                                "Conexão não suporta envio de mídia (use Evolution)."
                            )
                        legenda = _apply_tokens(camp.get("mensagem") or "", cn, v)
                        return await send_media(
                            phone,
                            media_url,
                            mediatype=media_tipo,
                            caption=legenda or None,
                        )
                    return await _cli.send_message(
                        phone, _apply_tokens(camp.get("mensagem") or "", cn, v)
                    )

                # Retry anti-ban: "Connection Closed" e afins são transitórios —
                # re-tenta com backoff curto antes de marcar falha definitiva.
                provider_msg_id = await _send_com_retry(_do_send, log=log, phone=phone)
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
                    # Conta no teto diário DA conexão usada (mesma transação).
                    await incr_uso_hoje(conn, empresa_id, cid)
                    await conn.commit()
                if restante[cid] is not None:
                    restante[cid] -= 1  # type: ignore[operator]
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

            processados += 1
            delay_s = _jitter_delay_s(min_ms, max_ms)

            # Pausa longa periódica (descanso anti-ban): a cada `pausa_cada`
            # envios, dorme `pausa_seg` segundos além do jitter normal.
            if pausa_cada > 0 and processados % pausa_cada == 0:
                log.info(
                    "campanha_pausa_periodica",
                    processados=processados,
                    segundos=pausa_seg,
                )
                delay_s += pausa_seg

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


async def _reagendar_warmup(
    pool: AsyncConnectionPool, camp_id: int, cap: int, motivo: str | None
) -> None:
    """Teto diário atingido: reagenda os pendentes pro início do dia seguinte.

    Não aborta — vira 'scheduled' com `scheduled_at` = meia-noite de amanhã; o
    `run_scheduled_poller` reivindica e o `_dispatch_loop` (ja_running) continua
    de onde parou. O disparo "pinga" ao longo dos dias = aquecimento na prática.
    `cap` é mantido por compat (com pool de números não há teto único).
    """
    _cap_txt = f" {cap}" if cap else ""
    nota = f"\n[teto diário{_cap_txt} atingido ({motivo or 'manual'}) — retoma amanhã]"
    async with pool.connection() as conn:
        await conn.execute(
            """
            UPDATE campanha
               SET status = 'scheduled',
                   scheduled_at = date_trunc('day', NOW()) + INTERVAL '1 day',
                   updated_at = NOW(),
                   descricao = COALESCE(descricao, '') || %s
             WHERE id = %s
            """,
            (nota, camp_id),
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


async def claim_scheduled_due(pool: AsyncConnectionPool) -> list[tuple[int, int]]:
    """Claim atômico de campanhas agendadas vencidas (scheduled_at <= now()).

    Usa `FOR UPDATE SKIP LOCKED` + transição `scheduled→running` na mesma
    transação, então 2 instâncias da API nunca disparam a mesma campanha.
    Retorna lista de `(empresa_id, camp_id)` reivindicadas (já em 'running').
    """
    claimed: list[tuple[int, int]] = []
    # bypass de RLS: poller é cross-tenant (varre todas as empresas).
    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn, conn.transaction():
            cur = await conn.execute(
                """
                UPDATE campanha SET status='running', started_at=NOW(), updated_at=NOW()
                 WHERE id IN (
                    SELECT id FROM campanha
                     WHERE status='scheduled' AND scheduled_at IS NOT NULL
                       AND scheduled_at <= NOW()
                     ORDER BY scheduled_at
                     FOR UPDATE SKIP LOCKED
                     LIMIT 20
                 )
                RETURNING empresa_id, id
                """
            )
            claimed = [(r[0], r[1]) for r in await cur.fetchall()]
    return claimed


async def run_scheduled_poller(
    pool: AsyncConnectionPool, interval_s: float = 30.0
) -> None:
    """Loop infinito: a cada `interval_s`, claim das agendadas vencidas e
    dispara cada uma (já 'running' pelo claim). Rodar como task no lifespan."""
    while True:
        try:
            due = await claim_scheduled_due(pool)
            for empresa_id, camp_id in due:
                logger.info("campanha_scheduled_fired", camp_id=camp_id)
                # empresa_scope capturado pelo create_task (contextvars) → o
                # _dispatch_loop roda com o tenant certo apesar do poller ser global.
                with empresa_scope(empresa_id):
                    task = asyncio.create_task(
                        _dispatch_loop(pool, empresa_id, camp_id, ja_running=True)
                    )
                _BG_TASKS.add(task)
                task.add_done_callback(_BG_TASKS.discard)
        except Exception as e:  # noqa: BLE001 — poller nunca pode morrer
            logger.error("campanha_scheduled_poller_error", error=str(e))
        await asyncio.sleep(interval_s)
