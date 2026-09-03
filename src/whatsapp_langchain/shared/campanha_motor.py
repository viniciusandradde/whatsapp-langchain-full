"""Motor durável de disparo — claim, lease e trilha de eventos (F2b, mig 183).

Por que este módulo existe: até a mig 183 o dispatcher rodava como
`asyncio.create_task` DENTRO do processo da API. A API reinicia a cada deploy
— e neste repo merge é deploy —, então qualquer merge no meio de uma campanha
matava o envio. E como `claim_scheduled_due` só reivindicava `scheduled`,
a campanha morta ficava `running` para sempre, com os destinatários `pendente`
para sempre: estado terminal, recuperável só por SQL manual.

O conserto não inventa mecanismo. É o mesmo padrão do `message_queue`
(`shared/queue.py::claim_next` + `worker/main.py::_lease_heartbeat`), que já
roda no worker com `FOR UPDATE SKIP LOCKED` + lease + heartbeat e é a parte
mais confiável do sistema — aplicado agora à campanha.

Duas garantias, em dois níveis:

1. **Campanha** — o claim tem três portas (`queued`, `scheduled` vencida e
   `running` com lease morto). A terceira é a fase inteira: campanha cujo dono
   morreu volta a ser reivindicável.
2. **Destinatário** — o lote é reivindicado com `FOR UPDATE SKIP LOCKED` e
   transição `pendente → enviando`. Sem isso, dois motores na mesma campanha
   enviam tudo em duplicado — e produção roda DOIS workers, então a corrida é
   real, não hipotética.

O fence do lease é load-bearing: `renovar_lease` casa por `lease_owner`, e um
worker que perdeu a propriedade PARA de trabalhar imediatamente. Sem isso, um
worker lento cujo lease expirou continuaria enviando ao lado do worker novo —
exatamente a duplicata que o claim existe para evitar.
"""

from __future__ import annotations

import json as _json
import os
import socket
from dataclasses import dataclass

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.rls_context import empresa_scope

logger = structlog.get_logger()

#: Identidade deste processo no lease. Dois workers no mesmo host têm pids
#: diferentes; o mesmo worker reiniciado tem pid novo e por isso NÃO se
#: reconhece como dono do lease antigo — que é o comportamento correto.
WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"

#: Duração do lease da campanha. Chute informado pelo `message_queue`
#: (LEASE_SECONDS=60); campanha usa o dobro porque um lote de 50 com jitter
#: anti-ban de 3-8s leva minutos. Calibrar depois do primeiro disparo real —
#: hoje não há dado de produção nenhum (o disparo nunca rodou).
LEASE_SECONDS = 120

