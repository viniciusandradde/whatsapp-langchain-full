"""Saúde das conexões dos clientes (mig 196) — "sem conexão" e "sem atividade".

Incidente 16→21/09/2026: o aparelho da empresa 1018 foi desvinculado, mas o
socket da Evolution ficou zumbi — `connectionState` seguiu dizendo `open` e
ninguém foi avisado por 4,5 dias. Este módulo combina três sinais por
conexão, cada um cobrindo o que o outro não vê:

1. **Passivo** — o webhook grava `connection.update` (estado + statusReason)
   em `conexao` (`registrar_evento_conexao`). No zumbi esse evento NÃO chega.
2. **Sonda ativa** — `connectionState` e uma consulta REAL ao WhatsApp com
   timeout curto (`fetch_profile_picture` do próprio número). O
   `whatsappNumbers` NÃO serve: tem cache e respondeu em 60 ms pela instância
   morta. Duas sondas ruins seguidas abrem `conexao_caida` (anti-flap).
3. **Silêncio contra baseline** — λ = mensagens esperadas na janela sem
   inbound, pela média por (dia da semana, hora LOCAL da empresa) das últimas
   4 semanas em `conexao_atividade`. λ ≥ `LAMBDA_MIN` com zero recebidas
   abre `sem_atividade`. Noite e fim de semana têm λ ≈ 0; cliente pequeno
   nunca dispara (a sonda cobre).

Episódios em `conexao_alerta` seguem a máquina da `ia_alerta` (mig 180):
uma linha ativa por (tipo, conexão), reabertura dentro do cooldown reativa a
mesma linha sem re-notificar, auto-resolve avisa só se o episódio foi
notificado e viveu ≥ 30 min. O tick manda UMA mensagem agrupada ao canal da
plataforma (`ia_alertas.notificar_plataforma`: Telegram + WhatsApp da VSA).

Regras puras ficam sem banco para o teste unitário; `avaliar_saude` recebe
sonda e notificador injetáveis (o E2E roda o job em processo). Texto ao
operador sem termo técnico, sem `_`, sem "pro/pra" (regra do dono).
"""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Final
from zoneinfo import ZoneInfo

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.plano_vigencia import TZ_PADRAO

logger = structlog.get_logger()

# --- Contrato visível (o teste unitário fixa estes números) -----------------
INTERVALO_TICK_SEGUNDOS: Final = 300  # um tick real a cada 5 min entre réplicas
SONDA_TIMEOUT_S: Final = 8.0
SONDAS_RUINS_MIN: Final = 2
SONDA_WABA_INTERVALO: Final = timedelta(hours=1)
BASELINE_DIAS: Final = 28
HISTORICO_MIN_DIAS: Final = 14.0
JANELA_SILENCIO_MAX_H: Final = 24 * 7
# Régua empírica do silêncio (mig 198): o maior intervalo entre recebidas em
# horas ativas da PRÓPRIA conexão nos últimos 28 dias, × fator, com piso e
# teto. Substitui o Poisson da mig 196: mensagens chegam em rajadas, e a VSA
# teve 38 silêncios ≥ 1 h em horário comercial num mês, todos saudáveis.
SILENCIO_FATOR: Final = 1.5
SILENCIO_PISO_H: Final = 2.0
SILENCIO_TETO_H: Final = 24.0
HORA_ATIVA_MIN: Final = 0.5  # média de recebidas por hora para a hora contar como ativa
# Eco: mensagem ao próprio número cujo ACK de entrega (`messages.update`) tem de
# voltar pelo webhook — a Evolution v2 não reemite `messages.upsert` do que ela
# mesma enviou (conferido no dev, 21/09), então o ack é o retorno decisivo; ele
# prova o servidor do WhatsApp E o caminho Evolution → webhook → Nexus. Silêncio
# acima do normal não é alerta — é o gatilho do eco; alerta só se o eco não volta.
ECO_TIMEOUT_MIN: Final = 3
ECO_INTERVALO_MIN: Final = 120
ECO_FALHAS_MIN: Final = 2
ECO_PREFIXO: Final = "Verificação automática do Nexus"
ECO_TEXTO: Final = ECO_PREFIXO + " — pode ignorar esta mensagem."
ATIVIDADE_RETENCAO_DIAS: Final = 60
COOLDOWN_HORAS: Final = 6
RESOLVE_NOTIFICA_MIN: Final = 30
# statusReason que a Evolution NÃO tenta reconectar sozinha (codesToNotReconnect).
DESCONEXAO_DEFINITIVA: Final = frozenset({401, 402, 403, 406})
ESTADOS_PAREANDO: Final = frozenset({"pending", "qr_pending", "pairing_code_pending"})

TIPOS_LABEL: Final = {
    "conexao_caida": "Conexão caída",
    "sem_atividade": "Sem mensagens",
}

# Predicado canônico de "mensagem recebida do cliente" (o mesmo de
# shared/atendimento_visualizacao.py). starts_with e não LIKE '%' — o
# placeholder do psycopg confunde com % (tests/unit/test_sql_placeholders.py).
#
# Histórico importado do WhatsApp Business (Coexistence, mig 200) fica de fora:
# entra com o `created_at` original, de até 180 dias atrás, e inflaria a régua
# de atividade da conexão justamente nas horas em que ela ainda não existia.
PREDICADO_INBOUND: Final = (
    "incoming_message IS NOT NULL AND incoming_message <> '' "
    "AND COALESCE(interna, FALSE) = FALSE "
    "AND NOT starts_with(COALESCE(message_id, ''), 'synthetic:') "
    "AND NOT starts_with(COALESCE(normalized_input, ''), 'historico:')"
)

_MOTIVO_CODIGO: Final = {
    401: "aparelho desvinculado no celular",
    402: "sessão recusada pelo WhatsApp",
    403: "número bloqueado pelo WhatsApp",
    406: "sessão recusada pelo WhatsApp",
    408: "tempo esgotado, reconectando",
    411: "sessão inválida, é preciso parear de novo",
    428: "conexão perdida, reconectando",
    440: "sessão aberta em outro aparelho",
    500: "sessão corrompida, é preciso parear de novo",
    503: "WhatsApp indisponível",
    515: "reinício pedido pelo WhatsApp",
}


# --- Dados ------------------------------------------------------------------


@dataclass(frozen=True)
class ConexaoMonitorada:
    id: int
    empresa_id: int
    empresa_nome: str
    tz: str
    provider: str
    display_name: str | None
    from_number: str | None
    instance_name: str | None
    tipo_atendimento: str
    connection_state: str
    state_message: str | None
    ultimo_health_check_at: datetime | None
    ultimo_health_check_ok: bool | None
    sonda_falhas_seguidas: int
    desconexao_codigo: int | None
    desconexao_em: datetime | None
    ultimo_inbound_em: datetime | None
    eco_ativo: bool = True
    eco_pendente_id: str | None = None
    eco_enviado_em: datetime | None = None
    ultimo_eco_em: datetime | None = None
    eco_falhas_seguidas: int = 0
    eco_solicitado_em: datetime | None = None
    ultimo_ack_em: datetime | None = None


@dataclass(frozen=True)
class ResultadoSonda:
    ok: bool
    # normalize_state(): open|connecting|disconnected|error; None = HTTP falhou
    estado: str | None
    responde: bool | None  # a consulta real respondeu no prazo (None = não tentada)
    latencia_ms: int | None
    motivo: str  # humano, vai no alerta
    plataforma_fora: bool = False  # a Evolution em si não respondeu


