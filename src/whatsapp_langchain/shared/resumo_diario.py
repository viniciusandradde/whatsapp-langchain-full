"""Resumo diário de atendimentos por WhatsApp (mig 135).

Job periódico do worker: pra cada empresa com `resumo_diario_ativo`, no
horário configurado (fuso local, dias da semana marcados), monta um resumo
dos atendimentos do dia e envia pela CONEXÃO PADRÃO da empresa pro telefone
configurado. Idempotência: `resumo_diario_last_sent` guarda a data local do
último envio — claim atômico via UPDATE condicional, seguro em multi-worker.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.rls_context import empresa_scope

logger = structlog.get_logger()


@dataclass
class ResumoConfig:
    empresa_id: int
    telefone: str
    horario: time
    dias: list[int]  # ISO: 1=segunda ... 7=domingo
    tz: str
    last_sent: object | None  # date local do último envio


def deve_enviar(cfg: ResumoConfig, now_utc: datetime | None = None) -> bool:
    """True quando: dia da semana marcado, horário local >= configurado e
    ainda não enviou hoje (data local). Função pura — testável sem DB."""
    now_utc = now_utc or datetime.now(UTC)
    try:
        local = now_utc.astimezone(ZoneInfo(cfg.tz))
    except Exception:  # tz inválida cadastrada — não trava o loop
        local = now_utc.astimezone(ZoneInfo("America/Campo_Grande"))
    if local.isoweekday() not in (cfg.dias or []):
        return False
    if local.time() < cfg.horario:
        return False
    return cfg.last_sent != local.date()


async def montar_resumo(pool: AsyncConnectionPool, empresa_id: int, tz: str) -> str:
    """Monta o texto do resumo do dia (dia LOCAL da empresa).

    Formato WhatsApp: texto puro, blocos curtos. Conteúdo estruturado que a
    plataforma conhece (status/fila); a triagem fina (categorias do agente)
    fica na conversa de cada atendimento.
    """
    local_now = datetime.now(UTC).astimezone(ZoneInfo(tz))
    dia = local_now.date()

    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT
                  COUNT(*) FILTER (WHERE created_at::date = %(dia)s) AS novos,
                  COUNT(*) FILTER (WHERE status = 'resolvido'
                                   AND updated_at::date = %(dia)s) AS resolvidos,
                  COUNT(*) FILTER (WHERE status = 'em_andamento') AS em_andamento,
                  COUNT(*) FILTER (WHERE status = 'aguardando') AS aguardando
                  FROM atendimento WHERE empresa_id = %(eid)s
                """,
                {"dia": dia, "eid": empresa_id},
            )
            novos, resolvidos, em_andamento, aguardando = await cur.fetchone()

            cur = await conn.execute(
                """
                SELECT COALESCE(c.nome, c.telefone, '?'), a.updated_at
                  FROM atendimento a
                  LEFT JOIN cliente c ON c.id = a.cliente_id
                 WHERE a.empresa_id = %s AND a.status IN ('aguardando', 'em_andamento')
                 ORDER BY a.updated_at DESC
                 LIMIT 10
                """,
                (empresa_id,),
            )
            pendentes = await cur.fetchall()

    linhas = [
        f"RESUMO DO DIA — {dia.strftime('%d/%m/%Y')}",
        "",
        f"Conversas novas hoje: {novos}",
        f"Resolvidas hoje: {resolvidos}",
        f"Em andamento: {em_andamento} | Aguardando: {aguardando}",
    ]
    if pendentes:
        linhas += ["", "Pendentes (mais recentes):"]
        for nome, upd in pendentes:
            hora = upd.astimezone(ZoneInfo(tz)).strftime("%H:%M") if upd else "--:--"
            linhas.append(f"- {nome} (última atividade {hora})")
    else:
        linhas += ["", "Nenhum atendimento pendente. Tudo em dia."]
    linhas += ["", "Detalhes no painel, aba Atendimentos."]
    return "\n".join(linhas)


async def _claim_envio_hoje(
    pool: AsyncConnectionPool, empresa_id: int, tz: str
) -> bool:
    """Marca o envio de HOJE (data local) atomicamente.

    UPDATE condicional: só ganha quem trocar o last_sent primeiro — evita
    envio duplicado com múltiplos workers rodando o mesmo loop.
    """
    local_date = datetime.now(UTC).astimezone(ZoneInfo(tz)).date()
    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                UPDATE empresa SET resumo_diario_last_sent = %s
                 WHERE id = %s
                   AND (resumo_diario_last_sent IS NULL
                        OR resumo_diario_last_sent < %s)
                """,
                (local_date, empresa_id, local_date),
            )
            await conn.commit()
            return cur.rowcount > 0


async def run_resumo_diario_all(pool: AsyncConnectionPool) -> int:
    """Varre empresas com resumo ativo e envia os que estão no horário.

    Retorna quantos resumos foram enviados neste tick. Erros por empresa são
    logados e não derrubam o loop (best-effort, mesmo padrão do cleanup).
    """
    from whatsapp_langchain.shared.rls_context import empresa_scope as _scope

    with _scope(None, bypass=True):
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT id, resumo_diario_telefone, resumo_diario_horario,
                       resumo_diario_dias, resumo_diario_tz,
                       resumo_diario_last_sent
                  FROM empresa
                 WHERE status = 'active' AND resumo_diario_ativo
                   AND resumo_diario_telefone IS NOT NULL
                """
            )
            rows = await cur.fetchall()

    enviados = 0
    for eid, tel, horario, dias, tz, last_sent in rows:
        cfg = ResumoConfig(
            empresa_id=eid,
            telefone=tel,
            horario=horario,
            dias=list(dias or []),
            tz=tz or "America/Campo_Grande",
            last_sent=last_sent,
        )
        if not deve_enviar(cfg):
            continue
        try:
            # Claim ANTES de enviar: em duplicidade de worker, só um passa.
            # Trade-off: falha de envio adia pro dia seguinte (aceitável;
            # o erro fica logado pra diagnóstico).
            if not await _claim_envio_hoje(pool, eid, cfg.tz):
                continue
            texto = await montar_resumo(pool, eid, cfg.tz)

            from whatsapp_langchain.shared.conexao import list_conexoes
            from whatsapp_langchain.shared.outbound import build_outbound_client

            with empresa_scope(eid):
                conexoes = await list_conexoes(pool, eid)
            ativas = [c for c in conexoes if c.status == "active"]
            if not ativas:
                logger.warning("resumo_diario_sem_conexao", empresa_id=eid)
                continue
            conexao = ativas[0]  # list_conexoes ordena is_default DESC
            with empresa_scope(eid):
                client, _mode = await build_outbound_client(pool, conexao)
                await client.send_message(cfg.telefone, texto)
            enviados += 1
            logger.info(
                "resumo_diario_enviado",
                empresa_id=eid,
                conexao_id=conexao.id,
                telefone=cfg.telefone,
            )
        except Exception as exc:  # noqa: BLE001 — best-effort por empresa
            logger.warning("resumo_diario_falhou", empresa_id=eid, error=str(exc))
    return enviados
