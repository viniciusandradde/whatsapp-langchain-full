"""Gates de plano que rodam POR MENSAGEM no worker (ADR-005).

Regra da ADR (D2): no worker o plano **degrada**, nunca falha o turno. Tudo
aqui é best-effort — plano ilegível devolve "liberado" com log, o mesmo que o
loader faz com `contexto_max` (mig 188).

Leva A: limite de atendimentos no mês (D5) — quando a empresa passa do
`limite_atendimentos_mes`, a IA para e o atendimento humano continua. O
contador é cacheado por 60 s por empresa: é um COUNT por mensagem em produção
sem o cache, e o número não precisa ser exato ao segundo.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Final

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.plano_limits import (
    count_atendimentos_mes,
    get_plano_info,
)
from whatsapp_langchain.shared.rls_context import empresa_scope

logger = structlog.get_logger()

# Percentual a partir do qual a empresa é avisada (uma vez por mês).
ALERTA_PCT: Final = 80
_CACHE_TTL_SECONDS: Final = 60.0
# empresa_id → (monotonic, usado)
_contagem_cache: dict[int, tuple[float, int]] = {}


def limpar_cache_contagem(empresa_id: int | None = None) -> None:
    if empresa_id is None:
        _contagem_cache.clear()
    else:
        _contagem_cache.pop(empresa_id, None)


@dataclass(frozen=True)
class StatusAtendimentosMes:
    """Uso × limite de atendimentos no mês corrente."""

    usado: int
    limite: int | None  # None = ilimitado

    @property
    def percentual(self) -> float | None:
        if self.limite is None or self.limite <= 0:
            return None
        return round(self.usado * 100.0 / self.limite, 1)

    @property
    def atingido(self) -> bool:
        """True quando a IA deve parar.

        `>` e não `>=`: na hora da checagem o atendimento desta mensagem JÁ
        foi criado e está no `usado`, então o 100º de um plano de 100 ainda
        é atendido — é o 101º que fica sem IA. (Na criação via API o
        `passou_limite` usa `>=` porque conta ANTES de criar.)
        """
        return self.limite is not None and self.usado > self.limite

    @property
    def em_alerta(self) -> bool:
        pct = self.percentual
        return pct is not None and pct >= ALERTA_PCT

    def to_dict(self) -> dict:
        return {
            "usado": self.usado,
            "limite": self.limite,
            "percentual": self.percentual,
            "atingido": self.atingido,
            "em_alerta": self.em_alerta,
        }


async def status_atendimentos_mes(
    pool: AsyncConnectionPool, empresa_id: int
) -> StatusAtendimentosMes:
    """Lê o plano (cache 30 s) e o contador do mês (cache 60 s). Levanta em
    falha — quem chama decide (o worker degrada, a API propaga)."""
    plano = await get_plano_info(pool, empresa_id)
    now = time.monotonic()
    cached = _contagem_cache.get(empresa_id)
    if cached and now - cached[0] < _CACHE_TTL_SECONDS:
        usado = cached[1]
    else:
        usado = await count_atendimentos_mes(pool, empresa_id)
        _contagem_cache[empresa_id] = (now, usado)
    return StatusAtendimentosMes(usado=usado, limite=plano.limite_atendimentos_mes)


async def ia_pausada_pelo_plano(
    pool: AsyncConnectionPool, empresa_id: int
) -> StatusAtendimentosMes | None:
    """Devolve o status quando a IA deve ficar calada; None quando pode rodar.

    Best-effort: qualquer erro (plano ilegível, banco fora) libera a IA com
    log — um problema de leitura de plano não pode calar o atendimento.
    """
    try:
        st = await status_atendimentos_mes(pool, empresa_id)
    except Exception as exc:
        logger.warning(
            "plano_atendimentos_ilegivel", empresa_id=empresa_id, error=str(exc)
        )
        return None
    return st if st.atingido else None


async def avisar_limite_atendimentos_se_preciso(
    pool: AsyncConnectionPool, empresa_id: int, st: StatusAtendimentosMes
) -> bool:
    """Avisa a empresa UMA vez por mês quando passa de `ALERTA_PCT` (D5).

    O claim é o `UPDATE ... WHERE marca IS NULL OR marca < início do mês`:
    atômico entre as réplicas do worker, sem tabela nova. O aviso sai pelo
    WhatsApp do resumo diário (`resumo_diario_telefone`); empresa sem esse
    telefone só vê o banner do painel — o claim é feito mesmo assim, para
    não consultar de novo a cada mensagem. Devolve True quando enviou.
    """
    if not st.em_alerta:
        return False
    try:
        with empresa_scope(None, bypass=True):
            async with pool.connection() as conn:
                cur = await conn.execute(
                    """
                    UPDATE empresa
                       SET plano_alerta_atendimentos_em = NOW()
                     WHERE id = %s
                       AND (plano_alerta_atendimentos_em IS NULL
                            OR plano_alerta_atendimentos_em < date_trunc('month', NOW()))
                    RETURNING resumo_diario_telefone
                    """,
                    (empresa_id,),
                )
                row = await cur.fetchone()
                await conn.commit()
        if row is None:
            return False  # outra réplica já avisou este mês
        telefone = row[0]
        if not telefone:
            logger.info(
                "plano_atendimentos_alerta_sem_telefone",
                empresa_id=empresa_id,
                usado=st.usado,
                limite=st.limite,
            )
            return False
        await _enviar_whatsapp(pool, empresa_id, telefone, _texto_alerta(st))
        logger.info(
            "plano_atendimentos_alerta_enviado",
            empresa_id=empresa_id,
            usado=st.usado,
            limite=st.limite,
        )
        return True
    except Exception as exc:
        logger.warning(
            "plano_atendimentos_alerta_falhou", empresa_id=empresa_id, error=str(exc)
        )
        return False


def _texto_alerta(st: StatusAtendimentosMes) -> str:
    if st.atingido:
        return (
            "⚠️ *Chat Nexus — limite do plano*\n\n"
            f"Sua empresa passou do limite de {st.limite} atendimentos neste mês "
            f"({st.usado} até agora). O agente de IA está pausado até o próximo "
            "mês; os atendentes continuam recebendo as conversas normalmente.\n\n"
            "Para liberar a IA agora, faça upgrade do plano no painel."
        )
    return (
        "⚠️ *Chat Nexus — limite do plano*\n\n"
        f"Sua empresa já usou {st.usado} de {st.limite} atendimentos deste mês "
        f"({st.percentual:.0f}%). Ao chegar no limite, o agente de IA para de "
        "responder e os atendentes continuam.\n\n"
        "Se precisar de mais, faça upgrade do plano no painel."
    )


async def _enviar_whatsapp(
    pool: AsyncConnectionPool, empresa_id: int, telefone: str, texto: str
) -> None:
    """Mesmo caminho do resumo diário (`shared/resumo_diario.py::_enviar`)."""
    from whatsapp_langchain.shared.conexao import list_conexoes
    from whatsapp_langchain.shared.outbound import build_outbound_client

    with empresa_scope(empresa_id):
        conexoes = await list_conexoes(pool, empresa_id)
    ativas = [c for c in conexoes if c.status == "active"]
    if not ativas:
        raise RuntimeError("empresa sem conexão ativa para enviar o aviso")
    conexao = ativas[0]  # list_conexoes ordena is_default DESC
    with empresa_scope(empresa_id):
        client, _mode = await build_outbound_client(pool, conexao)
        await client.send_message(telefone, texto)
