"""Alertas de degradação de IA (módulo Saúde de IA, F4 — mig 180).

Detecção DETERMINÍSTICA, sem LLM (mesmo racional do producao_checks.py):
`avaliar_condicoes` é função pura — recebe números, devolve achados — e por
isso tem teste de unidade com limiar visível. O tick do worker
(`run_openrouter_sync`) chama `avaliar_alertas` depois da coleta de métricas:
abre/atualiza/resolve episódios em `ia_alerta` e notifica pelos três canais
da decisão do dono (2026-08-25): WhatsApp da empresa 1 (mesmo caminho do
resumo diário), Telegram (envs opcionais) e o banner do painel (rota
`GET /api/openrouter/alertas`).

Anti-flap: (tipo, modelo_slug) ativo é único; reabertura dentro do cooldown
de 6h reativa a MESMA linha sem nova notificação; resolução só é notificada
quando o episódio foi notificado e viveu ao menos 30 minutos.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import httpx
import structlog

from whatsapp_langchain.shared.config import settings

if TYPE_CHECKING:
    from psycopg import AsyncConnection
    from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.llm import QUANTIZACOES_ACEITAS

logger = structlog.get_logger()

# --- Limiares (visíveis de propósito — são o contrato do alerta) ---

#: Melhor uptime_30m entre os endpoints do modelo. Abaixo disto nem o melhor
#: caminho do roteador está saudável.
UPTIME_MINIMO = 97.0

#: Latência p50 atual acima deste fator sobre o baseline 7d = degradação.
LATENCIA_FATOR_MAX = 2.0

#: Throughput p50 atual abaixo desta fração do baseline 7d = degradação.
THROUGHPUT_FATOR_MIN = 0.5

#: Taxa de erro da NOSSA operação (ia_execucao, última hora)...
ERRO_PROPRIO_PCT_MAX = 20.0
#: ...mas só com volume mínimo — 1 erro em 2 chamadas não é sinal.
ERRO_PROPRIO_MIN_CHAMADAS = 5

#: Reabertura dentro deste prazo após resolver NÃO re-notifica (flap).
COOLDOWN_HORAS = 6

#: Resolução só é notificada se o episódio viveu ao menos isto.
RESOLVE_NOTIFICA_MIN = 30

TIPOS_LABEL = {
    "uptime": "Uptime baixo",
    "latencia": "Latência alta",
    "throughput": "Throughput baixo",
    "erros_proprios": "Erros na nossa operação",
    "modelo_sumiu": "Modelo sem endpoints",
    # 21/09/2026 — disponibilidade de verdade (sonda real + piso de quantização)
    "modelo_indisponivel": "Modelo indisponível",
    "sem_provedor_permitido": "Modelo só com provedores abaixo do piso",
    "agente_falhando": "Agente falhando em série",
}
# Tipos que tiram o modelo de circulação: o seletor mostra "indisponível" e
# o worker troca pelo padrão (decisão do dono, 21/09/2026).
TIPOS_INDISPONIVEL = frozenset({"modelo_indisponivel", "modelo_sumiu"})
# Agente falhando em série: N mensagens `failed` na janela.
AGENTE_FALHAS_MIN = 3
AGENTE_FALHAS_JANELA_MIN = 30
CHAVE_AGENTE = "agente:"


def avaliar_condicoes(
    snapshot: dict[str, Any] | None,
    baseline: dict[str, Any],
    operacao: dict[str, Any],
    sonda: Any | None = None,
) -> list[dict[str, Any]]:
    """Função PURA: devolve as condições de alerta violadas por um modelo.

    - `snapshot`: agregado do último tick de openrouter_endpoint_metrica —
      {uptime_30m (melhor), latencia_p50 (menor), throughput_p50 (maior),
      endpoints (count), endpoints_permitidos (count no piso de quantização)}
      — ou None quando não houve coleta na janela.
    - `baseline`: 7 dias — {latencia_p50, throughput_p50, tinha_endpoints}.
    - `operacao`: ia_execucao 1h — {chamadas, erros}.
    - `sonda`: `llm.SondaModelo` da chamada real (None = não sondado).
      Transitório não muda nada; `inexistente` abre `modelo_indisponivel`;
      `sem_provedor_permitido` abre o tipo homônimo.
    """
    achados: list[dict[str, Any]] = []

    if sonda is not None and not sonda.transitorio:
        if sonda.inexistente:
            achados.append(
                {
                    "tipo": "modelo_indisponivel",
                    "detalhe": {
                        "motivo": sonda.motivo,
                        "codigo": sonda.codigo,
                        "origem": "sonda",
                    },
                }
            )
        elif sonda.sem_provedor_permitido:
            achados.append(
                {
                    "tipo": "sem_provedor_permitido",
                    "detalhe": {"motivo": sonda.motivo, "origem": "sonda"},
                }
            )
    if (
        snapshot is not None
        and snapshot.get("endpoints")
        and snapshot.get("endpoints_permitidos") == 0
        and not any(a["tipo"] == "sem_provedor_permitido" for a in achados)
        and not (sonda is not None and sonda.ok)
    ):
        achados.append(
            {
                "tipo": "sem_provedor_permitido",
                "detalhe": {
                    "motivo": "nenhum endpoint fp8/bf16/fp16/fp32 no catálogo",
                    "origem": "catalogo",
                    "endpoints": snapshot.get("endpoints"),
                },
            }
        )

    if snapshot is None or not snapshot.get("endpoints"):
        # Só é "sumiu" se o modelo EXISTIA na série — modelo recém-adicionado
        # sem histórico não pode acordar ninguém.
        if baseline.get("tinha_endpoints"):
            achados.append({"tipo": "modelo_sumiu", "detalhe": {}})
        snapshot = None

    if snapshot is not None:
        uptime = snapshot.get("uptime_30m")
        if uptime is not None and uptime < UPTIME_MINIMO:
            achados.append(
                {
                    "tipo": "uptime",
                    "detalhe": {"valor": uptime, "limiar": UPTIME_MINIMO},
                }
            )

        lat = snapshot.get("latencia_p50")
        lat_base = baseline.get("latencia_p50")
        if lat is not None and lat_base and lat > LATENCIA_FATOR_MAX * lat_base:
            achados.append(
                {
                    "tipo": "latencia",
                    "detalhe": {
                        "valor_ms": lat,
                        "baseline_ms": lat_base,
                        "fator": round(lat / lat_base, 2),
                    },
                }
            )

        thr = snapshot.get("throughput_p50")
        thr_base = baseline.get("throughput_p50")
        if thr is not None and thr_base and thr < THROUGHPUT_FATOR_MIN * thr_base:
            achados.append(
                {
                    "tipo": "throughput",
                    "detalhe": {
                        "valor": thr,
                        "baseline": thr_base,
                        "fracao": round(thr / thr_base, 2),
                    },
                }
            )

    chamadas = int(operacao.get("chamadas") or 0)
    erros = int(operacao.get("erros") or 0)
    if chamadas >= ERRO_PROPRIO_MIN_CHAMADAS:
        pct = erros * 100 / chamadas
        if pct > ERRO_PROPRIO_PCT_MAX:
            achados.append(
                {
                    "tipo": "erros_proprios",
                    "detalhe": {
                        "erros": erros,
                        "chamadas": chamadas,
                        "pct": round(pct, 1),
                        "limiar_pct": ERRO_PROPRIO_PCT_MAX,
                    },
                }
            )
    return achados


def formatar_alerta(
    slug: str, tipo: str, detalhe: dict[str, Any], usos: list[str] | None = None
) -> str:
    """Uma linha legível pro WhatsApp/Telegram — sem jargão de coluna.
    `usos` = quem usa o modelo ("agente X · Empresa (id)") — vai no fim."""
    label = TIPOS_LABEL.get(tipo, tipo)
    sufixo = f" · usado por: {', '.join(usos)}" if usos else ""
    if tipo == "modelo_indisponivel":
        return (
            f"{label}: {slug} — {detalhe.get('motivo', 'sem resposta')}; "
            f"os agentes com ele passam a responder pelo modelo padrão até você trocar{sufixo}"
        )
    if tipo == "sem_provedor_permitido":
        return (
            f"{label}: {slug} — {detalhe.get('motivo', '')}; "
            f"as respostas seguem, com qualidade menor — troque o modelo do agente{sufixo}"
        )
    if tipo == "agente_falhando":
        return (
            f"{label}: agente {detalhe.get('agente')} · {detalhe.get('empresa')} "
            f"({detalhe.get('empresa_id')}) — {detalhe.get('falhas')} mensagens falharam "
            f"nos últimos {AGENTE_FALHAS_JANELA_MIN} min ({detalhe.get('erro', 'erro não informado')})"
        )
    if tipo == "uptime":
        return f"{label}: {slug} em {detalhe.get('valor')}% (piso {UPTIME_MINIMO}%)"
    if tipo == "latencia":
        return (
            f"{label}: {slug} com p50 {round(detalhe.get('valor_ms') or 0)}ms — "
            f"{detalhe.get('fator')}× o normal dos últimos 7 dias"
        )
    if tipo == "throughput":
        return (
            f"{label}: {slug} gerando {detalhe.get('valor')} tok/s — "
            f"{round((detalhe.get('fracao') or 0) * 100)}% do normal"
        )
    if tipo == "erros_proprios":
        return (
            f"{label}: {slug} falhou {detalhe.get('erros')} de "
            f"{detalhe.get('chamadas')} chamadas na última hora "
            f"({detalhe.get('pct')}%)"
        )
    if tipo == "modelo_sumiu":
        return f"{label}: {slug} não aparece mais nos endpoints do OpenRouter{sufixo}"
    return f"{label}: {slug}{sufixo}"


# ---------------------------------------------------------------------------
# Coleta dos números (DB) — janelas documentadas em cada query.
# ---------------------------------------------------------------------------


async def _snapshot_modelo(conn: AsyncConnection, slug: str) -> dict | None:
    """Último snapshot (2h) agregado: melhor uptime, menor p50, maior tok/s.

    O roteador do OpenRouter escolhe o melhor caminho — por isso o agregado
    otimista: alerta só quando nem o melhor endpoint está bom.
    """
    cur = await conn.execute(
        """
        SELECT max(uptime_30m),
               min((latencia->>'p50')::numeric),
               max((throughput->>'p50')::numeric),
               count(*),
               count(*) FILTER (WHERE quantization = ANY(%s))
          FROM (
            SELECT DISTINCT ON (provider_tag)
                   uptime_30m, latencia, throughput, quantization
              FROM openrouter_endpoint_metrica
             WHERE modelo_slug = %s
               AND coletado_em > NOW() - interval '2 hours'
             ORDER BY provider_tag, coletado_em DESC
          ) ult
        """,
        (list(QUANTIZACOES_ACEITAS), slug),
    )
    r = await cur.fetchone()
    if not r or not r[3]:
        return None
    from whatsapp_langchain.shared.llm import provider_preferences

    # Modelo proprietário não leva piso: todo endpoint é "permitido".
    permitidos = int(r[4]) if provider_preferences(slug) is not None else int(r[3])
    return {
        "uptime_30m": float(r[0]) if r[0] is not None else None,
        "latencia_p50": float(r[1]) if r[1] is not None else None,
        "throughput_p50": float(r[2]) if r[2] is not None else None,
        "endpoints": int(r[3]),
        "endpoints_permitidos": permitidos,
    }


async def _baseline_modelo(conn: AsyncConnection, slug: str) -> dict:
    """Baseline 7d (excluindo as últimas 2h, senão a degradação atual
    contamina a régua): mediana dos p50 da série."""
    cur = await conn.execute(
        """
        SELECT percentile_cont(0.5)
                 WITHIN GROUP (ORDER BY (latencia->>'p50')::numeric),
               percentile_cont(0.5)
                 WITHIN GROUP (ORDER BY (throughput->>'p50')::numeric),
               count(*)
          FROM openrouter_endpoint_metrica
         WHERE modelo_slug = %s
           AND coletado_em BETWEEN NOW() - interval '7 days'
                               AND NOW() - interval '2 hours'
        """,
        (slug,),
    )
    r = await cur.fetchone()
    return {
        "latencia_p50": float(r[0]) if r and r[0] is not None else None,
        "throughput_p50": float(r[1]) if r and r[1] is not None else None,
        "tinha_endpoints": bool(r and r[2]),
    }


async def _operacao_modelo(conn: AsyncConnection, slug: str) -> dict:
    """Nossa operação (ia_execucao, última hora) — plataforma inteira."""
    provedor, _, nome = slug.partition("/")
    cur = await conn.execute(
        """
        SELECT count(*), count(*) FILTER (WHERE status <> 'success')
          FROM ia_execucao
         WHERE modelo_provedor = %s AND modelo_nome = %s
           AND created_at > NOW() - interval '1 hour'
        """,
        (provedor, nome),
    )
    r = await cur.fetchone()
    return {"chamadas": int(r[0]) if r else 0, "erros": int(r[1]) if r else 0}


# ---------------------------------------------------------------------------
# Máquina de estado dos episódios + notificação.
# ---------------------------------------------------------------------------


async def _sincronizar_episodios(
    conn: AsyncConnection, chave: str, achados: list[dict[str, Any]]
) -> tuple[list[tuple[str, str, dict]], list[tuple[str, str]]]:
    """Máquina de estado de UMA chave (modelo ou `agente:<empresa>:<slug>`):
    dedup do episódio ativo, reabertura dentro do cooldown sem re-notificar,
    auto-resolve com aviso só se foi notificado e viveu ≥ 30 min.
    Devolve (abertos, resolvidos notificáveis)."""
    abertos: list[tuple[str, str, dict]] = []
    resolvidos: list[tuple[str, str]] = []
    tipos_agora = {a["tipo"] for a in achados}
    cur = await conn.execute(
        "SELECT tipo FROM ia_alerta WHERE modelo_slug = %s AND resolvido_em IS NULL",
        (chave,),
    )
    ativos = {str(r[0]) for r in await cur.fetchall()}
    for a in achados:
        if a["tipo"] in ativos:
            await conn.execute(
                """
                UPDATE ia_alerta
                   SET detalhe = %s::jsonb, atualizado_em = NOW()
                 WHERE modelo_slug = %s AND tipo = %s AND resolvido_em IS NULL
                """,
                (_json(a["detalhe"]), chave, a["tipo"]),
            )
            continue
        cur = await conn.execute(
            """
            UPDATE ia_alerta
               SET resolvido_em = NULL, detalhe = %s::jsonb, atualizado_em = NOW()
             WHERE id = (
               SELECT id FROM ia_alerta
                WHERE modelo_slug = %s AND tipo = %s
                  AND resolvido_em > NOW() - make_interval(hours => %s)
                ORDER BY resolvido_em DESC LIMIT 1
             )
            """,
            (_json(a["detalhe"]), chave, a["tipo"], COOLDOWN_HORAS),
        )
        if cur.rowcount:
            continue
        # As 2 réplicas do worker avaliam no mesmo instante: quem perde a
        # corrida no índice parcial único não abre de novo nem re-notifica.
        cur = await conn.execute(
            """
            INSERT INTO ia_alerta (tipo, modelo_slug, detalhe) VALUES (%s, %s, %s::jsonb)
            ON CONFLICT (tipo, modelo_slug) WHERE resolvido_em IS NULL DO NOTHING
            """,
            (a["tipo"], chave, _json(a["detalhe"])),
        )
        if cur.rowcount:
            abertos.append((chave, a["tipo"], a["detalhe"]))
    for tipo in ativos - tipos_agora:
        cur = await conn.execute(
            """
            UPDATE ia_alerta SET resolvido_em = NOW()
             WHERE modelo_slug = %s AND tipo = %s AND resolvido_em IS NULL
            RETURNING notificado_em IS NOT NULL
                   AND criado_em < NOW() - make_interval(mins => %s)
            """,
            (chave, tipo, RESOLVE_NOTIFICA_MIN),
        )
        r = await cur.fetchone()
        if r and r[0]:
            resolvidos.append((chave, tipo))
    return abertos, resolvidos


async def _usos_por_modelo(conn: AsyncConnection) -> dict[str, list[str]]:
    """Quem usa cada modelo (agentes ativos) — mesma regra do runtime:
    `provedor/nome` quando os dois existem, senão a coluna legada."""
    cur = await conn.execute(
        """
        SELECT CASE WHEN COALESCE(a.modelo_provedor, '') <> '' AND COALESCE(a.modelo_nome, '') <> ''
                    THEN a.modelo_provedor || '/' || a.modelo_nome ELSE a.modelo END,
               a.slug, e.id, e.nome
          FROM agente_ia a JOIN empresa e ON e.id = a.empresa_id
         WHERE a.ativo AND e.status = 'active'
        """
    )
    usos: dict[str, list[str]] = {}
    for slug, agente, eid, enome in await cur.fetchall():
        if slug:
            usos.setdefault(str(slug), []).append(f"agente {agente} · {enome} ({eid})")
    return usos


async def _agentes_falhando(conn: AsyncConnection) -> list[dict[str, Any]]:
    """Mensagens `failed` por (empresa, agente) na janela — rede de segurança
    independente da causa (modelo, chave, provedor)."""
    cur = await conn.execute(
        """
        SELECT q.empresa_id, q.agent_id, count(*), max(q.error), e.nome
          FROM message_queue q JOIN empresa e ON e.id = q.empresa_id
         WHERE q.status = 'failed'
           AND q.updated_at > NOW() - make_interval(mins => %s)
         GROUP BY q.empresa_id, q.agent_id, e.nome
        HAVING count(*) >= %s
        """,
        (AGENTE_FALHAS_JANELA_MIN, AGENTE_FALHAS_MIN),
    )
    return [
        {
            "chave": f"{CHAVE_AGENTE}{r[0]}:{r[1]}",
            "empresa_id": int(r[0]),
            "agente": r[1],
            "falhas": int(r[2]),
            "erro": (r[3] or "")[:120],
            "empresa": r[4],
        }
        for r in await cur.fetchall()
    ]


async def _sondar_padrao(slug: str):
    from whatsapp_langchain.shared.llm import sondar_modelo

    return await sondar_modelo(slug)


async def avaliar_alertas(
    pool: AsyncConnectionPool,
    *,
    sondar: Callable[[str], Awaitable[Any]] | None = None,
) -> dict[str, int]:
    """Um passe completo: avalia os modelos EM USO (métricas + sonda real),
    os agentes falhando em série, abre/atualiza/resolve episódios e notifica
    os novos. Retorna contagens (pro log do tick)."""
    from whatsapp_langchain.shared.openrouter_catalogo import modelos_em_uso
    from whatsapp_langchain.shared.rls_context import empresa_scope

    sondar_fn: Callable[[str], Awaitable[Any]] = sondar or _sondar_padrao
    # Só os em uso de verdade (settings + agentes ativos) — alertar sobre
    # modelo curado que ninguém usa é ruído.
    slugs = await modelos_em_uso(pool, incluir_curados=False)

    abertos: list[tuple[str, str, dict]] = []
    resolvidos_notificaveis: list[tuple[str, str]] = []
    usos: dict[str, list[str]] = {}
    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            usos = await _usos_por_modelo(conn)
            for slug in slugs:
                snapshot = await _snapshot_modelo(conn, slug)
                baseline = await _baseline_modelo(conn, slug)
                operacao = await _operacao_modelo(conn, slug)
                try:
                    # O modelo de voz ("chat que fala") recusa chamada de texto
                    # puro: sondá-lo deu falso "não existe" em produção (21/09).
                    sonda = (
                        None if slug == settings.tts_model else await sondar_fn(slug)
                    )
                except Exception as exc:  # noqa: BLE001 — sonda quebrada não cala o resto
                    logger.warning(
                        "ia_sonda_modelo_erro", slug=slug, error=str(exc)[:200]
                    )
                    sonda = None
                achados = avaliar_condicoes(snapshot, baseline, operacao, sonda)
                ab, res = await _sincronizar_episodios(conn, slug, achados)
                abertos += ab
                resolvidos_notificaveis += res
            # Agentes falhando em série: chave própria, mesma máquina.
            falhando = {f["chave"]: f for f in await _agentes_falhando(conn)}
            cur = await conn.execute(
                "SELECT DISTINCT modelo_slug FROM ia_alerta "
                "WHERE tipo = 'agente_falhando' AND resolvido_em IS NULL"
            )
            chaves = set(falhando) | {str(r[0]) for r in await cur.fetchall()}
            for chave in sorted(chaves):
                f = falhando.get(chave)
                achados = (
                    [
                        {
                            "tipo": "agente_falhando",
                            "detalhe": {k: v for k, v in f.items() if k != "chave"},
                        }
                    ]
                    if f
                    else []
                )
                ab, res = await _sincronizar_episodios(conn, chave, achados)
                abertos += ab
                resolvidos_notificaveis += res
            await conn.commit()

    if abertos:
        linhas = [formatar_alerta(s_, t, d, usos.get(s_)) for s_, t, d in abertos]
        ok = await _notificar("⚠️ Saúde de IA — degradação detectada", linhas)
        if ok:
            async with pool.connection() as conn:
                for chave, tipo, _ in abertos:
                    await conn.execute(
                        "UPDATE ia_alerta SET notificado_em = NOW() "
                        "WHERE modelo_slug = %s AND tipo = %s AND resolvido_em IS NULL",
                        (chave, tipo),
                    )
                await conn.commit()
        _cache_indisponiveis.expira_em = 0.0
    if resolvidos_notificaveis:
        linhas = [
            (
                f"{TIPOS_LABEL.get(t, t)}: {s_.removeprefix(CHAVE_AGENTE)} voltou ao normal"
                if s_.startswith(CHAVE_AGENTE)
                else f"{TIPOS_LABEL.get(t, t)}: {s_} voltou ao normal"
            )
            for s_, t in resolvidos_notificaveis
        ]
        await _notificar("✅ Saúde de IA — normalizado", linhas)
        _cache_indisponiveis.expira_em = 0.0

    if abertos or resolvidos_notificaveis:
        logger.info(
            "ia_alertas_tick",
            abertos=len(abertos),
            resolvidos_notificados=len(resolvidos_notificaveis),
        )
    return {"abertos": len(abertos), "resolvidos": len(resolvidos_notificaveis)}


@dataclass
class _CacheIndisponiveis:
    expira_em: float = 0.0
    slugs: dict[str, str] = field(default_factory=dict)


_cache_indisponiveis = _CacheIndisponiveis()
INDISPONIVEIS_CACHE_S = 60.0


async def modelos_indisponiveis(pool: AsyncConnectionPool) -> dict[str, str]:
    """{slug: motivo} dos modelos com episódio ativo que os tira de
    circulação (`TIPOS_INDISPONIVEL`) + os só com provedor abaixo do piso
    (informativo no seletor). Cache de 60 s por processo — o loader consulta
    a cada mensagem."""
    import time

    if time.monotonic() < _cache_indisponiveis.expira_em:
        return _cache_indisponiveis.slugs
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT modelo_slug, tipo, detalhe->>'motivo'
              FROM ia_alerta
             WHERE resolvido_em IS NULL
               AND tipo IN ('modelo_indisponivel', 'modelo_sumiu', 'sem_provedor_permitido')
             ORDER BY CASE tipo WHEN 'sem_provedor_permitido' THEN 1 ELSE 0 END
            """
        )
        rows = await cur.fetchall()
    out: dict[str, str] = {}
    for slug, tipo, motivo in rows:
        out.setdefault(
            str(slug), f"{tipo}:{motivo or TIPOS_LABEL.get(str(tipo), str(tipo))}"
        )
    _cache_indisponiveis.slugs = out
    _cache_indisponiveis.expira_em = time.monotonic() + INDISPONIVEIS_CACHE_S
    return out


