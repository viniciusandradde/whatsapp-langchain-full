"""Relatório mensal de uso: o que a plataforma processou para um cliente.

Volume de mensagens, arquivos lidos, tempo de resposta e disponibilidade — os
números que o cliente recebe em PDF pelo WhatsApp. **Nada de conteúdo de
conversa**: só contagem, formato e tempo.

Uma nota sobre as consultas: elas usam `starts_with(response, '[marcador')` em
vez de `LIKE '[marcador%'`. Não é preferência de estilo — `%` dentro do texto
de uma query parametrizada é o defeito que já derrubou dois endpoints em
produção (ver `tests/unit/test_sql_placeholders.py`). Sem `%` no SQL, o
problema não pode nascer.
"""

from __future__ import annotations

import base64
import re
import unicodedata
from calendar import monthrange
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.rls_context import empresa_scope

logger = structlog.get_logger()

TZ_PADRAO = "America/Campo_Grande"

# Marcadores que o worker grava em `response` quando NÃO houve resposta do
# agente. Precisam ficar em sintonia com `worker/processor.py` — a mesma
# dívida que `android/.../domain/Bolha.kt:15-18` registra do outro lado.
MARCADOR_SILENCIADA = "[whitelist"
MARCADOR_ENCAMINHADA = "[fila do departamento"
MARCADOR_MANUAL = "[modo manual"
MARCADOR_SUPERADA = "[resposta superada"

# Como cada mime aparece no relatório. Ordem = ordem de exibição; o que não
# casar entra como "Outro" em vez de sumir.
_ROTULO_FORMATO: tuple[tuple[str, str], ...] = (
    ("audio/", "Áudio — nota de voz"),
    ("image/", "Imagem — foto"),
    ("application/pdf", "PDF"),
    ("video/", "Vídeo"),
    ("application/vnd.openxmlformats-officedocument.wordprocessingml", "Word"),
    ("application/msword", "Word"),
    ("application/vnd.openxmlformats-officedocument.spreadsheetml", "Planilha Excel"),
    ("application/vnd.ms-excel", "Planilha Excel"),
    ("application/vnd.openxmlformats-officedocument.presentationml", "Apresentação"),
    ("text/", "Texto"),
)


@dataclass
class Competencia:
    """Um mês fechado (ou o corrente, em curso)."""

    ano: int
    mes: int

    @property
    def inicio(self) -> date:
        return date(self.ano, self.mes, 1)

    @property
    def fim(self) -> date:
        """Último dia do mês, inclusivo."""
        return date(self.ano, self.mes, monthrange(self.ano, self.mes)[1])

    @property
    def rotulo(self) -> str:
        return f"{self.ano:04d}-{self.mes:02d}"

    def parcial_em(self, hoje: date) -> bool:
        """True quando o mês ainda está correndo — o PDF sai marcado."""
        return self.inicio <= hoje <= self.fim

    @classmethod
    def de_rotulo(cls, rotulo: str) -> Competencia:
        """`2026-07` -> Competencia(2026, 7). ValueError em formato inválido."""
        ano_s, _, mes_s = rotulo.partition("-")
        ano, mes = int(ano_s), int(mes_s)
        if not 1 <= mes <= 12 or not 2000 <= ano <= 2999:
            raise ValueError(f"competência fora do intervalo: {rotulo!r}")
        return cls(ano, mes)

    @classmethod
    def mes_anterior(cls, hoje: date | None = None) -> Competencia:
        """O último mês FECHADO — o default do relatório."""
        hoje = hoje or datetime.now(UTC).date()
        primeiro = date(hoje.year, hoje.month, 1)
        anterior = primeiro.replace(day=1)
        if anterior.month == 1:
            return cls(anterior.year - 1, 12)
        return cls(anterior.year, anterior.month - 1)


def rotulo_de_formato(media_type: str | None) -> str:
    """Nome legível do formato, a partir do mime cru."""
    mime = (media_type or "").split(";")[0].strip().lower()
    for prefixo, rotulo in _ROTULO_FORMATO:
        if mime.startswith(prefixo):
            return rotulo
    return "Outro"


