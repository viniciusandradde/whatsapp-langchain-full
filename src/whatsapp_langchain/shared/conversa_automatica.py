"""Guarda contra conversa automática do outro lado (robô × robô).

Caso real (empresa 1018, 14/09/2026): o dono do número falou com o Santander
pelo WhatsApp comercial; a URA do banco respondeu ("este telefone ainda não
está habilitado", "você não escolheu uma das opções") e o agente de IA
respondeu de volta ("Certo", "Compreendido", "Como posso ajudar?") — 9 trocas
em 2 minutos, cortadas só porque o BANCO tinha teto de tentativas. Sem teto
do outro lado, o loop seguiria indefinidamente, pagando LLM a cada volta.

Três sinais por mensagem recebida (só texto; mídia não conta):

1. **cara de menu automático** — vocabulário de URA/assistente virtual em
   pt-BR (`PADROES_MENU`) E a mensagem chegou até `IMEDIATA_S` depois da NOSSA
   resposta (robô responde em segundos; humano que encaminha um print do
   banco leva mais). Número corporativo (400x/300x/0800…) dispensa o tempo.
2. **texto repetido** — igual a outra mensagem recebida na janela (≥
   `REPETIDO_MIN_CHARS`), chegando logo após a nossa resposta: robô reenvia o
   menu literalmente; humano não.
3. **longa e imediata** — ≥ `LONGA_MIN_CHARS` em até `LONGA_IMEDIATA_S`:
   ninguém digita isso nesse tempo. Pega IA × IA sem vocabulário de URA.

`MIN_SINAIS` sinais em `JANELA_MIN` minutos na conversa → o worker marca a
mensagem com `CONVERSA_AUTOMATICA_MARKER` e não chama typing/LLM/envio. A
conversa volta sozinha quando a janela passa sem sinal novo. Tempo SEM padrão
nunca conta: cliente que manda "ok" em 3 s é o caso normal, não o robô.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime

import structlog
from psycopg_pool import AsyncConnectionPool

logger = structlog.get_logger()

# Marcador na coluna `response` (registrado em `MARKERS_INTERNOS`).
CONVERSA_AUTOMATICA_MARKER = "[conversa automática — IA em espera]"

JANELA_MIN = 15
IMEDIATA_S = 20
LONGA_IMEDIATA_S = 10
LONGA_MIN_CHARS = 120
REPETIDO_MIN_CHARS = 30
MIN_SINAIS = 2
# Quantas mensagens recebidas da conversa olhar para trás (dentro da janela).
HISTORICO_MAX = 20

# Números não geográficos brasileiros de empresa (URA por trás): 400x/300x com
# DDD (8 dígitos) e 0800/0300/0500/0900 (E.164 sem o zero: +55 800 …).
_NUMERO_CORPORATIVO = re.compile(r"^\+55(?:\d{2}(?:400\d|300\d)\d{4}|(?:800|300|500|900)\d{7})$")

# Vocabulário de URA/assistente virtual, comparado SEM acento e em minúsculas.
PADROES_MENU: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p)
    for p in (
        r"assistente virtual",
        r"atendimento (automatico|virtual|digital)",
        r"mensagem automatica",
        r"nao (escolheu|selecionou|digitou) uma (das )?opc",
        r"opcao invalida",
        r"(digite|envie|responda|informe|selecione|escolha|tecle) (o numero|uma das opcoes|uma opcao|apenas o numero|o codigo|\*?\d)",
        r"quantidade maxima de tentativas",
        r"nao e possivel continuar",
        r"(telefone|numero|canal|contato) (ainda )?nao esta (habilitado|cadastrado|autorizado)",
        r"nao responda (esta|essa|a esta) mensagem",
        r"para (voltar ao menu|falar com um atendente|falar com um de nossos)",
        r"para continuar,? (digite|escolha|selecione|responda|informe)",
        r"menu (principal|inicial|de opcoes)",
        r"central de (atendimento|relacionamento)",
        r"(seu|o) (numero de |numero do )?protocolo",
        r"horario de atendimento (e|eh) (de|das)",
        r"vamos tentar (de novo|novamente)",
        # menu numerado: duas linhas começando por dígito + separador
        r"(^|\n)\s*\d\s*[-–.)]\s*\S[^\n]*\n\s*\d\s*[-–.)]\s*\S",
    )
)


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in sem_acento if not unicodedata.combining(c)).lower()


def parece_menu_automatico(texto: str) -> bool:
    """O texto tem vocabulário de URA/assistente virtual (sem acento, minúsculas)."""
    if not texto:
        return False
    norm = _normalizar(texto)
    return any(p.search(norm) for p in PADROES_MENU)


def numero_corporativo(telefone: str) -> bool:
    """Número não geográfico de empresa (400x/300x/0800…): URA por trás."""
    return bool(_NUMERO_CORPORATIVO.match(telefone or ""))


@dataclass(frozen=True)
class Recebida:
    """Uma mensagem recebida da conversa, com o instante da NOSSA resposta anterior."""

    texto: str
    recebida_em: datetime
    # `processed_at` da última row anterior cuja resposta saiu de verdade
    # (não marcador); None quando não houve resposta antes desta.
    resposta_anterior_em: datetime | None = None


@dataclass(frozen=True)
class Veredito:
    suspender: bool
    sinais: tuple[str, ...] = field(default_factory=tuple)


def _segundos_apos_resposta(m: Recebida) -> float | None:
    if m.resposta_anterior_em is None:
        return None
    return (m.recebida_em - m.resposta_anterior_em).total_seconds()


def sinal_da_mensagem(
    m: Recebida, textos_anteriores: set[str], *, corporativo: bool
) -> str | None:
    """Um sinal (ou nenhum) para a mensagem, dado o que veio antes na janela."""
    texto = (m.texto or "").strip()
    if not texto:
        return None
    apos = _segundos_apos_resposta(m)
    imediata = apos is not None and 0 <= apos <= IMEDIATA_S
    if parece_menu_automatico(texto) and (imediata or corporativo):
        return "menu"
    norm = _normalizar(texto)
    if imediata and len(texto) >= REPETIDO_MIN_CHARS and norm in textos_anteriores:
        return "repetida"
    if (
        apos is not None
        and 0 <= apos <= LONGA_IMEDIATA_S
        and len(texto) >= LONGA_MIN_CHARS
    ):
        return "longa_imediata"
    return None


def avaliar(
    historico: list[Recebida], atual: Recebida, *, corporativo: bool
) -> Veredito:
    """Conta os sinais da janela (histórico + atual) e decide suspender.

    `historico` são as recebidas ANTERIORES da conversa dentro da janela, em
    ordem cronológica; `atual` é a mensagem que o worker vai processar. A
    repetição é medida contra o que veio antes de cada mensagem.
    """
    sinais: list[str] = []
    vistos: set[str] = set()
    for m in [*historico, atual]:
        s = sinal_da_mensagem(m, vistos, corporativo=corporativo)
        if s:
            sinais.append(s)
        if m.texto:
            vistos.add(_normalizar(m.texto.strip()))
    return Veredito(suspender=len(sinais) >= MIN_SINAIS, sinais=tuple(sinais))


async def carregar_historico(
    pool: AsyncConnectionPool,
    *,
    phone_number: str,
    agent_id: str,
    antes_de: datetime,
    excluir_id: int,
) -> tuple[list[Recebida], datetime | None]:
    """Recebidas da conversa na janela (mais antigas primeiro) e o instante da
    última resposta real antes de `antes_de` — para montar a `Recebida` atual.

    Índice `idx_queue_phone_agent (phone_number, agent_id, status)`.
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT incoming_message, created_at, response, processed_at
              FROM message_queue
             WHERE phone_number = %(phone)s AND agent_id = %(agent)s
               AND id <> %(id)s
               AND created_at > %(antes)s - make_interval(mins => %(janela)s)
               AND created_at <= %(antes)s
               AND COALESCE(interna, FALSE) = FALSE
             ORDER BY created_at DESC
             LIMIT %(limite)s
            """,
            {
                "phone": phone_number,
                "agent": agent_id,
                "id": excluir_id,
                "antes": antes_de,
                "janela": JANELA_MIN,
                "limite": HISTORICO_MAX,
            },
        )
        rows = list(await cur.fetchall())
    rows.reverse()
    historico: list[Recebida] = []
    ultima_resposta_em: datetime | None = None
    for incoming, created_at, response, processed_at in rows:
        if incoming:
            historico.append(
                Recebida(
                    texto=incoming,
                    recebida_em=created_at,
                    resposta_anterior_em=ultima_resposta_em,
                )
            )
        if response and not response.startswith("[") and processed_at:
            ultima_resposta_em = processed_at
    return historico, ultima_resposta_em


async def conversa_automatica(
    pool: AsyncConnectionPool,
    *,
    message_id: int,
    phone_number: str,
    agent_id: str,
    texto: str,
    recebida_em: datetime,
) -> Veredito:
    """Veredito para a mensagem que o worker vai processar (1 SELECT)."""
    historico, ultima_resposta_em = await carregar_historico(
        pool,
        phone_number=phone_number,
        agent_id=agent_id,
        antes_de=recebida_em,
        excluir_id=message_id,
    )
    atual = Recebida(
        texto=texto, recebida_em=recebida_em, resposta_anterior_em=ultima_resposta_em
    )
    return avaliar(historico, atual, corporativo=numero_corporativo(phone_number))
