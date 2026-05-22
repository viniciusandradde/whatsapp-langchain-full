"""Sprint B.3 — helpers de domínio billing.

Orquestra `integrations.asaas.client` + persistência local (`empresa`,
`transacao`, `billing_event_log`). Idempotente onde possível
(create_or_get_customer evita duplicação).

Bypass RLS quando necessário (billing é cross-tenant em poucos lugares:
webhook lookup, transação criada via webhook).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Any

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.integrations.asaas import AsaasClient, AsaasError
from whatsapp_langchain.shared.plano_limits import clear_plano_cache
from whatsapp_langchain.shared.rls_context import empresa_scope

logger = structlog.get_logger()

# ---------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------


async def create_or_get_asaas_customer(
    pool: AsyncConnectionPool,
    empresa_id: int,
) -> str:
    """Idempotente: cria customer Asaas pra empresa se não existe, retorna ID.

    Reusa `empresa.asaas_customer_id` se setado. Caso contrário:
    1. Lê dados empresa (razao_social ou nome, doc, etc)
    2. Procura customer no Asaas por external_reference=str(empresa_id)
       (defesa contra criação dupla se DB foi resetado)
    3. Cria customer se não achou
    4. Salva asaas_customer_id em empresa
    """
    with empresa_scope(empresa_id=empresa_id):
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT asaas_customer_id, nome, razao_social, doc "
                "FROM empresa WHERE id = %s",
                (empresa_id,),
            )
            row = await cur.fetchone()
    if row is None:
        raise ValueError(f"Empresa {empresa_id} não existe")
    asaas_id, nome, razao_social, doc = row
    if asaas_id:
        return asaas_id

    if not doc:
        raise AsaasError(
            "Empresa precisa ter CPF/CNPJ cadastrado pra cobrança.",
            status_code=400,
        )

    client = AsaasClient()
    # Idempotência: procura por external_reference primeiro
    existing = await client.list_customers_by_external_ref(str(empresa_id))
    if existing:
        asaas_id = existing[0]["id"]
        logger.info(
            "asaas_customer_found_existing",
            empresa_id=empresa_id, asaas_customer_id=asaas_id,
        )
    else:
        created = await client.create_customer(
            name=razao_social or nome,
            cpf_cnpj=_only_digits(doc),
            external_reference=str(empresa_id),
        )
        asaas_id = created["id"]
        logger.info(
            "asaas_customer_created",
            empresa_id=empresa_id, asaas_customer_id=asaas_id,
        )

    # Persiste (bypass — empresa não tem RLS própria mas mantém pattern)
    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            await conn.execute(
                "UPDATE empresa SET asaas_customer_id = %s, updated_at = NOW() "
                "WHERE id = %s",
                (asaas_id, empresa_id),
            )
            await conn.commit()
    return asaas_id


# ---------------------------------------------------------------------
# Subscriptions
# ---------------------------------------------------------------------


async def create_subscription_for_plano(
    pool: AsyncConnectionPool,
    empresa_id: int,
    plano_slug: str,
) -> dict[str, Any]:
    """Cria subscription Asaas + registra transacao inicial pendente.

    Retorna dict com {subscription_id, payment_url, valor, next_due_date}.
    UI usa payment_url pra redirecionar user pro checkout Asaas.

    Não atualiza empresa.plano ainda — espera webhook PAYMENT_CONFIRMED.
    """
    customer_id = await create_or_get_asaas_customer(pool, empresa_id)

    # Lookup do plano (valor mensal)
    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT id, preco_mensal_brl, nome FROM plano "
                "WHERE slug = %s AND ativo = TRUE",
                (plano_slug,),
            )
            row = await cur.fetchone()
    if row is None or row[1] is None or float(row[1]) <= 0:
        raise AsaasError(
            f"Plano '{plano_slug}' não está disponível pra cobrança "
            "(precisa ter preco_mensal_brl > 0).",
            status_code=400,
        )
    plano_id, valor, plano_nome = int(row[0]), float(row[1]), row[2]

    # Cancela subscription anterior se houver (downgrade/troca de plano)
    existing_sub = await _get_existing_subscription(pool, empresa_id)
    if existing_sub:
        try:
            await AsaasClient().cancel_subscription(existing_sub)
            logger.info(
                "asaas_old_subscription_cancelled",
                empresa_id=empresa_id, subscription_id=existing_sub,
            )
        except AsaasError as exc:
            logger.warning(
                "asaas_old_subscription_cancel_failed",
                empresa_id=empresa_id, error=str(exc),
            )

    # Cria nova subscription (próximo dia útil como vencimento)
    next_due = (date.today() + timedelta(days=1)).isoformat()
    client = AsaasClient()
    sub = await client.create_subscription(
        customer=customer_id,
        value=valor,
        next_due_date=next_due,
        cycle="MONTHLY",
        billing_type="UNDEFINED",  # user escolhe cartão/PIX/boleto no checkout
        description=f"Chat Nexus — Plano {plano_nome}",
        external_reference=str(empresa_id),
    )
    subscription_id = sub["id"]

    # Pega URL do primeiro pagamento gerado
    payments = await client.list_subscription_payments(subscription_id)
    payment_url = None
    asaas_payment_id = None
    if payments:
        first = payments[0]
        payment_url = first.get("invoiceUrl")
        asaas_payment_id = first.get("id")

    # Registra subscription + transacao inicial (pendente)
    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            await conn.execute(
                "UPDATE empresa SET asaas_subscription_id = %s, updated_at = NOW() "
                "WHERE id = %s",
                (subscription_id, empresa_id),
            )
            await conn.execute(
                """
                INSERT INTO transacao
                    (empresa_id, plano_id, tipo, valor_brl, status,
                     gateway, gateway_id, descricao)
                VALUES (%s, %s, 'assinatura', %s, 'pendente',
                        'asaas', %s, %s)
                """,
                (
                    empresa_id, plano_id, valor,
                    asaas_payment_id,
                    f"Assinatura {plano_nome} — vencimento {next_due}",
                ),
            )
            await conn.commit()

    logger.info(
        "asaas_subscription_created",
        empresa_id=empresa_id,
        subscription_id=subscription_id,
        plano=plano_slug, valor=valor,
    )
    return {
        "subscription_id": subscription_id,
        "payment_url": payment_url,
        "valor": valor,
        "next_due_date": next_due,
        "plano": plano_slug,
    }


async def cancel_active_subscription(
    pool: AsyncConnectionPool, empresa_id: int
) -> dict[str, str]:
    """Cancela subscription ativa + downgrade local pro plano free.

    User mantém acesso até o fim do ciclo atual (Asaas não estorna);
    plano local vira 'free' imediatamente — quotas restritas a partir
    da próxima request.
    """
    sub_id = await _get_existing_subscription(pool, empresa_id)
    if not sub_id:
        return {
            "status": "no_subscription",
            "message": "Empresa não tem subscription ativa.",
        }

    try:
        await AsaasClient().cancel_subscription(sub_id)
    except AsaasError as exc:
        logger.warning(
            "asaas_subscription_cancel_failed",
            empresa_id=empresa_id, error=str(exc),
        )
        # Continua o downgrade local mesmo se Asaas falhou — manual sync depois

    # Downgrade local
    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            await conn.execute(
                "UPDATE empresa "
                "SET asaas_subscription_id = NULL, plano = 'free', updated_at = NOW() "
                "WHERE id = %s",
                (empresa_id,),
            )
            await conn.commit()

    clear_plano_cache(empresa_id)
    logger.info(
        "asaas_subscription_cancelled",
        empresa_id=empresa_id, subscription_id=sub_id,
    )
    return {"status": "cancelled", "subscription_id": sub_id}


async def _get_existing_subscription(
    pool: AsyncConnectionPool, empresa_id: int
) -> str | None:
    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT asaas_subscription_id FROM empresa WHERE id = %s",
                (empresa_id,),
            )
            row = await cur.fetchone()
    return row[0] if row and row[0] else None


# ---------------------------------------------------------------------
# Webhook processing
# ---------------------------------------------------------------------


async def process_asaas_webhook(
    pool: AsyncConnectionPool,
    event: dict[str, Any],
) -> dict[str, Any]:
    """Processa evento webhook Asaas.

    Eventos relevantes:
    - PAYMENT_CONFIRMED — paga; atualiza transacao + ativa plano novo
    - PAYMENT_RECEIVED — confirmação adicional (boleto compensado)
    - PAYMENT_OVERDUE — vencido sem pagar; opcional: marca transacao
    - PAYMENT_REFUNDED — estornado; reverte plano
    - SUBSCRIPTION_DELETED — cancelada (provavelmente via UI Asaas)

    Idempotente: pode receber mesmo event_id 2x sem efeito duplicado.

    Sempre registra em billing_event_log (audit). Retorna dict
    com {processado, transacao_id?, action_taken}.
    """
    event_type = event.get("event") or ""
    payment = event.get("payment") or {}
    subscription_id = payment.get("subscription")
    customer_id = payment.get("customer")
    payment_id = payment.get("id")

    # Resolve empresa via customer_id ou subscription_id
    empresa_id = await _resolve_empresa_from_event(
        pool, customer_id, subscription_id
    )

    # SEMPRE registra log (audit append-only)
    log_id = await _log_billing_event(
        pool,
        event_type=event_type,
        asaas_payment_id=payment_id,
        asaas_customer_id=customer_id,
        asaas_subscription_id=subscription_id,
        empresa_id=empresa_id,
        payload=event,
    )

    if empresa_id is None:
        logger.warning(
            "asaas_webhook_unknown_customer",
            customer_id=customer_id, subscription_id=subscription_id,
            event_type=event_type,
        )
        return {"processado": False, "reason": "unknown_customer"}

    # Dispatch por tipo de evento
    action_taken = "ignored"
    transacao_id: int | None = None

    if event_type in ("PAYMENT_CONFIRMED", "PAYMENT_RECEIVED"):
        transacao_id = await _mark_transacao_paga(
            pool, empresa_id, payment_id
        )
        # Atualiza plano da empresa baseado no plano da subscription Asaas
        await _ativar_plano_pos_pagamento(pool, empresa_id, subscription_id)
        action_taken = "plano_ativado"

    elif event_type == "PAYMENT_OVERDUE":
        transacao_id = await _mark_transacao_vencida(
            pool, empresa_id, payment_id
        )
        action_taken = "marcado_pendente"

    elif event_type == "PAYMENT_REFUNDED":
        transacao_id = await _mark_transacao_estornada(
            pool, empresa_id, payment_id
        )
        # Reverte plano pra free
        with empresa_scope(None, bypass=True):
            async with pool.connection() as conn:
                await conn.execute(
                    "UPDATE empresa SET plano = 'free', updated_at = NOW() "
                    "WHERE id = %s",
                    (empresa_id,),
                )
                await conn.commit()
        clear_plano_cache(empresa_id)
        action_taken = "plano_revertido_free"

    elif event_type == "SUBSCRIPTION_DELETED":
        with empresa_scope(None, bypass=True):
            async with pool.connection() as conn:
                await conn.execute(
                    "UPDATE empresa "
                    "SET asaas_subscription_id = NULL, plano = 'free', "
                    "    updated_at = NOW() "
                    "WHERE id = %s",
                    (empresa_id,),
                )
                await conn.commit()
        clear_plano_cache(empresa_id)
        action_taken = "subscription_cancelled"

    # Marca log como processado
    await _mark_log_processado(pool, log_id, transacao_id)

    logger.info(
        "asaas_webhook_processed",
        event_type=event_type, empresa_id=empresa_id,
        action_taken=action_taken, transacao_id=transacao_id,
    )
    return {
        "processado": True,
        "empresa_id": empresa_id,
        "transacao_id": transacao_id,
        "action_taken": action_taken,
    }


async def _resolve_empresa_from_event(
    pool: AsyncConnectionPool,
    customer_id: str | None,
    subscription_id: str | None,
) -> int | None:
    if not customer_id and not subscription_id:
        return None
    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            if customer_id:
                cur = await conn.execute(
                    "SELECT id FROM empresa WHERE asaas_customer_id = %s",
                    (customer_id,),
                )
                row = await cur.fetchone()
                if row:
                    return int(row[0])
            if subscription_id:
                cur = await conn.execute(
                    "SELECT id FROM empresa WHERE asaas_subscription_id = %s",
                    (subscription_id,),
                )
                row = await cur.fetchone()
                if row:
                    return int(row[0])
    return None


async def _log_billing_event(
    pool: AsyncConnectionPool,
    *,
    event_type: str,
    asaas_payment_id: str | None,
    asaas_customer_id: str | None,
    asaas_subscription_id: str | None,
    empresa_id: int | None,
    payload: dict,
) -> int:
    import json as _json

    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                INSERT INTO billing_event_log
                    (event_type, asaas_payment_id, asaas_customer_id,
                     asaas_subscription_id, empresa_id, payload)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                RETURNING id
                """,
                (event_type, asaas_payment_id, asaas_customer_id,
                 asaas_subscription_id, empresa_id, _json.dumps(payload)),
            )
            row = await cur.fetchone()
            await conn.commit()
    return int(row[0])