async def montar_dados(
    pool: AsyncConnectionPool,
    empresa_id: int,
    competencia: Competencia,
    *,
    tz: str = TZ_PADRAO,
) -> dict[str, Any]:
    """Todos os blocos do relatório, num dict pronto para JSON e para o PDF.

    Um mês sem movimento devolve zeros e listas vazias, nunca erro: o cliente
    novo também recebe relatório, e "nenhuma mensagem" é uma informação.
    """
    inicio, fim = competencia.inicio, competencia.fim
    # Intervalo meio-aberto no SQL: `< fim + 1 dia` pega o último dia inteiro
    # sem depender do tipo da coluna.
    fim_exclusivo = date.fromordinal(fim.toordinal() + 1)
    params = {"eid": empresa_id, "ini": inicio, "fim": fim_exclusivo, "tz": tz}

    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            cur = await conn.execute(
                "SELECT nome FROM empresa WHERE id = %(eid)s", {"eid": empresa_id}
            )
            row_emp = await cur.fetchone()
            nome_empresa = row_emp[0] if row_emp else f"Empresa {empresa_id}"

            diario = await _diario(conn, params)
            formatos = await _formatos(conn, params)
            destino = await _destino(conn, params)
            desempenho = await _desempenho(conn, params)
            horas = await _horas(conn, params)
            triagem = await _triagem(conn, params)

    hoje = datetime.now(UTC).astimezone(ZoneInfo(tz)).date()
    parcial = competencia.parcial_em(hoje)
    dias = len(diario) or 1

    mensagens = sum(d["mensagens"] for d in diario)
    com_arquivo = sum(d["com_arquivo"] for d in diario)
    recebidos = sum(f["recebidos"] for f in formatos)
    lidos = sum(f["lidos"] for f in formatos)

    return {
        "empresa": {"id": empresa_id, "nome": nome_empresa},
        "competencia": competencia.rotulo,
        "inicio": inicio.isoformat(),
        "fim": fim.isoformat(),
        "parcial": parcial,
        "tz": tz,
        "totais": {
            "mensagens": mensagens,
            "com_arquivo": com_arquivo,
            "dias_com_movimento": len(diario),
            "mensagens_por_dia": round(mensagens / dias, 1),
            "contatos": triagem["pessoas"],
            "atendimentos": triagem["atendimentos"],
            "arquivos_recebidos": recebidos,
            "arquivos_lidos": lidos,
        },
        "diario": diario,
        "formatos": formatos,
        "destino": destino,
        "desempenho": desempenho,
        "horas": horas,
        "triagem": triagem,
    }


async def _diario(conn: Any, params: dict[str, Any]) -> list[dict[str, Any]]:
    cur = await conn.execute(
        """
        SELECT date_trunc('day', created_at AT TIME ZONE %(tz)s)::date AS dia,
               count(*) AS mensagens,
               count(*) FILTER (WHERE media_type IS NOT NULL) AS com_arquivo,
               count(DISTINCT phone_number) AS contatos,
               count(DISTINCT atendimento_id) AS atendimentos
          FROM message_queue
         WHERE empresa_id = %(eid)s
           AND created_at >= %(ini)s AND created_at < %(fim)s
         GROUP BY 1
         ORDER BY 1
        """,
        params,
    )
    return [
        {
            "dia": r[0].isoformat(),
            "mensagens": r[1],
            "com_arquivo": r[2],
            "contatos": r[3],
            "atendimentos": r[4],
        }
        for r in await cur.fetchall()
    ]