@dataclass(frozen=True)
class Silencio:
    esperadas: float  # λ na janela [última recebida, agora] — só para o texto
    horas: float
    desde: datetime
    dias_historico: float
    limite_normal_h: float | None = None  # régua empírica (em horas ATIVAS)
    hora_ativa: bool = False  # a hora atual é uma em que esta conexão recebe
    horas_ativas: float = 0.0  # do silêncio, só as horas em que costuma receber

    @property
    def acima_do_normal(self) -> bool:
        return (
            self.limite_normal_h is not None
            and self.hora_ativa
            and self.horas_ativas >= self.limite_normal_h
        )


@dataclass(frozen=True)
class SinaisConexao:
    connection_state: str
    desconexao_codigo: int | None
    desconexao_em: datetime | None
    sonda: ResultadoSonda | None
    sonda_falhas_seguidas: int  # já contando a sonda deste tick
    silencio: Silencio | None  # None = histórico curto ou nunca recebeu
    ultimo_inbound_em: datetime | None
    eco_falhas_seguidas: int = 0  # já contando a decisão deste tick


@dataclass(frozen=True)
class Achado:
    tipo: str
    detalhe: dict[str, Any]


Sondar = Callable[[ConexaoMonitorada], Awaitable[ResultadoSonda | None]]
Notificar = Callable[[str, list[str]], Awaitable[bool]]
# Manda o eco ao próprio número e devolve o id da mensagem (None = não enviou).
EnviarEco = Callable[[ConexaoMonitorada], Awaitable[str | None]]


# --- Regras puras -----------------------------------------------------------


def _zona(tz: str) -> ZoneInfo:
    try:
        return ZoneInfo(tz)
    except Exception:  # noqa: BLE001 — fuso inválido no cadastro não pode parar o tick
        return ZoneInfo(TZ_PADRAO)


def descrever_desconexao(codigo: int | None, estado: str) -> str:
    """Texto humano do estado da conexão para o alerta e para `state_message`."""
    if estado in ("open", "ready"):
        return "conectada"
    if estado == "connecting":
        return "conectando"
    if estado in ESTADOS_PAREANDO:
        return "aguardando pareamento"
    if codigo is not None and codigo in _MOTIVO_CODIGO:
        return _MOTIVO_CODIGO[codigo]
    if estado == "disconnected":
        return "conexão fechada"
    return "erro na conexão"


def esperadas_na_janela(
    baseline: dict[tuple[int, int], float],
    inicio_utc: datetime,
    fim_utc: datetime,
    tz: str,
) -> float:
    """Soma das médias por (dia ISO, hora local) ao longo de [inicio, fim),
    com as horas das pontas contando pela fração coberta."""
    if fim_utc <= inicio_utc or not baseline:
        return 0.0
    zona = _zona(tz)
    total = 0.0
    t = inicio_utc
    while t < fim_utc:
        proxima_hora = t.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        fim_fatia = min(fim_utc, proxima_hora)
        fracao = (fim_fatia - t).total_seconds() / 3600.0
        local = t.astimezone(zona)
        total += baseline.get((local.isoweekday(), local.hour), 0.0) * fracao
        t = fim_fatia
    return total


def calcular_limite_silencio(
    gaps_h: list[float], dias_historico: float
) -> float | None:
    """Régua empírica: o maior intervalo saudável entre recebidas (em horas
    ativas) × `SILENCIO_FATOR`, entre piso e teto. None sem histórico
    suficiente ou sem intervalos — sem régua não se julga silêncio."""
    if dias_historico < HISTORICO_MIN_DIAS or not gaps_h:
        return None
    return min(SILENCIO_TETO_H, max(SILENCIO_PISO_H, max(gaps_h) * SILENCIO_FATOR))


def hora_ativa(
    baseline: dict[tuple[int, int], float], quando_utc: datetime, tz: str
) -> bool:
    """A (dia ISO, hora local) de `quando` é uma em que esta conexão costuma
    receber (média ≥ `HORA_ATIVA_MIN`). Noite e fim de semana não contam."""
    local = quando_utc.astimezone(_zona(tz))
    return baseline.get((local.isoweekday(), local.hour), 0.0) >= HORA_ATIVA_MIN


def horas_ativas_entre(
    baseline: dict[tuple[int, int], float],
    inicio_utc: datetime,
    fim_utc: datetime,
    tz: str,
) -> float:
    """Quantas horas de [inicio, fim) caem em horas ativas da conexão. É a
    unidade da régua: a noite e o fim de semana contam zero, então o
    intervalo 17:45 → 08:00 vale 15 min, não 14 h."""
    if fim_utc <= inicio_utc or not baseline:
        return 0.0
    zona = _zona(tz)
    total = 0.0
    t = inicio_utc
    while t < fim_utc:
        proxima_hora = t.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        fim_fatia = min(fim_utc, proxima_hora)
        local = t.astimezone(zona)
        if baseline.get((local.isoweekday(), local.hour), 0.0) >= HORA_ATIVA_MIN:
            total += (fim_fatia - t).total_seconds() / 3600.0
        t = fim_fatia
    return total


def calcular_silencio(
    baseline: dict[tuple[int, int], float],
    dias_historico: float,
    ultimo_inbound_em: datetime | None,
    now_utc: datetime,
    tz: str,
    limite_normal_h: float | None = None,
) -> Silencio | None:
    """Há quanto tempo a conexão não recebe, contra a régua da própria conexão.

    None quando não dá para julgar: nunca recebeu ou histórico menor que
    `HISTORICO_MIN_DIAS`. O λ (`esperadas`) continua calculado só para o
    texto do painel — quem decide é `limite_normal_h` (mig 198). A janela é
    limitada a 7 dias para nada crescer para sempre num silêncio longo."""
    if ultimo_inbound_em is None or dias_historico < HISTORICO_MIN_DIAS:
        return None
    inicio = max(ultimo_inbound_em, now_utc - timedelta(hours=JANELA_SILENCIO_MAX_H))
    ativa = hora_ativa(baseline, now_utc, tz)
    if inicio >= now_utc:
        return Silencio(
            0.0, 0.0, ultimo_inbound_em, dias_historico, limite_normal_h, ativa
        )
    esperadas = esperadas_na_janela(baseline, inicio, now_utc, tz)
    horas = (now_utc - inicio).total_seconds() / 3600.0
    return Silencio(
        esperadas,
        horas,
        ultimo_inbound_em,
        dias_historico,
        limite_normal_h,
        ativa,
        horas_ativas_entre(baseline, inicio, now_utc, tz),
    )