async def _mark_log_processado(
    pool: AsyncConnectionPool, log_id: int, transacao_id: int | None
) -> None:
    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            await conn.execute(
                "UPDATE billing_event_log "
                "SET processado = TRUE, transacao_id = %s "
                "WHERE id = %s",
                (transacao_id, log_id),
            )
            await conn.commit()


async def _mark_transacao_paga(
    pool: AsyncConnectionPool, empresa_id: int, payment_id: str | None
) -> int | None:
    if not payment_id:
        return None
    with empresa_scope(empresa_id=empresa_id):
        async with pool.connection() as conn:
            cur = await conn.execute(
                "UPDATE transacao SET status = 'pago', pago_em = NOW(), "
                "    updated_at = NOW() "
                "WHERE empresa_id = %s AND gateway = 'asaas' "
                "  AND gateway_id = %s "
                "  AND status = 'pendente' "
                "RETURNING id",
                (empresa_id, payment_id),
            )
            row = await cur.fetchone()
            await conn.commit()
    return int(row[0]) if row else None


async def _mark_transacao_vencida(
    pool: AsyncConnectionPool, empresa_id: int, payment_id: str | None
) -> int | None:
    # Asaas considera "overdue" como pendente ainda — não muda status,
    # só registra no log. Função existe pra dispatch ficar simétrico.
    return None