async def _formatos(conn: Any, params: dict[str, Any]) -> list[dict[str, Any]]:
    """Arquivos por mime, agrupados pelo rótulo legível.

    O agrupamento acontece em Python, não no SQL: `.doc` e `.docx` são mimes
    diferentes que viram a mesma linha "Word", e um CASE cobrindo isso no SQL
    duplicaria a tabela `_ROTULO_FORMATO` num segundo lugar.
    """
    cur = await conn.execute(
        """
        SELECT media_type,
               count(*) AS recebidos,
               count(*) FILTER (WHERE media_processing_status = 'processed') AS lidos
          FROM message_queue
         WHERE empresa_id = %(eid)s
           AND media_type IS NOT NULL
           AND created_at >= %(ini)s AND created_at < %(fim)s
         GROUP BY 1
        """,
        params,
    )
    acumulado: dict[str, dict[str, int]] = {}
    for media_type, recebidos, lidos in await cur.fetchall():
        alvo = acumulado.setdefault(
            rotulo_de_formato(media_type), {"recebidos": 0, "lidos": 0}
        )
        alvo["recebidos"] += recebidos
        alvo["lidos"] += lidos

    return sorted(
        ({"formato": k, **v} for k, v in acumulado.items()),
        key=lambda f: f["recebidos"],
        reverse=True,
    )


async def _destino(conn: Any, params: dict[str, Any]) -> dict[str, int]:
    """Para onde foi cada mensagem — o roteamento, não o conteúdo."""
    cur = await conn.execute(
        """
        SELECT
          count(*) FILTER (
            WHERE response IS NOT NULL AND NOT starts_with(response, '[')
          ) AS respondida,
          count(*) FILTER (WHERE starts_with(response, %(m_fila)s)) AS encaminhada,
          count(*) FILTER (WHERE starts_with(response, %(m_white)s)) AS silenciada,
          count(*) FILTER (WHERE starts_with(response, %(m_manual)s)) AS manual,
          count(*) FILTER (WHERE starts_with(response, %(m_super)s)) AS superada
          FROM message_queue
         WHERE empresa_id = %(eid)s
           AND created_at >= %(ini)s AND created_at < %(fim)s
        """,
        {
            **params,
            "m_fila": MARCADOR_ENCAMINHADA,
            "m_white": MARCADOR_SILENCIADA,
            "m_manual": MARCADOR_MANUAL,
            "m_super": MARCADOR_SUPERADA,
        },
    )
    row = await cur.fetchone()
    chaves = ("respondida", "encaminhada", "silenciada", "manual", "superada")
    return dict(zip(chaves, row or (0,) * 5, strict=True))


async def _desempenho(conn: Any, params: dict[str, Any]) -> dict[str, Any]:
    """Tempo de resposta e confiabilidade.

    O tempo medido é de ponta a ponta — da chegada na fila até a conclusão —
    então inclui transcrever o áudio e ler o documento. É a medida honesta do
    que o cliente espera, não do que o modelo demora.
    """
    cur = await conn.execute(
        """
        SELECT count(*) AS processadas,
               avg(EXTRACT(epoch FROM (processed_at - created_at))) AS seg_medio,
               percentile_cont(0.95) WITHIN GROUP (
                 ORDER BY EXTRACT(epoch FROM (processed_at - created_at))
               ) AS seg_p95
          FROM message_queue
         WHERE empresa_id = %(eid)s
           AND processed_at IS NOT NULL
           AND created_at >= %(ini)s AND created_at < %(fim)s
        """,
        params,
    )
    row = await cur.fetchone()
    processadas, seg_medio, seg_p95 = row or (0, None, None)

    cur = await conn.execute(
        """
        SELECT count(*) AS total,
               count(*) FILTER (WHERE status = 'failed') AS falhas
          FROM message_queue
         WHERE empresa_id = %(eid)s
           AND created_at >= %(ini)s AND created_at < %(fim)s
        """,
        params,
    )
    row = await cur.fetchone()
    total, falhas = row or (0, 0)

    return {
        "processadas": processadas,
        "seg_medio": round(float(seg_medio), 1) if seg_medio is not None else None,
        "seg_p95": round(float(seg_p95), 1) if seg_p95 is not None else None,
        "falhas": falhas,
        "taxa_sucesso": round(100 * (1 - falhas / total), 2) if total else None,
    }