def modelo_fora_de_circulacao(slug: str | None, indisponiveis: dict[str, str]) -> bool:
    """Pura: só os tipos que tiram o modelo de circulação trocam o runtime."""
    if not slug or slug not in indisponiveis:
        return False
    tipo = indisponiveis[slug].split(":", 1)[0]
    return tipo in TIPOS_INDISPONIVEL


def _json(obj: Any) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False)


async def notificar_plataforma(titulo: str, linhas: list[str]) -> bool:
    """Canal do superadmin (WhatsApp da empresa 1 + Telegram) para outros
    módulos — a vigência de plano (ADR-005 leva E) avisa por aqui."""
    return await _notificar(titulo, linhas)


async def _notificar(titulo: str, linhas: list[str]) -> bool:
    """WhatsApp da empresa 1 + Telegram, ambos best-effort.

    True se AO MENOS um canal saiu — é o que marca `notificado_em` (com os
    dois mudos, o próximo episódio ainda tenta de novo; o banner do painel
    independe disto).
    """
    texto = titulo + "\n" + "\n".join(f"• {li}" for li in linhas)
    ok = False
    try:
        ok = await _enviar_whatsapp_vsa(texto) or ok
    except Exception as exc:  # noqa: BLE001 — canal não pode derrubar o tick
        logger.warning("ia_alerta_whatsapp_falhou", error=str(exc)[:200])
    try:
        ok = await _enviar_telegram(texto) or ok
    except Exception as exc:  # noqa: BLE001
        logger.warning("ia_alerta_telegram_falhou", error=str(exc)[:200])
    return ok