def decidir_eco(
    c: ConexaoMonitorada,
    silencio: Silencio | None,
    sonda_ok: bool | None,
    now_utc: datetime,
) -> str:
    """O que fazer com o eco neste tick: `enviar`, `aguardar` (há eco em voo
    dentro do prazo), `falhou` (o eco em voo venceu sem voltar) ou `nada`.

    Só Evolution com `eco_ativo`. Envia quando foi pedido fora do ciclo
    (`eco_solicitado_em`, ex.: logo após reconectar) ou quando o silêncio
    passou da régua em hora ativa com a sonda dizendo que o socket responde —
    é exatamente o caso ambíguo que o eco resolve. Respeita o intervalo
    mínimo entre ecos para não encher a conversa "Você" do cliente."""
    if c.provider != "evolution" or not c.eco_ativo:
        return "nada"
    if c.eco_pendente_id and c.eco_enviado_em is not None:
        voltou = c.ultimo_eco_em is not None and c.ultimo_eco_em >= c.eco_enviado_em
        if voltou:
            return "nada"
        if now_utc - c.eco_enviado_em >= timedelta(minutes=ECO_TIMEOUT_MIN):
            return "falhou"
        return "aguardar"
    ultimo = max(
        (t for t in (c.eco_enviado_em, c.ultimo_eco_em) if t is not None),
        default=None,
    )
    if c.eco_solicitado_em is not None and (
        c.eco_enviado_em is None or c.eco_enviado_em < c.eco_solicitado_em
    ):
        return "enviar"
    if (
        silencio is not None
        and silencio.acima_do_normal
        and sonda_ok is True
        and (ultimo is None or now_utc - ultimo >= timedelta(minutes=ECO_INTERVALO_MIN))
    ):
        return "enviar"
    return "nada"


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def avaliar_conexao(s: SinaisConexao) -> list[Achado]:
    """Decide o episódio a partir dos sinais. Pura. No máximo UM achado por
    conexão, sempre `conexao_caida`: evento definitivo > sondas ruins > ecos
    sem retorno. Silêncio nunca abre episódio (mig 198)."""
    if (
        s.connection_state in ("disconnected", "error")
        and s.desconexao_codigo in DESCONEXAO_DEFINITIVA
    ):
        return [
            Achado(
                "conexao_caida",
                {
                    "motivo": descrever_desconexao(
                        s.desconexao_codigo, s.connection_state
                    ),
                    "origem": "evento",
                    "codigo": s.desconexao_codigo,
                    "desde": _iso(s.desconexao_em),
                },
            )
        ]
    if s.sonda_falhas_seguidas >= SONDAS_RUINS_MIN:
        return [
            Achado(
                "conexao_caida",
                {
                    "motivo": s.sonda.motivo if s.sonda else "sem resposta",
                    "origem": "sonda",
                    "falhas": s.sonda_falhas_seguidas,
                    "desde": _iso(s.desconexao_em),
                },
            )
        ]
    if s.eco_falhas_seguidas >= ECO_FALHAS_MIN:
        return [
            Achado(
                "conexao_caida",
                {
                    "motivo": (
                        "não recebe mensagens: a verificação enviada ao próprio "
                        "número não voltou"
                    ),
                    "origem": "eco",
                    "falhas": s.eco_falhas_seguidas,
                    "desde": _iso(s.ultimo_inbound_em),
                },
            )
        ]
    return []


def sonda_devida(c: ConexaoMonitorada, now_utc: datetime) -> bool:
    """Evolution: toda passada. WABA: só o token, 1× por hora (Graph)."""
    if c.provider == "evolution":
        return True
    if c.provider == "waba":
        return (
            c.ultimo_health_check_at is None
            or now_utc - c.ultimo_health_check_at >= SONDA_WABA_INTERVALO
        )
    return False


def monitoravel(c: ConexaoMonitorada) -> bool:
    """Conexão que ainda está sendo pareada e nunca recebeu nada não é
    incidente — aparece na tela como 'aguardando pareamento'."""
    return c.connection_state not in ESTADOS_PAREANDO or c.ultimo_inbound_em is not None


def _fmt_local(valor: datetime | str | None, tz: str) -> str:
    if valor is None:
        return "—"
    dt = datetime.fromisoformat(valor) if isinstance(valor, str) else valor
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(_zona(tz)).strftime("%d/%m %H:%M")


def duracao_humana(delta: timedelta) -> str:
    total_min = max(int(delta.total_seconds() // 60), 0)
    dias, resto = divmod(total_min, 24 * 60)
    horas, minutos = divmod(resto, 60)
    if dias:
        return (
            f"{dias} dia{'s' if dias > 1 else ''} e {horas} h"
            if horas
            else f"{dias} dia{'s' if dias > 1 else ''}"
        )
    if horas:
        return f"{horas} h {minutos:02d} min" if minutos else f"{horas} h"
    return f"{minutos} min"


def _nome_conexao(c: ConexaoMonitorada) -> str:
    nome = (c.display_name or "").replace("_", " ").strip()
    numero = (c.from_number or "").strip()
    if numero.startswith("evolution:"):
        numero = ""
    if nome and numero:
        return f"{nome} {numero}"
    return nome or numero or f"conexão {c.id}"


def formatar_linha(
    c: ConexaoMonitorada,
    pares: list[tuple[str, dict[str, Any]]],
    *,
    resolvido: bool = False,
    now_utc: datetime | None = None,
) -> str:
    """Uma linha por conexão: `Empresa (id) · Conexão: motivo · motivo · última mensagem recebida …`."""
    now = now_utc or datetime.now(UTC)
    partes: list[str] = []
    for tipo, d in pares:
        if tipo == "conexao_caida":
            if resolvido:
                criado = d.get("criado_em")
                fora = (
                    f" (ficou {duracao_humana(now - datetime.fromisoformat(criado))} fora)"
                    if criado
                    else ""
                )
                partes.append(f"conectada de novo{fora}")
            else:
                desde = d.get("desde")
                sufixo = f" — desde {_fmt_local(desde, c.tz)}" if desde else ""
                partes.append(f"{d.get('motivo', 'conexão fechada')}{sufixo}")
        elif tipo == "sem_atividade":
            if resolvido:
                partes.append("voltou a receber mensagens")
            else:
                desde = d.get("desde")
                ha = (
                    f"há {duracao_humana(now - datetime.fromisoformat(desde))}"
                    if desde
                    else "há um tempo"
                )
                esperadas = d.get("esperadas")
                esp = (
                    f" (esperadas ≈ {esperadas:.0f})"
                    if isinstance(esperadas, int | float)
                    else ""
                )
                texto = f"sem mensagens {ha}{esp}"
                if d.get("sonda_ok") is True:
                    texto += " · conexão responde"
                elif d.get("sonda_ok") is False:
                    texto += " · conexão sem resposta"
                partes.append(texto)
    ultima = (
        f"última mensagem recebida {_fmt_local(c.ultimo_inbound_em, c.tz)}"
        if c.ultimo_inbound_em
        else "nunca recebeu mensagem"
    )
    return f"{c.empresa_nome} ({c.empresa_id}) · {_nome_conexao(c)}: {' · '.join(partes)} · {ultima}"


def montar_mensagem(
    itens: list[tuple[ConexaoMonitorada, str, dict[str, Any]]],
    *,
    resolvido: bool = False,
    now_utc: datetime | None = None,
) -> list[str]:
    """Agrupa por conexão (uma linha por conexão), ordena por empresa."""
    por_conexao: dict[
        int, tuple[ConexaoMonitorada, list[tuple[str, dict[str, Any]]]]
    ] = {}
    for c, tipo, d in itens:
        por_conexao.setdefault(c.id, (c, []))[1].append((tipo, d))
    grupos = sorted(por_conexao.values(), key=lambda g: (g[0].empresa_id, g[0].id))
    return [
        formatar_linha(c, pares, resolvido=resolvido, now_utc=now_utc)
        for c, pares in grupos
    ]


# --- Banco: estado do tick e atividade -----------------------------------------


async def _claim_tick(pool: AsyncConnectionPool) -> datetime | None:
    """Uma réplica por tick: quem move `proximo_tick_em` roda. Devolve a marca
    d'água da atividade; None = outra réplica já rodou ou ainda é cedo."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            UPDATE saude_conexoes_estado
               SET proximo_tick_em = NOW() + make_interval(secs => %s),
                   ultimo_tick_em = NOW()
             WHERE id = 1 AND proximo_tick_em <= NOW()
            RETURNING marca_atividade
            """,
            (INTERVALO_TICK_SEGUNDOS - 30,),
        )
        row = await cur.fetchone()
    return row[0] if row else None


async def _ler_marca(pool: AsyncConnectionPool) -> datetime:
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT marca_atividade FROM saude_conexoes_estado WHERE id = 1"
        )
        row = await cur.fetchone()
    return row[0] if row else datetime.now(UTC) - timedelta(hours=1)