async def _horas(conn: Any, params: dict[str, Any]) -> list[dict[str, int]]:
    cur = await conn.execute(
        """
        SELECT EXTRACT(hour FROM created_at AT TIME ZONE %(tz)s)::int AS hora,
               count(*) AS mensagens
          FROM message_queue
         WHERE empresa_id = %(eid)s
           AND created_at >= %(ini)s AND created_at < %(fim)s
         GROUP BY 1
         ORDER BY 1
        """,
        params,
    )
    return [{"hora": r[0], "mensagens": r[1]} for r in await cur.fetchall()]


async def _triagem(conn: Any, params: dict[str, Any]) -> dict[str, Any]:
    cur = await conn.execute(
        """
        SELECT count(*) AS atendimentos,
               count(*) FILTER (WHERE triagem_completa) AS com_triagem,
               count(*) FILTER (WHERE prioridade = 'urgente') AS urgentes,
               count(*) FILTER (WHERE prioridade = 'alta') AS alta,
               count(DISTINCT cliente_id) AS pessoas
          FROM atendimento
         WHERE empresa_id = %(eid)s
           AND created_at >= %(ini)s AND created_at < %(fim)s
        """,
        params,
    )
    row = await cur.fetchone()
    atendimentos, com_triagem, urgentes, alta, pessoas = row or (0, 0, 0, 0, 0)
    return {
        "atendimentos": atendimentos,
        "com_triagem": com_triagem,
        "urgentes": urgentes,
        "alta": alta,
        "pessoas": pessoas,
        "cobertura_pct": (
            round(100 * com_triagem / atendimentos) if atendimentos else None
        ),
    }


# ---------------------------------------------------------------------------
# Agendamento mensal — o molde é `shared/resumo_diario.py`, com uma diferença:
# a unidade de idempotência é a COMPETÊNCIA, não o dia.
# ---------------------------------------------------------------------------

# Tentativas por competência antes de desistir. Mesma razão do resumo diário:
# a falha devolve a competência, e sem teto um telefone inválido viraria uma
# chamada a cada tick contra o provedor até a virada do mês.
MAX_TENTATIVAS = 5


@dataclass
class AgendaUso:
    empresa_id: int
    telefone: str
    dia: int
    horario: time
    tz: str
    last_sent: date | None


def deve_enviar_mensal(cfg: AgendaUso, now_utc: datetime | None = None) -> bool:
    """True quando a competência devida ainda não foi enviada e já passou da
    hora marcada. Função pura — testável sem banco."""
    now_utc = now_utc or datetime.now(UTC)
    try:
        local = now_utc.astimezone(ZoneInfo(cfg.tz))
    except Exception:  # tz inválida cadastrada — não trava o laço
        local = now_utc.astimezone(ZoneInfo(TZ_PADRAO))

    if local.day < cfg.dia:
        return False
    if local.day == cfg.dia and local.time() < cfg.horario:
        return False

    devida = Competencia.mes_anterior(local.date())
    return cfg.last_sent is None or cfg.last_sent < devida.inicio


async def gerar_pdf(
    pool: AsyncConnectionPool,
    empresa_id: int,
    competencia: Competencia,
    *,
    tz: str = TZ_PADRAO,
    com_comparacao: bool = True,
) -> tuple[bytes, str]:
    """Monta o PDF do mês. Devolve `(bytes, nome_do_arquivo)`.

    `com_comparacao` busca também o mês anterior — é o que dá a coluna de
    comparação. Sai desligado quando quem chama já sabe que não há histórico.
    """
    from whatsapp_langchain.shared.relatorio_uso_pdf import montar_pdf

    dados = await montar_dados(pool, empresa_id, competencia, tz=tz)

    anterior = None
    if com_comparacao:
        mes_ant = Competencia.mes_anterior(competencia.inicio)
        dados_ant = await montar_dados(pool, empresa_id, mes_ant, tz=tz)
        # Mês anterior sem nenhuma mensagem quase sempre é "cliente ainda não
        # existia" — uma coluna de zeros ao lado sugeriria queda, não estreia.
        if dados_ant["totais"]["mensagens"]:
            anterior = dados_ant

    pdf = montar_pdf(dados, anterior)
    nome = _nome_arquivo(dados["empresa"]["nome"], competencia)
    return pdf, nome


