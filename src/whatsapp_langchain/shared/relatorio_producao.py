"""Leitura e pedidos do relatório de produção (mig 173).

Quem PRODUZ o relatório é o script no host (`scripts/analise_producao.py`) —
ele tem acesso a docker, disco e aos logs da Evolution, que o container não
tem. Este módulo é o lado de dentro: lê o histórico que o host publicou e
enfileira pedidos de "gerar agora".

O painel nunca dispara o script diretamente. Abrir esse caminho exigiria SSH de
dentro do container ou o socket do Docker montado nele — e aí quem invadisse o
container controlaria a máquina. Em vez disso o painel só insere uma linha, e o
host, que já acorda de minuto em minuto, consome. A fronteira de privilégio
continua onde estava.

Escopo de PLATAFORMA: as tabelas não têm `empresa_id` e não têm RLS (falam do
servidor, não de um cliente). Quem protege é o gate `is_superadmin` nas rotas —
mesmo desenho de `platform_integration_config` (mig 117).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.rls_context import empresa_scope

logger = structlog.get_logger()


@dataclass(frozen=True, slots=True)
class ConfigRelatorio:
    ativo: bool
    horario: time
    tz: str
    last_run_date: str | None


def _sem_tenant():
    """As tabelas são de plataforma; o contexto de empresa não se aplica.

    `bypass=True` porque não há `empresa_id` para casar na policy — e sem isso
    o RLS STRICT recusaria a leitura fora de um request de tenant.
    """
    return empresa_scope(None, bypass=True)


async def listar_relatorios(
    pool: AsyncConnectionPool, *, limite: int = 30
) -> list[dict]:
    """Histórico, do mais recente para o mais antigo.

    Não devolve `dados` (a coleta crua): são dezenas de KB por linha e a lista
    não os usa. Quem quiser confere no detalhe.
    """
    with _sem_tenant():
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT id, criado_at, origem, solicitado_por, severidade,
                       achados, texto, modelo, erro
                  FROM relatorio_producao
                 ORDER BY criado_at DESC
                 LIMIT %s
                """,
                (limite,),
            )
            rows = await cur.fetchall()
    return [
        {
            "id": r[0],
            "criado_at": r[1].isoformat() if r[1] else None,
            "origem": r[2],
            "solicitado_por": r[3],
            "severidade": r[4],
            "achados": r[5] or [],
            "texto": r[6],
            "modelo": r[7],
            "erro": r[8],
        }
        for r in rows
    ]


async def get_relatorio(pool: AsyncConnectionPool, relatorio_id: int) -> dict | None:
    """Um relatório com os dados crus — é o que permite conferir a conclusão."""
    with _sem_tenant():
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT id, criado_at, origem, solicitado_por, severidade,
                       achados, texto, modelo, erro, dados
                  FROM relatorio_producao
                 WHERE id = %s
                """,
                (relatorio_id,),
            )
            row = await cur.fetchone()
    if row is None:
        return None
    return {
        "id": row[0],
        "criado_at": row[1].isoformat() if row[1] else None,
        "origem": row[2],
        "solicitado_por": row[3],
        "severidade": row[4],
        "achados": row[5] or [],
        "texto": row[6],
        "modelo": row[7],
        "erro": row[8],
        "dados": row[9] or {},
    }


async def criar_pedido(pool: AsyncConnectionPool, *, user_id: str) -> dict:
    """Enfileira um "gerar agora". Idempotente enquanto houver pendente.

    Clicar o botão duas vezes não deve render dois relatórios: o segundo
    clique recebe o pedido que já está na fila. Sem isso, um duplo-clique
    custaria duas chamadas ao modelo e duas coletas no host.
    """
    with _sem_tenant():
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT id, criado_at FROM relatorio_producao_pedido
                 WHERE atendido_at IS NULL
                 ORDER BY criado_at
                 LIMIT 1
                """
            )
            pendente = await cur.fetchone()
            if pendente is not None:
                return {
                    "id": pendente[0],
                    "criado_at": pendente[1].isoformat(),
                    "ja_existia": True,
                }

            cur = await conn.execute(
                """
                INSERT INTO relatorio_producao_pedido (solicitado_por)
                VALUES (%s)
                RETURNING id, criado_at
                """,
                (user_id,),
            )
            row = await cur.fetchone()
            await conn.commit()

    assert row is not None
    logger.info("relatorio_producao_pedido_criado", user_id=user_id, pedido_id=row[0])
    return {"id": row[0], "criado_at": row[1].isoformat(), "ja_existia": False}


async def pedido_pendente(pool: AsyncConnectionPool) -> dict | None:
    """Há pedido esperando o host? É o que a tela usa para dizer "gerando…"."""
    with _sem_tenant():
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT id, criado_at, solicitado_por
                  FROM relatorio_producao_pedido
                 WHERE atendido_at IS NULL
                 ORDER BY criado_at
                 LIMIT 1
                """
            )
            row = await cur.fetchone()
    if row is None:
        return None
    return {
        "id": row[0],
        "criado_at": row[1].isoformat(),
        "solicitado_por": row[2],
    }


async def get_config(pool: AsyncConnectionPool) -> ConfigRelatorio:
    with _sem_tenant():
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT ativo, horario, tz, last_run_date
                  FROM relatorio_producao_config WHERE id = 1
                """
            )
            row = await cur.fetchone()
    if row is None:
        # A migration semeia a linha; se sumiu, o default é o comportamento
        # antigo (ligado às 05:00 locais) em vez de silêncio.
        return ConfigRelatorio(True, time(5, 0), "America/Campo_Grande", None)
    return ConfigRelatorio(
        ativo=row[0],
        horario=row[1],
        tz=row[2],
        last_run_date=row[3].isoformat() if row[3] else None,
    )


async def update_config(
    pool: AsyncConnectionPool,
    *,
    ativo: bool,
    horario: time,
    tz: str,
) -> None:
    """Salva o agendamento.

    `last_run_date` NÃO é tocado de propósito: mudar o horário não deve fazer o
    relatório sair de novo no mesmo dia, nem pular o dia seguinte.
    """
    with _sem_tenant():
        async with pool.connection() as conn:
            await conn.execute(
                """
                UPDATE relatorio_producao_config
                   SET ativo = %s, horario = %s, tz = %s, atualizado_at = NOW()
                 WHERE id = 1
                """,
                (ativo, horario, tz),
            )
            await conn.commit()
    logger.info(
        "relatorio_producao_config_atualizada", ativo=ativo, horario=str(horario)
    )