async def _fechar_tick(
    pool: AsyncConnectionPool, marca: datetime, *, ok: bool, erro: str | None = None
) -> None:
    async with pool.connection() as conn:
        await conn.execute(
            """
            UPDATE saude_conexoes_estado
               SET marca_atividade = %s, ultimo_tick_ok = %s, ultimo_erro = %s
             WHERE id = 1
            """,
            (marca, ok, (erro or "")[:500] or None),
        )


async def _acumular_atividade(conn, marca: datetime, corte: datetime) -> None:
    """Leva `message_queue` para `conexao_atividade` e `conexao.ultimo_inbound_em`.

    Recomputa os buckets desde a hora da marca (não soma): mover a marca
    para trás não duplica, e a hora parcial do tick anterior fica certa."""
    inicio = marca.replace(minute=0, second=0, microsecond=0)
    await conn.execute(
        f"""
        INSERT INTO conexao_atividade (conexao_id, empresa_id, hora, recebidas)
        SELECT conexao_id, empresa_id, date_trunc('hour', created_at), count(*)
          FROM message_queue
         WHERE conexao_id IS NOT NULL
           AND created_at >= %(inicio)s AND created_at < %(corte)s
           AND {PREDICADO_INBOUND}
         GROUP BY 1, 2, 3
        ON CONFLICT (conexao_id, hora) DO UPDATE SET recebidas = EXCLUDED.recebidas
        """,
        {"inicio": inicio, "corte": corte},
    )
    await conn.execute(
        f"""
        UPDATE conexao c
           SET ultimo_inbound_em = GREATEST(COALESCE(c.ultimo_inbound_em, 'epoch'::timestamptz), m.max_at)
          FROM (SELECT conexao_id, max(created_at) AS max_at
                  FROM message_queue
                 WHERE conexao_id IS NOT NULL
                   AND created_at >= %(inicio)s AND created_at < %(corte)s
                   AND {PREDICADO_INBOUND}
                 GROUP BY conexao_id) m
         WHERE c.id = m.conexao_id
        """,
        {"inicio": inicio, "corte": corte},
    )
    await conn.execute(
        "DELETE FROM conexao_atividade WHERE hora < NOW() - make_interval(days => %s)",
        (ATIVIDADE_RETENCAO_DIAS,),
    )


_COLS_MONITORADA = """
    c.id, c.empresa_id, e.nome, e.timezone, c.provider, c.display_name, c.from_number,
    c.payload_json->>'instance_name', c.credentials_encrypted, c.tipo_atendimento,
    c.connection_state, c.state_message, c.ultimo_health_check_at, c.ultimo_health_check_ok,
    c.sonda_falhas_seguidas, c.desconexao_codigo, c.desconexao_em, c.ultimo_inbound_em,
    c.eco_ativo, c.eco_pendente_id, c.eco_enviado_em, c.ultimo_eco_em,
    c.eco_falhas_seguidas, c.eco_solicitado_em, c.ultimo_ack_em
"""


def _row_monitorada(r) -> ConexaoMonitorada:
    instance_name = r[7]
    if not instance_name and r[8]:
        try:
            from whatsapp_langchain.integrations.crypto import decrypt_dict

            instance_name = decrypt_dict(r[8]).get("instance_name")
        except Exception:  # noqa: BLE001
            instance_name = None
    tz = r[3] or TZ_PADRAO
    try:
        ZoneInfo(tz)
    except Exception:  # noqa: BLE001
        tz = TZ_PADRAO
    return ConexaoMonitorada(
        id=int(r[0]),
        empresa_id=int(r[1]),
        empresa_nome=r[2] or f"empresa {r[1]}",
        tz=tz,
        provider=r[4],
        display_name=r[5],
        from_number=r[6],
        instance_name=instance_name,
        tipo_atendimento=r[9] or "ia",
        connection_state=r[10] or "pending",
        state_message=r[11],
        ultimo_health_check_at=r[12],
        ultimo_health_check_ok=r[13],
        sonda_falhas_seguidas=int(r[14] or 0),
        desconexao_codigo=r[15],
        desconexao_em=r[16],
        ultimo_inbound_em=r[17],
        eco_ativo=bool(r[18]) if r[18] is not None else True,
        eco_pendente_id=r[19],
        eco_enviado_em=r[20],
        ultimo_eco_em=r[21],
        eco_falhas_seguidas=int(r[22] or 0),
        eco_solicitado_em=r[23],
        ultimo_ack_em=r[24],
    )


async def _listar_monitoradas(pool: AsyncConnectionPool) -> list[ConexaoMonitorada]:
    """Todas as conexões ativas de empresas ativas (o chamador já está em bypass de RLS)."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {_COLS_MONITORADA}
              FROM conexao c JOIN empresa e ON e.id = c.empresa_id
             WHERE c.status = 'active' AND e.status = 'active'
             ORDER BY c.empresa_id, c.id
            """
        )
        rows = await cur.fetchall()
    return [_row_monitorada(r) for r in rows]


async def carregar_baseline(
    conn, conexao_id: int, tz: str, inicio: datetime, fim: datetime
) -> tuple[dict[tuple[int, int], float], float]:
    """Média de recebidas por (dia ISO, hora local) em [inicio, fim) e o
    tamanho do histórico em dias. Horas sem linha contam zero."""
    cur = await conn.execute(
        """
        WITH faixa AS (
            SELECT date_trunc('hour', GREATEST(
                       %(inicio)s::timestamptz,
                       COALESCE((SELECT min(hora) FROM conexao_atividade WHERE conexao_id = %(cid)s),
                                %(inicio)s::timestamptz))) AS ini,
                   date_trunc('hour', %(fim)s::timestamptz) AS fim
        ),
        horas AS (
            SELECT h FROM faixa, generate_series(ini, fim - interval '1 hour', interval '1 hour') AS h
             WHERE ini < fim
        ),
        serie AS (
            SELECT h, COALESCE(a.recebidas, 0) AS recebidas
              FROM horas
              LEFT JOIN conexao_atividade a ON a.conexao_id = %(cid)s AND a.hora = h
        )
        SELECT EXTRACT(ISODOW FROM (h AT TIME ZONE %(tz)s))::int,
               EXTRACT(HOUR FROM (h AT TIME ZONE %(tz)s))::int,
               avg(recebidas)::float,
               (SELECT EXTRACT(EPOCH FROM (fim - ini)) / 86400.0 FROM faixa)
          FROM serie
         GROUP BY 1, 2
        """,
        {"inicio": inicio, "fim": fim, "cid": conexao_id, "tz": tz},
    )
    rows = await cur.fetchall()
    baseline = {(int(r[0]), int(r[1])): float(r[2]) for r in rows}
    dias = float(rows[0][3]) if rows and rows[0][3] is not None else 0.0
    return baseline, max(dias, 0.0)