def _nome_arquivo(nome_empresa: str, competencia: Competencia) -> str:
    """Nome que o cliente vê no WhatsApp — sem acento e sem espaço, porque é
    o que atravessa provedor e sistema de arquivos sem surpresa."""
    limpo = "".join(
        c if c.isalnum() else "-"
        for c in unicodedata.normalize("NFKD", nome_empresa)
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    limpo = re.sub(r"-+", "-", limpo).strip("-") or "cliente"
    return f"Relatorio-de-Uso-{limpo}-{competencia.rotulo}.pdf"


async def _carregar_agenda(
    pool: AsyncConnectionPool, empresa_id: int
) -> AgendaUso | None:
    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT relatorio_uso_telefone, relatorio_uso_dia,
                       relatorio_uso_horario, relatorio_uso_tz,
                       relatorio_uso_last_sent
                  FROM empresa WHERE id = %s
                """,
                (empresa_id,),
            )
            row = await cur.fetchone()
    if not row or not row[0]:
        return None
    return AgendaUso(
        empresa_id=empresa_id,
        telefone=row[0],
        dia=row[1],
        horario=row[2],
        tz=row[3] or TZ_PADRAO,
        last_sent=row[4],
    )


async def _claim_competencia(
    pool: AsyncConnectionPool, empresa_id: int, competencia: Competencia
) -> bool:
    """Marca a competência como enviada, atomicamente.

    UPDATE condicional: só ganha quem trocar primeiro — dois workers rodando o
    mesmo laço não mandam o relatório duas vezes.
    """
    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                UPDATE empresa SET relatorio_uso_last_sent = %(comp)s
                 WHERE id = %(eid)s
                   AND (relatorio_uso_last_sent IS NULL
                        OR relatorio_uso_last_sent < %(comp)s)
                """,
                {"comp": competencia.inicio, "eid": empresa_id},
            )
            await conn.commit()
            return cur.rowcount > 0


async def _registrar_sucesso(
    pool: AsyncConnectionPool, empresa_id: int, competencia: Competencia
) -> None:
    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            await conn.execute(
                """
                UPDATE empresa
                   SET relatorio_uso_last_status = 'ok',
                       relatorio_uso_last_error = NULL,
                       relatorio_uso_last_attempt_at = NOW(),
                       relatorio_uso_tentativas = 0,
                       relatorio_uso_tentativas_mes = %s
                 WHERE id = %s
                """,
                (competencia.inicio, empresa_id),
            )
            await conn.commit()