async def _mark_transacao_estornada(
    pool: AsyncConnectionPool, empresa_id: int, payment_id: str | None
) -> int | None:
    if not payment_id:
        return None
    with empresa_scope(empresa_id=empresa_id):
        async with pool.connection() as conn:
            cur = await conn.execute(
                "UPDATE transacao SET status = 'estornado', updated_at = NOW() "
                "WHERE empresa_id = %s AND gateway = 'asaas' "
                "  AND gateway_id = %s "
                "RETURNING id",
                (empresa_id, payment_id),
            )
            row = await cur.fetchone()
            await conn.commit()
    return int(row[0]) if row else None


async def _ativar_plano_pos_pagamento(
    pool: AsyncConnectionPool,
    empresa_id: int,
    subscription_id: str | None,
) -> None:
    """Após pagamento confirmado, sync plano local com plano da subscription.

    Usa o plano_id da transacao mais recente da subscription pra atualizar
    empresa.plano. Trigger do mig 104 sincroniza plano_id automaticamente.
    """
    if not subscription_id:
        return
    with empresa_scope(empresa_id=empresa_id):
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT p.slug FROM transacao t
                  JOIN plano p ON p.id = t.plano_id
                 WHERE t.empresa_id = %s
                   AND t.gateway = 'asaas'
                   AND t.status = 'pago'
                 ORDER BY t.created_at DESC
                 LIMIT 1
                """,
                (empresa_id,),
            )
            row = await cur.fetchone()
    if row is None:
        return
    plano_slug = row[0]

    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            await conn.execute(
                "UPDATE empresa SET plano = %s, updated_at = NOW() "
                "WHERE id = %s",
                (plano_slug, empresa_id),
            )
            await conn.commit()
    clear_plano_cache(empresa_id)


# ---------------------------------------------------------------------
# Listagem pra UI
# ---------------------------------------------------------------------


async def list_transacoes(
    pool: AsyncConnectionPool, empresa_id: int, limit: int = 50
) -> list[dict[str, Any]]:
    """Lista últimas N transações da empresa pra UI billing/historico."""
    with empresa_scope(empresa_id=empresa_id):
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT t.id, t.tipo, t.valor_brl, t.status, t.gateway,
                       t.gateway_id, t.descricao, t.pago_em,
                       t.created_at, p.slug AS plano_slug, p.nome AS plano_nome
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
        }
        for r in rows
    ]


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------


def _only_digits(value: str) -> str:
    """Tira tudo que não é dígito (CPF/CNPJ)."""
    return "".join(c for c in value if c.isdigit())


__all__ = [
    "AsaasError",
    "cancel_active_subscription",
    "create_or_get_asaas_customer",
    "create_subscription_for_plano",
    "list_transacoes",
    "process_asaas_webhook",
]


# Silence unused imports (datetime/UTC used by future expansions)
_ = (datetime, UTC)
