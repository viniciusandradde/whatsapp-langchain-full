"""Vigência do plano e rebaixamento automático (ADR-005 leva E, mig 193).

`empresa.plano_valido_ate` é o último dia (inclusive) em que o plano pago
vale; NULL = sem vencimento (cortesia/legado — é o estado de todas as
empresas até a leva F registrar pagamentos). O worker roda `processar_vigencias`
periodicamente e, para cada empresa com data:

- D-7, D-3 e D0: avisa UMA vez por etapa — WhatsApp do telefone do resumo
  diário (se houver), aviso ao superadmin pelo canal dos alertas de IA
  (WhatsApp da empresa 1 + Telegram) e banner no painel (`resumo_para_painel`
  entrega `dias_para_vencer`, sem envio nenhum).
- Vencida há mais de `CARENCIA_DIAS`: rebaixa para Free num único
  `UPDATE … RETURNING` (atômico entre réplicas), registra no `audit_log` e
  avisa os dois lados.

O claim de cada etapa fica em `plano_aviso_vencimento_etapa` + `_ref` (a data
a que se refere): renovar muda a data e a etapa gravada deixa de valer
sozinha. Avisos só saem em horário comercial local (`JANELA_ENVIO`), para
não mandar WhatsApp de madrugada; fora dela o tick pula e tenta depois.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Final
from zoneinfo import ZoneInfo

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.rls_context import empresa_scope

logger = structlog.get_logger()

CARENCIA_DIAS: Final = 5
TZ_PADRAO: Final = "America/Campo_Grande"
# Hora local (inclusive/exclusive) em que avisos e rebaixamentos acontecem.
JANELA_ENVIO: Final = (8, 20)
_ORDEM_ETAPA: Final = {"d7": 1, "d3": 2, "d0": 3, "rebaixado": 4}


@dataclass(frozen=True)
class EmpresaVigencia:
    id: int
    nome: str
    plano_slug: str
    plano_nome: str
    valido_ate: date
    tz: str
    telefone: str | None
    etapa: str | None
    etapa_ref: date | None


# ---- Regras puras (testáveis sem banco) --------------------------------------


def hoje_local(tz: str, now_utc: datetime | None = None) -> date:
    now = now_utc or datetime.now(UTC)
    try:
        return now.astimezone(ZoneInfo(tz)).date()
    except Exception:  # noqa: BLE001 — tz inválida no cadastro não pode parar o job
        return now.astimezone(ZoneInfo(TZ_PADRAO)).date()


def dentro_da_janela(tz: str, now_utc: datetime | None = None) -> bool:
    now = now_utc or datetime.now(UTC)
    try:
        hora = now.astimezone(ZoneInfo(tz)).hour
    except Exception:  # noqa: BLE001
        hora = now.astimezone(ZoneInfo(TZ_PADRAO)).hour
    return JANELA_ENVIO[0] <= hora < JANELA_ENVIO[1]


def dias_para_vencer(valido_ate: date, hoje: date) -> int:
    """Positivo = ainda vale; 0 = vence hoje; negativo = já venceu."""
    return (valido_ate - hoje).days


def etapa_devida(dias: int) -> str | None:
    """Etapa de aviso que corresponde a `dias` (a mais avançada que couber)."""
    if dias <= 0:
        return "d0"
    if dias <= 3:
        return "d3"
    if dias <= 7:
        return "d7"
    return None


def deve_rebaixar(dias: int) -> bool:
    """Passou a carência: venceu há mais de `CARENCIA_DIAS` dias."""
    return dias < -CARENCIA_DIAS


def etapa_ja_enviada(
    etapa_gravada: str | None, ref: date | None, valido_ate: date, etapa: str
) -> bool:
    """A etapa (ou uma posterior) já saiu PARA ESTA data?"""
    if etapa_gravada is None or ref != valido_ate:
        return False
    return _ORDEM_ETAPA.get(etapa_gravada, 0) >= _ORDEM_ETAPA[etapa]


def carencia_ate(valido_ate: date) -> date:
    return valido_ate + timedelta(days=CARENCIA_DIAS)


def _fmt(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def texto_aviso_cliente(etapa: str, e: EmpresaVigencia) -> str:
    """Texto do WhatsApp para a empresa (E.1 — sem termo técnico)."""
    limite = _fmt(carencia_ate(e.valido_ate))
    if etapa == "d7":
        return (
            f"Olá! O plano *{e.plano_nome}* da *{e.nome}* no Chat Nexus vence em 7 dias "
            f"({_fmt(e.valido_ate)}). Para continuar com todos os recursos, renove até "
            f"lá — em *Plano e cobrança* no painel ou falando com a nossa equipe."
        )
    if etapa == "d3":
        return (
            f"Lembrete: o plano *{e.plano_nome}* da *{e.nome}* no Chat Nexus vence em 3 dias "
            f"({_fmt(e.valido_ate)}). Renove em *Plano e cobrança* no painel ou fale com a "
            f"nossa equipe para não perder os recursos do plano."
        )
    if etapa == "d0":
        return (
            f"O plano *{e.plano_nome}* da *{e.nome}* no Chat Nexus vence hoje "
            f"({_fmt(e.valido_ate)}). Você tem até {limite} para renovar — depois disso a "
            f"conta volta ao plano Free: os atendimentos continuam, mas os recursos do "
            f"{e.plano_nome} ficam pausados."
        )
    return (
        f"O plano *{e.plano_nome}* da *{e.nome}* no Chat Nexus venceu em "
        f"{_fmt(e.valido_ate)} e não foi renovado: a conta passou para o plano Free. Os "
        f"atendimentos continuam normalmente; para voltar ao {e.plano_nome}, renove em "
        f"*Plano e cobrança* no painel ou fale com a nossa equipe."
    )


def texto_aviso_plataforma(etapa: str, e: EmpresaVigencia) -> str:
    """Aviso ao superadmin (canal dos alertas de IA)."""
    if etapa == "rebaixado":
        return (
            f"⬇️ Plano rebaixado — {e.nome} (id {e.id}) passou de {e.plano_nome} para Free: "
            f"venceu em {_fmt(e.valido_ate)} e não houve pagamento em {CARENCIA_DIAS} dias."
        )
    quando = {"d7": "em 7 dias", "d3": "em 3 dias", "d0": "hoje"}[etapa]
    return (
        f"⚠️ Plano a vencer — {e.nome} (id {e.id}, {e.plano_nome}) vence {quando} "
        f"({_fmt(e.valido_ate)}). Registre o pagamento em Empresas → {e.nome} "
        f"para estender a vigência."
    )


# ---- Banco --------------------------------------------------------------------


async def listar_com_vigencia(pool: AsyncConnectionPool) -> list[EmpresaVigencia]:
    """Empresas pagas com data de vencimento (índice parcial da mig 193)."""
    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT e.id, e.nome, e.plano, COALESCE(p.nome, e.plano),
                       e.plano_valido_ate, COALESCE(e.resumo_diario_tz, %s),
                       e.resumo_diario_telefone,
                       e.plano_aviso_vencimento_etapa, e.plano_aviso_vencimento_ref
                  FROM empresa e
                  LEFT JOIN plano p ON p.id = e.plano_id
                 WHERE e.plano_valido_ate IS NOT NULL
                   AND e.plano <> 'free'
                   AND e.status = 'active'
                 ORDER BY e.plano_valido_ate, e.id
                """,
                (TZ_PADRAO,),
            )
            rows = await cur.fetchall()
    return [
        EmpresaVigencia(
            id=int(r[0]),
            nome=r[1],
            plano_slug=r[2],
            plano_nome=r[3],
            valido_ate=r[4],
            tz=r[5],
            telefone=r[6],
            etapa=r[7],
            etapa_ref=r[8],
        )
        for r in rows
    ]