async def carregar_gaps_ativos(
    conn,
    conexao_id: int,
    tz: str,
    baseline: dict[tuple[int, int], float],
    inicio: datetime,
    fim: datetime,
) -> list[float]:
    """Intervalos entre recebidas consecutivas em [inicio, fim), medidos em
    HORAS ATIVAS da própria conexão (a noite conta zero). É a matéria-prima
    da régua empírica: o maior deles é o silêncio saudável já observado."""
    cur = await conn.execute(
        f"""
        WITH r AS (
            SELECT created_at AS t,
                   lag(created_at) OVER (ORDER BY created_at) AS t_ant
              FROM message_queue
             WHERE conexao_id = %(cid)s
               AND created_at >= %(inicio)s AND created_at < %(fim)s
               AND {PREDICADO_INBOUND}
        )
        SELECT t_ant, t FROM r WHERE t_ant IS NOT NULL
        """,
        {"cid": conexao_id, "inicio": inicio, "fim": fim},
    )
    gaps: list[float] = []
    for t_ant, t in await cur.fetchall():
        h = horas_ativas_entre(baseline, t_ant, t, tz)
        if h > 0:
            gaps.append(h)
    return gaps


async def _registrar_eco_enviado(
    conn, c: ConexaoMonitorada, key_id: str, now_utc: datetime
) -> None:
    # `now_utc` é o relógio do tick (o E2E roda ticks no passado) — o prazo do
    # eco é medido contra ele, não contra NOW().
    await conn.execute(
        """
        UPDATE conexao
           SET eco_pendente_id = %s, eco_enviado_em = %s, eco_solicitado_em = NULL,
               updated_at = NOW()
         WHERE id = %s
        """,
        (key_id, now_utc, c.id),
    )


async def _registrar_eco_falhou(conn, c: ConexaoMonitorada) -> int:
    cur = await conn.execute(
        """
        UPDATE conexao
           SET eco_pendente_id = NULL, eco_falhas_seguidas = eco_falhas_seguidas + 1,
               updated_at = NOW()
         WHERE id = %s
        RETURNING eco_falhas_seguidas
        """,
        (c.id,),
    )
    row = await cur.fetchone()
    return int(row[0]) if row else c.eco_falhas_seguidas + 1


async def _sondar_padrao_eco(c: ConexaoMonitorada) -> str | None:
    """Manda o eco ao próprio número pela instância da conexão (chave admin da
    Evolution, mesma da sonda). Em modo mock (dev) não chama a Evolution: o
    E2E injeta o retorno pelo webhook."""
    from whatsapp_langchain.integrations.evolution import admin as evo_admin
    from whatsapp_langchain.shared.config import settings

    if not settings.evolution_admin_enabled or not c.instance_name or not c.from_number:
        return None
    if (c.from_number or "").startswith("evolution:"):
        return None  # ainda sem número real
    if (settings.evolution_outbound_mode or "mock") != "real":
        return f"mock-eco-{uuid.uuid4().hex[:12]}"
    return await evo_admin.send_text(c.instance_name, c.from_number, ECO_TEXTO)


async def _registrar_sonda(conn, c: ConexaoMonitorada, r: ResultadoSonda | None) -> int:
    """Grava o resultado na conexão. `connection_state` continua sendo a
    palavra da Evolution (não vira `error` quando ela diz `open` e a
    consulta estoura — quem julga isso é o episódio); estados de pareamento
    não são sobrescritos por uma sonda que diz fechada. Qualquer sonda ruim
    carimba o primeiro `desconexao_em` (é o "desde quando" do alerta, também
    no zumbi em que a Evolution diz `open`); sonda boa limpa."""
    if r is None:
        return c.sonda_falhas_seguidas
    cur = await conn.execute(
        """
        UPDATE conexao
           SET ultimo_health_check_at = NOW(),
               ultimo_health_check_ok = %(ok)s,
               state_message = %(msg)s,
               sonda_falhas_seguidas = CASE WHEN %(ok)s THEN 0 ELSE sonda_falhas_seguidas + 1 END,
               connection_state = CASE
                   WHEN %(estado)s = 'open' THEN 'open'
                   WHEN %(estado)s IS NULL THEN connection_state
                   WHEN connection_state IN ('pending', 'qr_pending', 'pairing_code_pending')
                        THEN connection_state
                   ELSE %(estado)s END,
               desconexao_em = CASE
                   WHEN %(ok)s THEN NULL
                   ELSE COALESCE(desconexao_em, NOW()) END,
               desconexao_codigo = CASE WHEN %(ok)s THEN NULL ELSE desconexao_codigo END,
               updated_at = NOW()
         WHERE id = %(id)s
        RETURNING sonda_falhas_seguidas
        """,
        {"ok": r.ok, "msg": r.motivo[:200], "estado": r.estado, "id": c.id},
    )
    row = await cur.fetchone()
    return int(row[0]) if row else c.sonda_falhas_seguidas


async def _episodios_ativos(conn, conexao_id: int) -> dict[str, datetime]:
    cur = await conn.execute(
        "SELECT tipo, criado_em FROM conexao_alerta "
        "WHERE conexao_id = %s AND resolvido_em IS NULL",
        (conexao_id,),
    )
    return {str(r[0]): r[1] for r in await cur.fetchall()}


def _json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str)


async def _sincronizar_episodios(
    conn,
    c: ConexaoMonitorada,
    achados: list[Achado],
    ativos: dict[str, datetime],
) -> tuple[list[tuple[str, dict[str, Any]]], list[tuple[str, dict[str, Any]]]]:
    """Mesma máquina de `ia_alertas.avaliar_alertas`, chave (tipo, conexao_id).
    Devolve (abertos agora, resolvidos que merecem aviso)."""
    abertos: list[tuple[str, dict[str, Any]]] = []
    resolvidos: list[tuple[str, dict[str, Any]]] = []
    tipos_agora = {a.tipo for a in achados}

    for a in achados:
        if a.tipo in ativos:
            await conn.execute(
                """
                UPDATE conexao_alerta
                   SET detalhe = %s::jsonb, atualizado_em = NOW()
                 WHERE conexao_id = %s AND tipo = %s AND resolvido_em IS NULL
                """,
                (_json(a.detalhe), c.id, a.tipo),
            )
            continue
        # Reabertura dentro do cooldown reativa a MESMA linha, sem re-notificar.
        cur = await conn.execute(
            """
            UPDATE conexao_alerta
               SET resolvido_em = NULL, detalhe = %s::jsonb, atualizado_em = NOW()
             WHERE id = (
               SELECT id FROM conexao_alerta
                WHERE conexao_id = %s AND tipo = %s
                  AND resolvido_em > NOW() - make_interval(hours => %s)
                ORDER BY resolvido_em DESC LIMIT 1
             )
            """,
            (_json(a.detalhe), c.id, a.tipo, COOLDOWN_HORAS),
        )
        if cur.rowcount:
            continue
        await conn.execute(
            """
            INSERT INTO conexao_alerta (empresa_id, conexao_id, tipo, detalhe)
            VALUES (%s, %s, %s, %s::jsonb)
            """,
            (c.empresa_id, c.id, a.tipo, _json(a.detalhe)),
        )
        abertos.append((a.tipo, a.detalhe))

    for tipo in set(ativos) - tipos_agora:
        cur = await conn.execute(
            """
            UPDATE conexao_alerta SET resolvido_em = NOW()
             WHERE conexao_id = %s AND tipo = %s AND resolvido_em IS NULL
            RETURNING notificado_em IS NOT NULL
                   AND criado_em < NOW() - make_interval(mins => %s),
                   criado_em
            """,
            (c.id, tipo, RESOLVE_NOTIFICA_MIN),
        )
        r = await cur.fetchone()
        if r and r[0]:
            resolvidos.append((tipo, {"criado_em": _iso(r[1])}))
    return abertos, resolvidos