async def _registrar_falha(
    pool: AsyncConnectionPool,
    empresa_id: int,
    erro: str,
    competencia: Competencia,
    *,
    devolver_para: date | None,
) -> int:
    """Grava a falha e, enquanto houver tentativa, DEVOLVE a competência.

    Mesmo desenho do resumo diário: sem a devolução, um erro passageiro
    custaria o mês inteiro; sem o teto, um telefone inválido viraria uma
    chamada a cada tick até a virada do mês.
    """
    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                UPDATE empresa
                   SET relatorio_uso_tentativas =
                           CASE WHEN relatorio_uso_tentativas_mes = %(mes)s
                                THEN relatorio_uso_tentativas + 1 ELSE 1 END,
                       relatorio_uso_tentativas_mes = %(mes)s,
                       relatorio_uso_last_status = 'erro',
                       relatorio_uso_last_error = %(erro)s,
                       relatorio_uso_last_attempt_at = NOW()
                 WHERE id = %(eid)s
             RETURNING relatorio_uso_tentativas
                """,
                {"mes": competencia.inicio, "erro": erro[:500], "eid": empresa_id},
            )
            row = await cur.fetchone()
            tentativas = int(row[0]) if row else MAX_TENTATIVAS

            if tentativas < MAX_TENTATIVAS:
                await conn.execute(
                    "UPDATE empresa SET relatorio_uso_last_sent = %s WHERE id = %s",
                    (devolver_para, empresa_id),
                )
            await conn.commit()
    return tentativas


async def enviar_relatorio(
    pool: AsyncConnectionPool,
    empresa_id: int,
    competencia: Competencia,
    *,
    telefone: str | None = None,
    tz: str = TZ_PADRAO,
) -> int:
    """Gera o PDF e manda pela conexão padrão da empresa.

    Levanta exceção em qualquer falha — quem chama decide o que fazer com a
    competência. Não persiste linha em `message_queue` nem cria atendimento: é
    mensagem fora do fluxo de atendimento, como o resumo diário.

    Devolve o id da conexão usada.
    """
    # Imports tardios: `outbound` puxa `atendimento` -> `campanha` e de volta
    # este módulo. No topo isso vira ImportError de módulo parcialmente
    # inicializado — o mesmo motivo documentado em `resumo_diario._enviar`.
    from whatsapp_langchain.shared.conexao import list_conexoes
    from whatsapp_langchain.shared.outbound import (
        MIDIA_MAX_BYTES,
        build_outbound_client,
    )

    destino = telefone
    if not destino:
        agenda = await _carregar_agenda(pool, empresa_id)
        if not agenda:
            raise RuntimeError("empresa sem telefone cadastrado para o relatório")
        destino = agenda.telefone
        tz = agenda.tz

    with empresa_scope(empresa_id):
        conexoes = await list_conexoes(pool, empresa_id)
    ativas = [c for c in conexoes if c.status == "active"]
    if not ativas:
        raise RuntimeError("empresa sem conexão ativa para enviar o relatório")
    conexao = ativas[0]  # list_conexoes ordena is_default DESC

    pdf, nome = await gerar_pdf(pool, empresa_id, competencia, tz=tz)
    if len(pdf) > MIDIA_MAX_BYTES:
        raise RuntimeError(
            f"relatório com {len(pdf) // 1024} KB passou do limite de envio"
        )

    with empresa_scope(empresa_id):
        client, _mode = await build_outbound_client(pool, conexao)
        # Duck-typing igual ao de `outbound.send_outbound_manual_midia`: só o
        # cliente Evolution tem `send_media`. WABA exigiria upload no /media do
        # Graph, o que não existe hoje.
        enviar_midia = getattr(client, "send_media", None)
        if enviar_midia is None:
            raise RuntimeError(
                f"conexões {conexao.provider} ainda não enviam arquivo; "
                "use uma conexão Evolution"
            )
        legenda = (
            f"Relatório de uso — {competencia.rotulo}. "
            "Volume processado, arquivos lidos e tempo de resposta."
        )
        await enviar_midia(
            destino,
            base64.b64encode(pdf).decode("ascii"),
            mediatype="document",
            caption=legenda,
            filename=nome,
        )
    return conexao.id


async def _processar_empresa(
    pool: AsyncConnectionPool, agenda: AgendaUso, competencia: Competencia
) -> bool:
    anterior = agenda.last_sent
    if not await _claim_competencia(pool, agenda.empresa_id, competencia):
        return False
    try:
        conexao_id = await enviar_relatorio(
            pool, agenda.empresa_id, competencia, telefone=agenda.telefone, tz=agenda.tz
        )
    except Exception as exc:
        tentativas = await _registrar_falha(
            pool,
            agenda.empresa_id,
            str(exc),
            competencia,
            devolver_para=anterior,
        )
        logger.warning(
            "relatorio_uso_falhou",
            empresa_id=agenda.empresa_id,
            competencia=competencia.rotulo,
            error=str(exc),
            tentativas=tentativas,
            desistiu=tentativas >= MAX_TENTATIVAS,
        )
        return False

    await _registrar_sucesso(pool, agenda.empresa_id, competencia)
    logger.info(
        "relatorio_uso_enviado",
        empresa_id=agenda.empresa_id,
        competencia=competencia.rotulo,
        conexao_id=conexao_id,
        telefone=agenda.telefone,
    )
    return True


async def run_relatorio_uso_all(pool: AsyncConnectionPool) -> int:
    """Varre as empresas com o envio mensal ligado. Devolve quantos saíram."""
    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT id, relatorio_uso_telefone, relatorio_uso_dia,
                       relatorio_uso_horario, relatorio_uso_tz,
                       relatorio_uso_last_sent
                  FROM empresa
                 WHERE status = 'active'
                   AND relatorio_uso_ativo
                   AND relatorio_uso_telefone IS NOT NULL
                """
            )
            linhas = await cur.fetchall()

    enviados = 0
    agora = datetime.now(UTC)
    for eid, telefone, dia, horario, tz, last_sent in linhas:
        agenda = AgendaUso(
            empresa_id=eid,
            telefone=telefone,
            dia=dia,
            horario=horario,
            tz=tz or TZ_PADRAO,
            last_sent=last_sent,
        )
        if not deve_enviar_mensal(agenda, agora):
            continue
        try:
            local = agora.astimezone(ZoneInfo(agenda.tz))
        except Exception:
            local = agora.astimezone(ZoneInfo(TZ_PADRAO))
        competencia = Competencia.mes_anterior(local.date())
        try:
            if await _processar_empresa(pool, agenda, competencia):
                enviados += 1
        except Exception as exc:  # uma empresa não derruba o laço
            logger.warning(
                "relatorio_uso_erro_inesperado", empresa_id=eid, error=str(exc)
            )
    return enviados