#: Renovação a cada ~lease/3, mesmo critério do `_lease_heartbeat`.
HEARTBEAT_INTERVAL_S = max(5, LEASE_SECONDS // 3)

#: Depois de quanto tempo um destinatário `enviando` é considerado órfão.
#: Generoso de propósito: melhor esperar do que concorrer com um envio vivo.
DEST_ORFAO_SEGUNDOS = 600


# ---------------------------------------------------------------------------
# Trilha de eventos
# ---------------------------------------------------------------------------


async def _insert_evento(
    conn, empresa_id: int, camp_id: int, tipo: str, payload: dict | None = None
) -> None:
    """Grava um evento usando uma conexão já aberta (para entrar na transação
    de quem chama)."""
    await conn.execute(
        "INSERT INTO campanha_evento (campanha_id, empresa_id, tipo, payload)"
        " VALUES (%s, %s, %s, %s)",
        (camp_id, empresa_id, tipo, _json.dumps(payload or {})),
    )


async def registrar_evento(
    pool: AsyncConnectionPool,
    empresa_id: int,
    camp_id: int,
    tipo: str,
    payload: dict | None = None,
) -> None:
    """Grava um evento da campanha. Best-effort: trilha nunca derruba disparo.

    Substitui a concatenação em `campanha.descricao` (o histórico virava texto
    solto no campo que o usuário escreveu, impossível de consultar ou exibir).
    """
    try:
        with empresa_scope(empresa_id):
            async with pool.connection() as conn:
                await _insert_evento(conn, empresa_id, camp_id, tipo, payload)
                await conn.commit()
    except Exception as e:  # noqa: BLE001 — trilha é observabilidade, não fluxo
        logger.warning(
            "campanha_evento_falhou", camp_id=camp_id, tipo=tipo, erro=str(e)
        )


# ---------------------------------------------------------------------------
# Lease da campanha
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CampanhaClaim:
    """Campanha reivindicada, com o estado que ela tinha ANTES do claim.

    `era_orfa` é o que permite registrar a retomada: sem ele, "a campanha se
    recuperou sozinha" fica indistinguível de "nunca quebrou".
    """

    empresa_id: int
    camp_id: int
    status_anterior: str
    dono_anterior: str | None

    @property
    def era_orfa(self) -> bool:
        return self.status_anterior == "running"


async def claim_campanha(pool: AsyncConnectionPool) -> CampanhaClaim | None:
    """Reivindica UMA campanha para este worker.

    As três portas do `WHERE`:

    - `queued` — o usuário mandou disparar e ninguém pegou ainda.
    - `scheduled` vencida — o agendamento chegou a hora (era o único caso que
      o `claim_scheduled_due` cobria).
    - `running` com `lease_expires_at` no passado — **a campanha órfã**. É a
      porta que conserta o estado terminal: o dono morreu, o lease venceu,
      outro worker assume de onde parou (os `enviado` já estão gravados, o
      loop só relê `pendente`).

    `LIMIT 1` é deliberado: uma campanha por worker, para que um disparo longo
    não monopolize o processo que também atende `message_queue`.

    Cross-tenant por design (o worker varre todas as empresas), daí o bypass de
    RLS — mesmo contrato do `claim_scheduled_due`.

    O `UPDATE ... FROM (subquery)` em vez de `WHERE id IN (...)` existe por um
    motivo: `RETURNING` devolve os valores NOVOS, e precisamos dos ANTIGOS pra
    saber se este claim foi uma retomada de órfã. A subquery já os carrega.
    """
    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn, conn.transaction():
            cur = await conn.execute(
                """
                UPDATE campanha c
                   SET status = 'running',
                       lease_owner = %s,
                       lease_expires_at = NOW() + (%s || ' seconds')::interval,
                       heartbeat_at = NOW(),
                       started_at = COALESCE(c.started_at, NOW()),
                       updated_at = NOW()
                  FROM (
                    SELECT id,
                           status      AS status_antes,
                           lease_owner AS dono_antes
                      FROM campanha
                     WHERE status = 'queued'
                        OR (status = 'scheduled' AND scheduled_at IS NOT NULL
                            AND scheduled_at <= NOW())
                        OR (status = 'running' AND lease_expires_at IS NOT NULL
                            AND lease_expires_at < NOW())
                     ORDER BY COALESCE(scheduled_at, updated_at)
                     FOR UPDATE SKIP LOCKED
                     LIMIT 1
                  ) sel
                 WHERE c.id = sel.id
                RETURNING c.empresa_id, c.id, sel.status_antes, sel.dono_antes
                """,
                (WORKER_ID, LEASE_SECONDS),
            )
            row = await cur.fetchone()
    if row is None:
        return None
    return CampanhaClaim(
        empresa_id=row[0], camp_id=row[1], status_anterior=row[2], dono_anterior=row[3]
    )


async def renovar_lease(pool: AsyncConnectionPool, camp_id: int) -> bool:
    """Renova o lease. Retorna False se este worker NÃO é mais o dono.

    O fence por `lease_owner` é o que impede duplicata numa troca de dono: se
    o lease expirou e outro worker assumiu, este precisa parar de enviar
    imediatamente — os dois enviando é exatamente o cenário que o claim existe
    para evitar. Mesmo contrato do `renew_lease` do `message_queue`, que faz o
    fence por `attempts`.
    """
    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                UPDATE campanha
                   SET lease_expires_at = NOW() + (%s || ' seconds')::interval,
                       heartbeat_at = NOW()
                 WHERE id = %s AND lease_owner = %s AND status = 'running'
                """,
                (LEASE_SECONDS, camp_id, WORKER_ID),
            )
            await conn.commit()
            return (cur.rowcount or 0) > 0


async def liberar_lease(pool: AsyncConnectionPool, camp_id: int) -> None:
    """Solta o lease sem mexer no status — a campanha fica imediatamente
    reivindicável em vez de esperar o lease vencer."""
    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            await conn.execute(
                "UPDATE campanha SET lease_owner = NULL, lease_expires_at = NULL,"
                " updated_at = NOW() WHERE id = %s AND lease_owner = %s",
                (camp_id, WORKER_ID),
            )
            await conn.commit()


# ---------------------------------------------------------------------------
# Claim de destinatário
# ---------------------------------------------------------------------------


async def recuperar_destinatarios_orfaos(
    pool: AsyncConnectionPool, empresa_id: int, camp_id: int
) -> tuple[int, int]:
    """Resolve destinatários deixados em `enviando` por um worker que morreu.

    Retorna `(devolvidos, incertos)`.

    A decisão de para onde vai cada um sai de `provider_chamado_at`, gravado
    imediatamente antes da chamada ao provedor:

    - **NULL** → o envio nunca chegou a sair. Volta para `pendente`, será
      reenviado, sem risco de duplicata.
    - **setado, sem resultado** → pode ter saído. Vira `incerto` e **não é
      reenviado**.

    Não reenviar o incerto é deliberado: em disparo em massa a duplicata é pior
    que o buraco — é o sinal de spam que queimou o número na campanha 9 —, e o
    buraco é visível no relatório e corrigível por reenvio manual, enquanto a
    duplicata já saiu.
    """
    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                UPDATE campanha_destinatario
                   SET status = 'pendente', claimed_at = NULL, claimed_by = NULL
                 WHERE campanha_id = %s AND status = 'enviando'
                   AND provider_chamado_at IS NULL
                   AND claimed_at < NOW() - (%s || ' seconds')::interval
                """,
                (camp_id, DEST_ORFAO_SEGUNDOS),
            )
            devolvidos = cur.rowcount or 0
            cur = await conn.execute(
                """
                UPDATE campanha_destinatario
                   SET status = 'incerto',
                       erro = 'worker caiu depois de chamar o provedor — '
                              'não reenviado para não duplicar'
                 WHERE campanha_id = %s AND status = 'enviando'
                   AND provider_chamado_at IS NOT NULL
                   AND claimed_at < NOW() - (%s || ' seconds')::interval
                """,
                (camp_id, DEST_ORFAO_SEGUNDOS),
            )
            incertos = cur.rowcount or 0
            await conn.commit()
    if devolvidos or incertos:
        logger.info(
            "campanha_destinatarios_orfaos_recuperados",
            camp_id=camp_id,
            devolvidos=devolvidos,
            incertos=incertos,
        )
    return (devolvidos, incertos)


