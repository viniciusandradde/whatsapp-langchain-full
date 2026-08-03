"""Resumo diário de atendimentos por WhatsApp (mig 135).

Job periódico do worker: pra cada empresa com `resumo_diario_ativo`, no
horário configurado (fuso local, dias da semana marcados), monta um resumo
dos atendimentos do dia e envia pela CONEXÃO PADRÃO da empresa pro telefone
configurado. Idempotência: `resumo_diario_last_sent` guarda a data local do
último envio — claim atômico via UPDATE condicional, seguro em multi-worker.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.rls_context import empresa_scope

logger = structlog.get_logger()

# Tentativas do agendamento por dia local antes de desistir. Existe porque a
# falha devolve o dia: sem teto, um telefone inválido viraria uma chamada por
# minuto contra o provedor até a virada do dia. Cinco cobre a indisponibilidade
# curta (que é o caso realista) sem virar insistência.
MAX_TENTATIVAS = 5


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
            # Agregado sem GROUP BY sempre devolve exatamente 1 row, mas o
            # tipo é `tuple | None` — desempacotar direto não passa no pyright.
            contagens = await cur.fetchone()
            assert contagens is not None  # COUNT(*) sem GROUP BY
            novos, resolvidos, em_andamento, aguardando = contagens

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


async def _registrar_sucesso(
    pool: AsyncConnectionPool, empresa_id: int, local_date: date
) -> None:
    """Grava o resultado bom e zera o contador de tentativas do dia."""
    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            await conn.execute(
                """
                UPDATE empresa
                   SET resumo_diario_last_status = 'ok',
                       resumo_diario_last_error = NULL,
                       resumo_diario_last_attempt_at = NOW(),
                       resumo_diario_tentativas = 0,
                       resumo_diario_tentativas_dia = %s
                 WHERE id = %s
                """,
                (local_date, empresa_id),
            )
            await conn.commit()


async def _registrar_falha(
    pool: AsyncConnectionPool,
    empresa_id: int,
    erro: str,
    local_date: date,
    *,
    devolver_para: object | None,
) -> int:
    """Grava a falha e, enquanto houver tentativa, DEVOLVE o dia.

    `devolver_para` é o `last_sent` que existia antes do claim. Restaurá-lo é
    o que faz o próximo tick (60s) tentar de novo — antes disso, qualquer erro
    consumia a única chance do dia.

    Ao bater `MAX_TENTATIVAS` o dia fica consumido de propósito: falha
    permanente (telefone inválido, instância desconectada) não pode virar uma
    chamada por minuto contra o provedor até a virada do dia. O erro fica
    gravado e aparece na tela.

    Retorna o número de tentativas do dia após esta.
    """
    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                UPDATE empresa
                   SET resumo_diario_tentativas =
                           CASE WHEN resumo_diario_tentativas_dia = %(dia)s
                                THEN resumo_diario_tentativas + 1 ELSE 1 END,
                       resumo_diario_tentativas_dia = %(dia)s,
                       resumo_diario_last_status = 'erro',
                       resumo_diario_last_error = %(erro)s,
                       resumo_diario_last_attempt_at = NOW()
                 WHERE id = %(eid)s
             RETURNING resumo_diario_tentativas
                """,
                {"dia": local_date, "erro": erro[:500], "eid": empresa_id},
            )
            row = await cur.fetchone()
            tentativas = int(row[0]) if row else MAX_TENTATIVAS

            if tentativas < MAX_TENTATIVAS:
                await conn.execute(
                    "UPDATE empresa SET resumo_diario_last_sent = %s WHERE id = %s",
                    (devolver_para, empresa_id),
                )
            await conn.commit()
    return tentativas


async def _enviar(pool: AsyncConnectionPool, cfg: ResumoConfig) -> int:
    """Monta e envia o resumo pela conexão padrão. Devolve o id da conexão.

    Levanta exceção em qualquer falha — quem chama decide o que fazer com o
    dia. Ausência de conexão ativa também é falha: antes esse caminho dava
    `continue` depois do claim, e a empresa perdia o dia por não ter conexão
    naquele instante.
    """
    from whatsapp_langchain.shared.conexao import list_conexoes
    from whatsapp_langchain.shared.outbound import build_outbound_client

    texto = await montar_resumo(pool, cfg.empresa_id, cfg.tz)

    with empresa_scope(cfg.empresa_id):
        conexoes = await list_conexoes(pool, cfg.empresa_id)
    ativas = [c for c in conexoes if c.status == "active"]
    if not ativas:
        raise RuntimeError("empresa sem conexão ativa para enviar o resumo")

    conexao = ativas[0]  # list_conexoes ordena is_default DESC
    with empresa_scope(cfg.empresa_id):
        client, _mode = await build_outbound_client(pool, conexao)
        await client.send_message(cfg.telefone, texto)
    return conexao.id