async def _enviar_whatsapp_vsa(texto: str) -> bool:
    """Mesmo caminho do resumo diário: conexão ativa da empresa 1 (VSA) →
    telefone do resumo diário. Sem telefone ou sem conexão = canal mudo."""
    from whatsapp_langchain.shared.conexao import list_conexoes
    from whatsapp_langchain.shared.db import get_pool
    from whatsapp_langchain.shared.outbound import build_outbound_client
    from whatsapp_langchain.shared.rls_context import empresa_scope

    pool = await get_pool()
    with empresa_scope(1):
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT resumo_diario_telefone FROM empresa WHERE id = 1"
            )
            row = await cur.fetchone()
        telefone = str(row[0]) if row and row[0] else None
        if not telefone:
            return False
        conexoes = await list_conexoes(pool, 1)
        ativas = [c for c in conexoes if c.status == "active"]
        if not ativas:
            return False
        client, _mode = await build_outbound_client(pool, ativas[0])
        await client.send_message(telefone, texto)
    return True


async def _enviar_telegram(texto: str) -> bool:
    """Bot API direto — sem lib. Envs vazios = canal desligado."""
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        return False
    token = settings.telegram_bot_token.get_secret_value()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": settings.telegram_chat_id, "text": texto},
            timeout=15.0,
        )
        resp.raise_for_status()
    return True