async def claim_destinatarios(
    pool: AsyncConnectionPool, empresa_id: int, camp_id: int, limite: int = 50
) -> list[tuple]:
    """Reivindica um lote de pendentes: `pendente → enviando` com dono e hora.

    Substitui o `SELECT ... WHERE status='pendente' LIMIT 50` que não tinha
    lock nenhum — dois motores liam o mesmo lote e enviavam tudo duas vezes.

    Retorna `(id, telefone, cliente_nome, variaveis)`, mesma tupla que o
    dispatcher já consumia.
    """
    with empresa_scope(empresa_id):
        async with pool.connection() as conn, conn.transaction():
            cur = await conn.execute(
                """
                UPDATE campanha_destinatario cd
                   SET status = 'enviando',
                       claimed_at = NOW(),
                       claimed_by = %s,
                       provider_chamado_at = NULL,
                       tentativas = cd.tentativas + 1
                 WHERE cd.id IN (
                    SELECT id FROM campanha_destinatario
                     WHERE campanha_id = %s AND status = 'pendente'
                     ORDER BY id
                     FOR UPDATE SKIP LOCKED
                     LIMIT %s
                 )
                RETURNING cd.id, cd.telefone, cd.cliente_id, cd.variaveis
                """,
                (WORKER_ID, camp_id, limite),
            )
            claimed = await cur.fetchall()
            if not claimed:
                return []
            # O nome do cliente vem de `cliente`, que o UPDATE..RETURNING não
            # alcança. Resolve em lote, sem N+1.
            ids = [r[2] for r in claimed if r[2] is not None]
            nomes: dict[int, str] = {}
            if ids:
                cur = await conn.execute(
                    "SELECT id, nome FROM cliente WHERE id = ANY(%s)", (ids,)
                )
                nomes = {r[0]: r[1] for r in await cur.fetchall()}
    return [(r[0], r[1], nomes.get(r[2]), r[3]) for r in claimed]


async def marcar_provider_chamado(
    pool: AsyncConnectionPool, empresa_id: int, dest_id: int
) -> None:
    """Marca o instante imediatamente ANTES da chamada ao provedor.

    É o que torna o órfão decidível: sem esta marca, um `enviando` abandonado
    é indistinguível entre "nunca saiu" e "pode ter saído", e as duas
    suposições erradas são simétricas (duplicar ou deixar buraco).
    """
    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            await conn.execute(
                "UPDATE campanha_destinatario SET provider_chamado_at = NOW()"
                " WHERE id = %s",
                (dest_id,),
            )
            await conn.commit()