async def _claim_etapa(
    pool: AsyncConnectionPool, e: EmpresaVigencia, etapa: str
) -> bool:
    """Grava a etapa atomicamente; só ganha quem achar a linha ainda sem ela
    (para ESTA data). `rowcount == 0` = outra réplica já avisou."""
    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                UPDATE empresa
                   SET plano_aviso_vencimento_etapa = %s,
                       plano_aviso_vencimento_ref = plano_valido_ate,
                       plano_aviso_vencimento_em = NOW()
                 WHERE id = %s
                   AND plano_valido_ate = %s
                   AND (plano_aviso_vencimento_etapa IS NULL
                        OR plano_aviso_vencimento_ref IS DISTINCT FROM plano_valido_ate
                        OR NOT (plano_aviso_vencimento_etapa = ANY(%s::text[])))
                """,
                (
                    etapa,
                    e.id,
                    e.valido_ate,
                    # etapas iguais ou posteriores à pedida já cobrem o aviso
                    [k for k, v in _ORDEM_ETAPA.items() if v >= _ORDEM_ETAPA[etapa]],
                ),
            )
            await conn.commit()
            return cur.rowcount > 0


async def _rebaixar(pool: AsyncConnectionPool, e: EmpresaVigencia) -> bool:
    """Free num único UPDATE condicional; a data fica registrada em
    `plano_aviso_vencimento_ref` (histórico do vencimento) e some de
    `plano_valido_ate` (Free não vence)."""
    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                UPDATE empresa
                   SET plano = 'free',
                       plano_valido_ate = NULL,
                       plano_aviso_vencimento_etapa = 'rebaixado',
                       plano_aviso_vencimento_ref = plano_valido_ate,
                       plano_aviso_vencimento_em = NOW(),
                       updated_at = NOW()
                 WHERE id = %s
                   AND plano <> 'free'
                   AND plano_valido_ate = %s
                RETURNING id
                """,
                (e.id, e.valido_ate),
            )
            row = await cur.fetchone()
            await conn.commit()
    if row is None:
        return False
    from whatsapp_langchain.shared.audit import record_audit
    from whatsapp_langchain.shared.plano_limits import clear_plano_cache

    clear_plano_cache(e.id)
    # O worker roda fora de request: o INSERT em `audit_log` (FORCE RLS)
    # precisa do escopo da empresa.
    with empresa_scope(e.id):
        await record_audit(
            pool,
            empresa_id=e.id,
            user_id=None,
            action="plano.rebaixado_por_vencimento",
            entity_type="empresa",
            entity_id=str(e.id),
            payload_diff={
                "plano": {"before": e.plano_slug, "after": "free"},
                "plano_valido_ate": {"before": e.valido_ate.isoformat(), "after": None},
                "carencia_dias": CARENCIA_DIAS,
            },
        )
    return True