async def _marcar_notificados(
    pool: AsyncConnectionPool,
    abertos: list[tuple[ConexaoMonitorada, str, dict[str, Any]]],
) -> None:
    async with pool.connection() as conn:
        for c, tipo, _ in abertos:
            await conn.execute(
                "UPDATE conexao_alerta SET notificado_em = NOW() "
                "WHERE conexao_id = %s AND tipo = %s AND resolvido_em IS NULL",
                (c.id, tipo),
            )


async def _flip_evolution(pool: AsyncConnectionPool, fora: bool) -> str | None:
    """Liga/desliga `evolution_indisponivel_desde`; devolve 'caiu'/'voltou'
    quando o estado mudou (um aviso de plataforma, não N linhas)."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT evolution_indisponivel_desde FROM saude_conexoes_estado WHERE id = 1"
        )
        row = await cur.fetchone()
        atual = row[0] if row else None
        if fora and atual is None:
            await conn.execute(
                "UPDATE saude_conexoes_estado SET evolution_indisponivel_desde = NOW() WHERE id = 1"
            )
            return "caiu"
        if not fora and atual is not None:
            await conn.execute(
                "UPDATE saude_conexoes_estado SET evolution_indisponivel_desde = NULL WHERE id = 1"
            )
            return "voltou"
    return None


# --- Sondas ------------------------------------------------------------------


async def _sondar_evolution(c: ConexaoMonitorada) -> ResultadoSonda | None:
    import httpx

    from whatsapp_langchain.integrations.evolution import admin as evo_admin
    from whatsapp_langchain.shared.config import settings

    if not settings.evolution_admin_enabled or not c.instance_name:
        return None
    t0 = time.monotonic()
    try:
        raw = await evo_admin.get_connection_state(c.instance_name)
    except evo_admin.EvolutionAdminError as exc:
        if exc.status_code == 404:
            return ResultadoSonda(
                ok=False,
                estado="error",
                responde=None,
                latencia_ms=None,
                motivo="instância não existe mais na Evolution",
            )
        return ResultadoSonda(
            ok=False,
            estado=None,
            responde=None,
            latencia_ms=None,
            motivo="Evolution sem resposta",
            plataforma_fora=True,
        )
    except (httpx.HTTPError, OSError, TimeoutError):
        return ResultadoSonda(
            ok=False,
            estado=None,
            responde=None,
            latencia_ms=None,
            motivo="Evolution sem resposta",
            plataforma_fora=True,
        )

    estado = evo_admin.normalize_state(raw)
    if estado != "open":
        motivo = (
            "Evolution informou conexão fechada"
            if estado == "disconnected"
            else f"Evolution informou {descrever_desconexao(None, estado)}"
        )
        return ResultadoSonda(
            ok=False, estado=estado, responde=None, latencia_ms=None, motivo=motivo
        )

    digitos = re.sub(r"\D", "", c.from_number or "")
    if not digitos or (c.from_number or "").startswith("evolution:"):
        return ResultadoSonda(
            ok=True,
            estado="open",
            responde=None,
            latencia_ms=None,
            motivo="conexão aberta (número ainda não vinculado)",
        )
    try:
        await asyncio.wait_for(
            evo_admin.fetch_profile_picture(
                c.instance_name, digitos, timeout=SONDA_TIMEOUT_S
            ),
            SONDA_TIMEOUT_S + 1,
        )
    except (TimeoutError, httpx.TimeoutException):
        return ResultadoSonda(
            ok=False,
            estado="open",
            responde=False,
            latencia_ms=None,
            motivo=f"sem resposta do WhatsApp em {SONDA_TIMEOUT_S:.0f} s",
        )
    except evo_admin.EvolutionAdminError as exc:
        return ResultadoSonda(
            ok=False,
            estado="open",
            responde=False,
            latencia_ms=None,
            motivo=f"WhatsApp respondeu erro {exc.status_code}",
        )
    except (httpx.HTTPError, OSError):
        return ResultadoSonda(
            ok=False,
            estado="open",
            responde=False,
            latencia_ms=None,
            motivo="erro ao consultar o WhatsApp",
        )
    return ResultadoSonda(
        ok=True,
        estado="open",
        responde=True,
        latencia_ms=int((time.monotonic() - t0) * 1000),
        motivo="conexão responde",
    )


async def _sondar_waba(c: ConexaoMonitorada) -> ResultadoSonda | None:
    """Só o acesso da Meta (token) — o WABA não tem socket para ficar zumbi."""
    import httpx

    from whatsapp_langchain.shared.conexao import get_credentials_decrypted
    from whatsapp_langchain.shared.config import settings
    from whatsapp_langchain.shared.db import get_pool

    try:
        creds = await get_credentials_decrypted(await get_pool(), c.id) or {}
    except Exception:  # noqa: BLE001
        creds = {}
    token = creds.get("access_token")
    phone_id = creds.get("phone_id")
    if not token or not phone_id:
        return None
    url = f"https://graph.facebook.com/{settings.waba_graph_api_version}/{phone_id}"
    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
    except (httpx.HTTPError, OSError):
        return ResultadoSonda(
            ok=False,
            estado=None,
            responde=None,
            latencia_ms=None,
            motivo="Meta sem resposta",
        )
    if resp.status_code == 200:
        return ResultadoSonda(
            ok=True,
            estado="open",
            responde=True,
            latencia_ms=int((time.monotonic() - t0) * 1000),
            motivo="acesso da Meta válido",
        )
    if resp.status_code in (401, 403, 190):
        motivo = "acesso da Meta expirado ou revogado"
    else:
        motivo = f"Meta respondeu {resp.status_code}"
    return ResultadoSonda(
        ok=False, estado="error", responde=False, latencia_ms=None, motivo=motivo
    )


async def _sondar_padrao(c: ConexaoMonitorada) -> ResultadoSonda | None:
    if c.provider == "evolution":
        return await _sondar_evolution(c)
    if c.provider == "waba":
        return await _sondar_waba(c)
    return None


async def _notificar_padrao(titulo: str, linhas: list[str]) -> bool:
    from whatsapp_langchain.shared.ia_alertas import notificar_plataforma

    return await notificar_plataforma(titulo, linhas)


# --- O tick -------------------------------------------------------------------


async def _avaliar_uma(
    pool: AsyncConnectionPool,
    c: ConexaoMonitorada,
    now_utc: datetime,
    sondar: Sondar,
    enviar_eco: EnviarEco,
) -> tuple[list[tuple[str, dict[str, Any]]], list[tuple[str, dict[str, Any]]], bool]:
    """Sonda + régua de silêncio + eco + decisão + episódios de UMA conexão.
    Devolve (abertos, resolvidos notificáveis, evolution fora)."""
    sonda: ResultadoSonda | None = None
    plataforma_fora = False
    if monitoravel(c) and sonda_devida(c, now_utc):
        try:
            sonda = await sondar(c)
        except Exception as exc:  # noqa: BLE001 — sonda quebrada não pode calar o resto
            logger.warning("saude_sonda_erro", conexao_id=c.id, error=str(exc))
            sonda = None
        if sonda is not None and sonda.plataforma_fora:
            plataforma_fora = True
            sonda = None

    async with pool.connection() as conn:
        falhas = await _registrar_sonda(conn, c, sonda)

        estado, codigo, desde = c.connection_state, c.desconexao_codigo, c.desconexao_em
        if sonda is not None and sonda.ok:
            estado, codigo, desde = "open", None, None
        elif sonda is not None:
            desde = desde or now_utc
            if sonda.estado in ("disconnected", "error"):
                estado = sonda.estado

        silencio: Silencio | None = None
        if monitoravel(c) and c.ultimo_inbound_em is not None:
            inicio = c.ultimo_inbound_em - timedelta(days=BASELINE_DIAS)
            baseline, dias = await carregar_baseline(
                conn, c.id, c.tz, inicio, c.ultimo_inbound_em
            )
            gaps = await carregar_gaps_ativos(
                conn, c.id, c.tz, baseline, inicio, c.ultimo_inbound_em
            )
            silencio = calcular_silencio(
                baseline,
                dias,
                c.ultimo_inbound_em,
                now_utc,
                c.tz,
                calcular_limite_silencio(gaps, dias),
            )

        # Eco (mig 198): silêncio acima do normal não é alerta, é a pergunta.
        eco_falhas = c.eco_falhas_seguidas
        if c.eco_pendente_id and c.ultimo_eco_em and c.eco_enviado_em:
            if c.ultimo_eco_em >= c.eco_enviado_em:
                eco_falhas = 0
        acao = (
            decidir_eco(c, silencio, sonda.ok if sonda else None, now_utc)
            if monitoravel(c)
            else "nada"
        )
        if acao == "falhou":
            eco_falhas = await _registrar_eco_falhou(conn, c)
            logger.warning(
                "saude_eco_sem_retorno",
                conexao_id=c.id,
                empresa_id=c.empresa_id,
                falhas=eco_falhas,
            )
        elif acao == "enviar":
            try:
                key_id = await enviar_eco(c)
            except Exception as exc:  # noqa: BLE001 — eco que não sai conta como falha
                logger.warning(
                    "saude_eco_envio_falhou", conexao_id=c.id, error=str(exc)
                )
                key_id = None
            if key_id:
                await _registrar_eco_enviado(conn, c, key_id, now_utc)
                logger.info(
                    "saude_eco_enviado",
                    conexao_id=c.id,
                    empresa_id=c.empresa_id,
                    motivo="reconexao" if c.eco_solicitado_em else "silencio",
                    quieto_h=round(silencio.horas, 1) if silencio else None,
                    limite_h=silencio.limite_normal_h if silencio else None,
                )
            else:
                eco_falhas = await _registrar_eco_falhou(conn, c)

        ativos = await _episodios_ativos(conn, c.id)
        sinais = SinaisConexao(
            connection_state=estado,
            desconexao_codigo=codigo,
            desconexao_em=desde,
            sonda=sonda,
            sonda_falhas_seguidas=falhas,
            silencio=silencio,
            ultimo_inbound_em=c.ultimo_inbound_em,
            eco_falhas_seguidas=eco_falhas,
        )
        achados = avaliar_conexao(sinais) if monitoravel(c) else []
        abertos, resolvidos = await _sincronizar_episodios(conn, c, achados, ativos)
    return abertos, resolvidos, plataforma_fora


async def avaliar_saude(
    pool: AsyncConnectionPool,
    *,
    now_utc: datetime | None = None,
    sondar: Sondar | None = None,
    notificar: Notificar | None = None,
    enviar_eco: EnviarEco | None = None,
    forcar: bool = False,
) -> dict[str, int]:
    """Um tick completo. `forcar=True` pula o claim (testes). Retorna contagens."""
    from whatsapp_langchain.shared.rls_context import empresa_scope

    now = now_utc or datetime.now(UTC)
    sondar = sondar or _sondar_padrao
    notificar = notificar or _notificar_padrao
    enviar_eco = enviar_eco or _sondar_padrao_eco
    contagem = {"conexoes": 0, "abertos": 0, "resolvidos": 0, "erros": 0, "pulado": 0}

    with empresa_scope(None, bypass=True):
        marca = await _ler_marca(pool) if forcar else await _claim_tick(pool)
        if marca is None:
            contagem["pulado"] = 1
            return contagem
        corte = now - timedelta(minutes=1)
        try:
            async with pool.connection() as conn:
                await _acumular_atividade(conn, marca, corte)
            conexoes = await _listar_monitoradas(pool)
            contagem["conexoes"] = len(conexoes)

            sem = asyncio.Semaphore(4)

            async def _uma(c: ConexaoMonitorada):
                async with sem:
                    return await asyncio.wait_for(
                        _avaliar_uma(pool, c, now, sondar, enviar_eco),
                        timeout=SONDA_TIMEOUT_S * 2 + 10,
                    )

            resultados = await asyncio.gather(
                *(_uma(c) for c in conexoes), return_exceptions=True
            )

            abertos: list[tuple[ConexaoMonitorada, str, dict[str, Any]]] = []
            resolvidos: list[tuple[ConexaoMonitorada, str, dict[str, Any]]] = []
            evo_total = evo_fora = 0
            for c, r in zip(conexoes, resultados, strict=True):
                if isinstance(r, BaseException):
                    contagem["erros"] += 1
                    logger.warning("saude_conexao_erro", conexao_id=c.id, error=str(r))
                    continue
                ab, res, fora = r
                abertos.extend((c, t, d) for t, d in ab)
                resolvidos.extend((c, t, d) for t, d in res)
                if c.provider == "evolution" and monitoravel(c):
                    evo_total += 1
                    evo_fora += int(fora)

            if evo_total:
                flip = await _flip_evolution(pool, evo_fora == evo_total)
                if flip == "caiu":
                    await notificar(
                        "⚠️ Evolution sem resposta",
                        [
                            f"nenhuma das {evo_total} conexões pôde ser verificada — a Evolution não respondeu"
                        ],
                    )
                elif flip == "voltou":
                    await notificar(
                        "✅ Evolution respondendo",
                        ["as verificações de conexão voltaram"],
                    )

            if abertos:
                titulo = f"🔴 Clientes — {len({c.id for c, _, _ in abertos})} conexão(ões) com problema"
                ok = await notificar(titulo, montar_mensagem(abertos, now_utc=now))
                if ok:
                    await _marcar_notificados(pool, abertos)
            if resolvidos:
                titulo = f"✅ Clientes — {len({c.id for c, _, _ in resolvidos})} conexão(ões) normalizada(s)"
                await notificar(
                    titulo, montar_mensagem(resolvidos, resolvido=True, now_utc=now)
                )

            contagem["abertos"] = len(abertos)
            contagem["resolvidos"] = len(resolvidos)
            await _fechar_tick(pool, corte, ok=True)
        except Exception as exc:
            await _fechar_tick(pool, marca, ok=False, erro=str(exc))
            raise
    return contagem


# --- Leitura para o painel -----------------------------------------------------


def _alerta_dict(r) -> dict[str, Any]:
    return {
        "id": int(r[0]),
        "tipo": r[1],
        "detalhe": r[2],
        "criado_em": _iso(r[3]),
        "notificado_em": _iso(r[4]),
        "resolvido_em": _iso(r[5]),
    }


async def montar_painel(
    pool: AsyncConnectionPool, now_utc: datetime | None = None
) -> dict[str, Any]:
    """Tudo que a tela "Saúde dos clientes" precisa (chamador em bypass de RLS)."""
    now = now_utc or datetime.now(UTC)
    conexoes = await _listar_monitoradas(pool)
    async with pool.connection() as conn:
        cur = await conn.execute("SELECT * FROM saude_conexoes_estado WHERE id = 1")
        est = await cur.fetchone()
        cols = [d.name for d in cur.description or []]
        estado = dict(zip(cols, est, strict=False)) if est else {}
        for k, v in list(estado.items()):
            if isinstance(v, datetime):
                estado[k] = v.isoformat()
        estado.pop("id", None)

        cur = await conn.execute(
            "SELECT conexao_id, sum(recebidas) FROM conexao_atividade "
            "WHERE hora >= %s GROUP BY conexao_id",
            (now - timedelta(hours=24),),
        )
        recebidas = {int(r[0]): int(r[1]) for r in await cur.fetchall()}

        cur = await conn.execute(
            """
            SELECT id, tipo, detalhe, criado_em, notificado_em, resolvido_em, conexao_id
              FROM conexao_alerta WHERE resolvido_em IS NULL ORDER BY criado_em DESC
            """
        )
        ativos: dict[int, list[dict[str, Any]]] = {}
        for r in await cur.fetchall():
            ativos.setdefault(int(r[6]), []).append(_alerta_dict(r))

        cur = await conn.execute(
            """
            SELECT a.id, a.tipo, a.detalhe, a.criado_em, a.notificado_em, a.resolvido_em,
                   a.conexao_id, a.empresa_id, e.nome, c.display_name, c.from_number
              FROM conexao_alerta a
              JOIN empresa e ON e.id = a.empresa_id
              JOIN conexao c ON c.id = a.conexao_id
             WHERE a.resolvido_em >= NOW() - interval '48 hours'
             ORDER BY a.resolvido_em DESC LIMIT 50
            """
        )
        resolvidos = [
            {
                **_alerta_dict(r),
                "conexao_id": int(r[6]),
                "empresa_id": int(r[7]),
                "empresa_nome": r[8],
                "display_name": r[9],
                "from_number": r[10],
            }
            for r in await cur.fetchall()
        ]

        items: list[dict[str, Any]] = []
        for c in conexoes:
            esperadas = 0.0
            silencio: Silencio | None = None
            if c.ultimo_inbound_em is not None:
                baseline, _dias = await carregar_baseline(
                    conn, c.id, c.tz, now - timedelta(days=BASELINE_DIAS), now
                )
                esperadas = esperadas_na_janela(
                    baseline, now - timedelta(hours=24), now, c.tz
                )
                inicio = c.ultimo_inbound_em - timedelta(days=BASELINE_DIAS)
                base_regua, dias = await carregar_baseline(
                    conn, c.id, c.tz, inicio, c.ultimo_inbound_em
                )
                gaps = await carregar_gaps_ativos(
                    conn, c.id, c.tz, base_regua, inicio, c.ultimo_inbound_em
                )
                silencio = calcular_silencio(
                    base_regua,
                    dias,
                    c.ultimo_inbound_em,
                    now,
                    c.tz,
                    calcular_limite_silencio(gaps, dias),
                )
            eco_pendente = bool(c.eco_pendente_id) and not (
                c.ultimo_eco_em
                and c.eco_enviado_em
                and c.ultimo_eco_em >= c.eco_enviado_em
            )
            items.append(
                {
                    "conexao_id": c.id,
                    "empresa_id": c.empresa_id,
                    "empresa_nome": c.empresa_nome,
                    "display_name": c.display_name,
                    "from_number": c.from_number,
                    "provider": c.provider,
                    "tipo_atendimento": c.tipo_atendimento,
                    "connection_state": c.connection_state,
                    "state_message": c.state_message,
                    "monitorada": monitoravel(c),
                    "ultimo_health_check_at": _iso(c.ultimo_health_check_at),
                    "ultimo_health_check_ok": c.ultimo_health_check_ok,
                    "sonda_falhas_seguidas": c.sonda_falhas_seguidas,
                    "ultimo_inbound_em": _iso(c.ultimo_inbound_em),
                    "recebidas_24h": recebidas.get(c.id, 0),
                    "esperadas_24h": round(esperadas, 1),
                    "quieto_ha_h": round(silencio.horas, 2) if silencio else None,
                    "limite_normal_h": silencio.limite_normal_h if silencio else None,
                    "hora_ativa": silencio.hora_ativa if silencio else None,
                    "acima_do_normal": bool(silencio and silencio.acima_do_normal),
                    "eco": {
                        "ativo": c.eco_ativo and c.provider == "evolution",
                        "ultimo_em": _iso(c.ultimo_eco_em),
                        "pendente_desde": _iso(c.eco_enviado_em)
                        if eco_pendente
                        else None,
                        "falhas": c.eco_falhas_seguidas,
                    },
                    "ultimo_ack_em": _iso(c.ultimo_ack_em),
                    "alertas": ativos.get(c.id, []),
                }
            )
    items.sort(
        key=lambda i: (0 if i["alertas"] else 1, i["empresa_id"], i["conexao_id"])
    )
    return {"estado": estado, "items": items, "resolvidos_recentes": resolvidos}


async def banner_da_empresa(
    pool: AsyncConnectionPool, empresa_id: int
) -> dict[str, Any]:
    """Conexões da empresa que o cliente precisa reconectar (chamador no escopo da empresa)."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT c.id, c.display_name, c.from_number, c.connection_state, c.state_message,
                   c.desconexao_codigo, c.desconexao_em, a.detalhe, a.criado_em
              FROM conexao c
              LEFT JOIN conexao_alerta a
                     ON a.conexao_id = c.id AND a.tipo = 'conexao_caida' AND a.resolvido_em IS NULL
             WHERE c.empresa_id = %s AND c.status = 'active'
               AND (a.id IS NOT NULL OR c.connection_state IN ('disconnected', 'error'))
             ORDER BY c.id
            """,
            (empresa_id,),
        )
        rows = await cur.fetchall()
    caidas = []
    for r in rows:
        detalhe = r[7] or {}
        motivo = detalhe.get("motivo") or descrever_desconexao(
            r[5], r[3] or "disconnected"
        )
        caidas.append(
            {
                "conexao_id": int(r[0]),
                "display_name": r[1],
                "from_number": r[2],
                "motivo": motivo,
                "desde": _iso(r[6] or r[8]),
            }
        )
    return {"caidas": caidas}
