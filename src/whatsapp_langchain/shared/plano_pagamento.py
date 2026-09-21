"""Cobrança por planos hospedados (ADR-005 leva F, mig 194).

Não há API de cobrança: o dono cria os planos nos painéis da InfinitePay
(Cobrança Recorrente — padrão) e do Mercado Pago (Assinaturas — alternativa),
cola os links em `plano.link_*` e o `/billing` mostra ao cliente. Quem paga
é conciliado pelo painel do gateway e a **ativação é manual**: o superadmin
registra o pagamento aqui, o que grava em `transacao`, muda o plano da
empresa se preciso e estende `empresa.plano_valido_ate` (leva E) — o claim
dos avisos de vencimento zera junto, porque a data mudou.

Idempotência: `(gateway, gateway_id)` informado nunca entra duas vezes
(`PagamentoDuplicadoError` → 409 na rota). Sem id (pagamento `manual`) não
há como deduplicar — o histórico mostra e o superadmin decide.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Final
from urllib.parse import urlparse

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.rls_context import empresa_scope

logger = structlog.get_logger()

GATEWAYS: Final = ("infinitepay", "mercadopago", "manual")

# Domínios aceitos por gateway ao colar o link do plano hospedado: protege o
# superadmin de um link errado e fecha `javascript:`/http.
_DOMINIOS_LINK: Final = {
    "infinitepay": ("infinitepay.io",),
    "mercadopago": (
        "mercadopago.com",
        "mercadopago.com.br",
        "mpago.la",
        "mercadolibre.com",
    ),
}


class PagamentoInvalidoError(ValueError):
    """Dados que a rota devolve como 400 (texto para o superadmin)."""


class PagamentoDuplicadoError(ValueError):
    """Mesmo `(gateway, gateway_id)` já registrado → 409."""


# ---- Regras puras ---------------------------------------------------------------


def somar_um_mes(d: date) -> date:
    """31/01 + 1 mês = 28/02 (dia travado no último do mês)."""
    ano, mes = (d.year + 1, 1) if d.month == 12 else (d.year, d.month + 1)
    return date(ano, mes, min(d.day, calendar.monthrange(ano, mes)[1]))


def proximo_periodo(valido_ate: date | None, hoje: date) -> tuple[date, date]:
    """Sugestão de período do próximo pagamento mensal: começa no dia
    seguinte ao fim da vigência atual (ou hoje, se já venceu/não tem) e dura
    um mês — `fim` é o novo `plano_valido_ate` (inclusive)."""
    inicio = (
        hoje
        if valido_ate is None or valido_ate < hoje
        else valido_ate + timedelta(days=1)
    )
    fim = somar_um_mes(inicio) - timedelta(days=1)
    return inicio, fim


def validar_link(gateway: str, link: str | None) -> str | None:
    """Link do plano hospedado: https e domínio do gateway. Vazio = limpa."""
    if link is None or not link.strip():
        return None
    url = link.strip()
    partes = urlparse(url)
    dominios = _DOMINIOS_LINK.get(gateway, ())
    host = (partes.hostname or "").lower()
    if partes.scheme != "https" or not any(
        host == d or host.endswith("." + d) for d in dominios
    ):
        raise PagamentoInvalidoError(
            f"O link precisa começar com https:// e ser do próprio gateway ({', '.join(dominios)})."
        )
    return url


def texto_confirmacao_pagamento(
    empresa_nome: str, plano_nome: str, periodo_fim: date
) -> str:
    return (
        f"Pagamento confirmado! O plano *{plano_nome}* da *{empresa_nome}* no Chat Nexus "
        f"está ativo até {periodo_fim.strftime('%d/%m/%Y')}. Obrigado!"
    )


# ---- Banco ------------------------------------------------------------------------


@dataclass(frozen=True)
class PagamentoRegistrado:
    transacao_id: int
    empresa_id: int
    empresa_nome: str
    plano_slug: str
    plano_nome: str
    valor_brl: float
    periodo_inicio: date
    periodo_fim: date
    plano_anterior: str
    valido_ate_anterior: date | None
    telefone: str | None


async def registrar_pagamento(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    plano_slug: str,
    gateway: str,
    gateway_id: str | None,
    valor_brl: float,
    periodo_inicio: date,
    periodo_fim: date,
    observacao: str | None,
    user_id: str | None,
) -> PagamentoRegistrado:
    """Grava a transação paga e ativa/estende a vigência da empresa.

    Uma transação só: `transacao` + `empresa` no mesmo commit — não pode
    existir pagamento gravado com plano velho nem plano novo sem pagamento.
    """
    if gateway not in GATEWAYS:
        raise PagamentoInvalidoError("Forma de pagamento desconhecida.")
    if valor_brl < 0:
        raise PagamentoInvalidoError("O valor não pode ser negativo.")
    if periodo_fim < periodo_inicio:
        raise PagamentoInvalidoError("O fim do período não pode vir antes do início.")
    gateway_id = (gateway_id or "").strip() or None

    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT id, nome FROM plano WHERE slug = %s AND ativo", (plano_slug,)
            )
            plano = await cur.fetchone()
            if plano is None:
                raise PagamentoInvalidoError("Plano não encontrado.")
            if plano_slug == "free":
                raise PagamentoInvalidoError("O plano Free não tem pagamento.")
            cur = await conn.execute(
                "SELECT nome, plano, plano_valido_ate, resumo_diario_telefone "
                "FROM empresa WHERE id = %s",
                (empresa_id,),
            )
            emp = await cur.fetchone()
            if emp is None:
                raise PagamentoInvalidoError("Empresa não encontrada.")
            if gateway_id:
                cur = await conn.execute(
                    "SELECT id FROM transacao WHERE gateway = %s AND gateway_id = %s",
                    (gateway, gateway_id),
                )
                if await cur.fetchone() is not None:
                    raise PagamentoDuplicadoError(
                        f"Esse pagamento ({gateway} {gateway_id}) já foi registrado."
                    )

            descricao = (
                f"Plano {plano[1]} — {periodo_inicio.strftime('%d/%m/%Y')} a "
                f"{periodo_fim.strftime('%d/%m/%Y')}"
            )
            if observacao and observacao.strip():
                descricao += f" · {observacao.strip()}"
            cur = await conn.execute(
                """
                INSERT INTO transacao (empresa_id, plano_id, tipo, valor_brl, status,
                                       gateway, gateway_id, descricao, pago_em,
                                       periodo_inicio, periodo_fim)
                VALUES (%s, %s, 'assinatura', %s, 'pago', %s, %s, %s, NOW(), %s, %s)
                RETURNING id
                """,
                (
                    empresa_id,
                    plano[0],
                    valor_brl,
                    gateway,
                    gateway_id,
                    descricao,
                    periodo_inicio,
                    periodo_fim,
                ),
            )
            row = await cur.fetchone()
            assert row is not None
            transacao_id = int(row[0])
            # A vigência nova zera o claim dos avisos (leva E) — a etapa
            # gravada se referia à data antiga.
            await conn.execute(
                """
                UPDATE empresa
                   SET plano = %s,
                       plano_valido_ate = %s,
                       plano_aviso_vencimento_etapa = NULL,
                       plano_aviso_vencimento_ref = NULL,
                       plano_aviso_vencimento_em = NULL,
                       updated_at = NOW()
                 WHERE id = %s
                """,
                (plano_slug, periodo_fim, empresa_id),
            )
            await conn.commit()

    from whatsapp_langchain.shared.audit import record_audit
    from whatsapp_langchain.shared.plano_limits import clear_plano_cache

    clear_plano_cache(empresa_id)
    with empresa_scope(empresa_id):
        await record_audit(
            pool,
            empresa_id=empresa_id,
            user_id=user_id,
            action="plano.pagamento_registrado",
            entity_type="transacao",
            entity_id=str(transacao_id),
            payload_diff={
                "plano": {"before": emp[1], "after": plano_slug},
                "plano_valido_ate": {
                    "before": emp[2].isoformat() if emp[2] else None,
                    "after": periodo_fim.isoformat(),
                },
                "gateway": gateway,
                "gateway_id": gateway_id,
                "valor_brl": valor_brl,
            },
        )
    logger.info(
        "plano_pagamento_registrado",
        empresa_id=empresa_id,
        transacao_id=transacao_id,
        plano=plano_slug,
        gateway=gateway,
        periodo_fim=periodo_fim.isoformat(),
    )
    return PagamentoRegistrado(
        transacao_id=transacao_id,
        empresa_id=empresa_id,
        empresa_nome=emp[0],
        plano_slug=plano_slug,
        plano_nome=plano[1],
        valor_brl=float(valor_brl),
        periodo_inicio=periodo_inicio,
        periodo_fim=periodo_fim,
        plano_anterior=emp[1],
        valido_ate_anterior=emp[2],
        telefone=emp[3],
    )


async def confirmar_por_whatsapp(
    pool: AsyncConnectionPool, p: PagamentoRegistrado
) -> bool:
    """Best-effort: mesmo caminho dos avisos de vencimento (telefone do
    resumo diário). Sem telefone = False, sem erro."""
    if not p.telefone:
        return False
    from whatsapp_langchain.shared.plano_gate import _enviar_whatsapp

    try:
        await _enviar_whatsapp(
            pool,
            p.empresa_id,
            p.telefone,
            texto_confirmacao_pagamento(p.empresa_nome, p.plano_nome, p.periodo_fim),
        )
        return True
    except Exception as exc:  # noqa: BLE001 — confirmação não desfaz o registro
        logger.warning(
            "plano_pagamento_whatsapp_falhou",
            empresa_id=p.empresa_id,
            error=str(exc)[:200],
        )
        return False


async def listar_pagamentos(
    pool: AsyncConnectionPool, empresa_id: int, limit: int = 50
) -> list[dict[str, Any]]:
    """Últimas transações da empresa (histórico do /billing e do bloco do
    superadmin em /companies). Substitui `asaas.list_transacoes`."""
    with empresa_scope(empresa_id=empresa_id):
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT t.id, t.tipo, t.valor_brl, t.status, t.gateway,
                       t.gateway_id, t.descricao, t.pago_em,
                       t.created_at, p.slug AS plano_slug, p.nome AS plano_nome,
                       t.periodo_inicio, t.periodo_fim
                  FROM transacao t
                  LEFT JOIN plano p ON p.id = t.plano_id
                 WHERE t.empresa_id = %s
                 ORDER BY t.created_at DESC
                 LIMIT %s
                """,
                (empresa_id, limit),
            )
            rows = await cur.fetchall()
    return [
        {
            "id": int(r[0]),
            "tipo": r[1],
            "valor_brl": float(r[2]) if r[2] is not None else 0.0,
            "status": r[3],
            "gateway": r[4],
            "gateway_id": r[5],
            "descricao": r[6],
            "pago_em": r[7].isoformat() if r[7] else None,
            "created_at": r[8].isoformat() if r[8] else None,
            "plano_slug": r[9],
            "plano_nome": r[10],
            "periodo_inicio": r[11].isoformat() if r[11] else None,
            "periodo_fim": r[12].isoformat() if r[12] else None,
        }
        for r in rows
    ]


def hoje_local() -> date:
    from whatsapp_langchain.shared.plano_vigencia import TZ_PADRAO
    from whatsapp_langchain.shared.plano_vigencia import hoje_local as _hoje

    return _hoje(TZ_PADRAO, datetime.now(UTC))