async def listar_clientes(pool: AsyncConnectionPool, user_id: str) -> list[dict]:
    """Empresas visíveis ao operador, com a elegibilidade para receber.

    "Elegível" quer dizer três coisas ao mesmo tempo: existe conexão ativa,
    o provedor dessa conexão sabe enviar arquivo, e há telefone cadastrado.
    Empresa que falha em qualquer uma continua na lista — com o motivo — em vez
    de sumir: saber que um cliente está sem conexão é informação, não ruído.
    """
    with empresa_scope(None, bypass=True):
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT e.id, e.nome, e.status,
                       e.relatorio_uso_ativo, e.relatorio_uso_telefone,
                       e.relatorio_uso_last_sent, e.relatorio_uso_last_status,
                       e.relatorio_uso_last_error, e.relatorio_uso_last_attempt_at,
                       count(c.id) FILTER (WHERE c.status = 'active') AS ativas,
                       min(c.provider) FILTER (WHERE c.status = 'active') AS provider
                  FROM empresa e
                  JOIN empresa_membro m ON m.empresa_id = e.id
                  LEFT JOIN conexao c ON c.empresa_id = e.id
                 WHERE m.user_id = %s AND e.status = 'active'
                 GROUP BY e.id
                 ORDER BY e.nome
                """,
                (user_id,),
            )
            linhas = await cur.fetchall()

    clientes = []
    for (
        eid,
        nome,
        _status,
        ativo,
        telefone,
        last_sent,
        last_status,
        last_error,
        last_attempt,
        ativas,
        provider,
    ) in linhas:
        motivos = []
        if not ativas:
            motivos.append("sem conexão ativa")
        elif provider != "evolution":
            motivos.append(f"conexões {provider} ainda não enviam arquivo")
        if not telefone:
            motivos.append("sem telefone cadastrado")

        clientes.append(
            {
                "empresa_id": eid,
                "nome": nome,
                "conexoes_ativas": ativas,
                "provider": provider,
                "telefone": telefone,
                "envio_mensal_ativo": ativo,
                "pode_enviar": not motivos,
                "motivo": " · ".join(motivos) or None,
                "ultima_competencia": last_sent.isoformat() if last_sent else None,
                "ultimo_status": last_status,
                "ultimo_erro": last_error,
                "ultima_tentativa_em": (
                    last_attempt.isoformat() if last_attempt else None
                ),
            }
        )
    return clientes