async def _avisar_cliente_padrao(e: EmpresaVigencia, texto: str) -> None:
    if not e.telefone:
        logger.info("plano_vigencia_sem_telefone", empresa_id=e.id)
        return
    from whatsapp_langchain.shared.db import get_pool
    from whatsapp_langchain.shared.plano_gate import _enviar_whatsapp

    await _enviar_whatsapp(await get_pool(), e.id, e.telefone, texto)


async def _avisar_plataforma_padrao(_e: EmpresaVigencia, texto: str) -> None:
    from whatsapp_langchain.shared.ia_alertas import notificar_plataforma

    await notificar_plataforma("Chat Nexus — vigência de plano", [texto])


async def processar_vigencias(
    pool: AsyncConnectionPool,
    *,
    now_utc: datetime | None = None,
    avisar_cliente: Callable[[EmpresaVigencia, str], Awaitable[None]] | None = None,
    avisar_plataforma: Callable[[EmpresaVigencia, str], Awaitable[None]] | None = None,
) -> dict[str, int]:
    """Um tick: avisa as etapas devidas e rebaixa quem passou da carência.
    Idempotente (claim por etapa; rebaixamento condicional) — pode rodar em
    todas as réplicas, a qualquer intervalo. Devolve contagens para log."""
    avisar_cliente = avisar_cliente or _avisar_cliente_padrao
    avisar_plataforma = avisar_plataforma or _avisar_plataforma_padrao
    contagem = {"avisos": 0, "rebaixadas": 0, "fora_da_janela": 0, "erros": 0}

    for e in await listar_com_vigencia(pool):
        try:
            if not dentro_da_janela(e.tz, now_utc):
                contagem["fora_da_janela"] += 1
                continue
            dias = dias_para_vencer(e.valido_ate, hoje_local(e.tz, now_utc))
            if deve_rebaixar(dias):
                if await _rebaixar(pool, e):
                    contagem["rebaixadas"] += 1
                    logger.info(
                        "plano_rebaixado_por_vencimento", empresa_id=e.id, dias=dias
                    )
                    await _notificar_os_dois(
                        e, "rebaixado", avisar_cliente, avisar_plataforma
                    )
                continue
            etapa = etapa_devida(dias)
            if etapa is None or etapa_ja_enviada(
                e.etapa, e.etapa_ref, e.valido_ate, etapa
            ):
                continue
            if await _claim_etapa(pool, e, etapa):
                contagem["avisos"] += 1
                logger.info(
                    "plano_vencimento_aviso", empresa_id=e.id, etapa=etapa, dias=dias
                )
                await _notificar_os_dois(e, etapa, avisar_cliente, avisar_plataforma)
        except Exception as exc:  # noqa: BLE001 — uma empresa não derruba as outras
            contagem["erros"] += 1
            logger.warning("plano_vigencia_erro", empresa_id=e.id, error=str(exc)[:200])
    return contagem


async def _notificar_os_dois(
    e: EmpresaVigencia,
    etapa: str,
    avisar_cliente: Callable[[EmpresaVigencia, str], Awaitable[None]],
    avisar_plataforma: Callable[[EmpresaVigencia, str], Awaitable[None]],
) -> None:
    # Cada canal é best-effort: o claim já foi feito, e o banner do painel
    # não depende de nenhum dos dois.
    try:
        await avisar_cliente(e, texto_aviso_cliente(etapa, e))
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "plano_vigencia_aviso_cliente_falhou", empresa_id=e.id, error=str(exc)[:200]
        )
    try:
        await avisar_plataforma(e, texto_aviso_plataforma(etapa, e))
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "plano_vigencia_aviso_plataforma_falhou",
            empresa_id=e.id,
            error=str(exc)[:200],
        )