async def _processar_empresa(pool: AsyncConnectionPool, cfg: ResumoConfig) -> bool:
    """Claim + envio de uma empresa. True quando o resumo saiu.

    O claim continua vindo ANTES do envio — é ele que impede dois workers de
    mandarem o mesmo resumo. O que mudou é o desfecho da falha: o dia volta
    pro estado anterior e o tick seguinte tenta de novo.
    """
    local_date = datetime.now(UTC).astimezone(ZoneInfo(cfg.tz)).date()
    anterior = cfg.last_sent

    if not await _claim_envio_hoje(pool, cfg.empresa_id, cfg.tz):
        return False

    try:
        conexao_id = await _enviar(pool, cfg)
    except Exception as exc:  # noqa: BLE001 — best-effort por empresa
        tentativas = await _registrar_falha(
            pool,
            cfg.empresa_id,
            str(exc),
            local_date,
            devolver_para=anterior,
        )
        logger.warning(
            "resumo_diario_falhou",
            empresa_id=cfg.empresa_id,
            error=str(exc),
            tentativas=tentativas,
            desistiu_do_dia=tentativas >= MAX_TENTATIVAS,
        )
        return False

    await _registrar_sucesso(pool, cfg.empresa_id, local_date)
    logger.info(
        "resumo_diario_enviado",
        empresa_id=cfg.empresa_id,
        conexao_id=conexao_id,
        telefone=cfg.telefone,
    )
    return True


async def enviar_resumo_agora(
    pool: AsyncConnectionPool, empresa_id: int
) -> tuple[bool, str | None]:
    """Envia o resumo AGORA, ignorando horário e dia da semana.

    Não toca em `resumo_diario_last_sent`: validar a configuração não pode
    custar o envio agendado do dia. Grava o resultado, porque é justamente
    isso que o botão serve pra descobrir.

    Devolve (ok, erro) — o erro sobe pra tela em vez de virar linha de log.
    """
    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT resumo_diario_telefone, resumo_diario_horario,
                       resumo_diario_dias, resumo_diario_tz
                  FROM empresa WHERE id = %s
                """,
                (empresa_id,),
            )
            row = await cur.fetchone()

    if row is None:
        return False, "Empresa não encontrada."
    telefone, horario, dias, tz = row
    if not telefone:
        return False, "Informe o telefone de destino antes de testar."

    tz = tz or "America/Campo_Grande"
    cfg = ResumoConfig(
        empresa_id=empresa_id,
        telefone=telefone,
        horario=horario,
        dias=list(dias or []),
        tz=tz,
        last_sent=None,
    )
    local_date = datetime.now(UTC).astimezone(ZoneInfo(tz)).date()

    try:
        conexao_id = await _enviar(pool, cfg)
    except Exception as exc:  # noqa: BLE001 — o erro é a resposta, não um log
        with empresa_scope(empresa_id):
            async with pool.connection() as conn:
                await conn.execute(
                    """
                    UPDATE empresa
                       SET resumo_diario_last_status = 'erro',
                           resumo_diario_last_error = %s,
                           resumo_diario_last_attempt_at = NOW()
                     WHERE id = %s
                    """,
                    (str(exc)[:500], empresa_id),
                )
                await conn.commit()
        logger.warning(
            "resumo_diario_teste_falhou", empresa_id=empresa_id, error=str(exc)
        )
        return False, str(exc)

    await _registrar_sucesso(pool, empresa_id, local_date)
    logger.info(
        "resumo_diario_teste_enviado", empresa_id=empresa_id, conexao_id=conexao_id
    )
    return True, None


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
            if await _processar_empresa(pool, cfg):
                enviados += 1
        except Exception as exc:  # noqa: BLE001 — uma empresa não derruba o laço
            logger.warning(
                "resumo_diario_erro_inesperado", empresa_id=eid, error=str(exc)
            )
    return enviados
