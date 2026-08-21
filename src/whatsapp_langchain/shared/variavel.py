"""Variáveis de ambiente por empresa (M5.d).

Permite que admin cadastre KVs (`{nome, valor}`) e referencie em prompts/
modelos como `{{var.NOME}}`. O `render_template` resolve namespaces:

- `empresa.*` — campos do row de empresa (nome, slug, plano, doc).
- `cliente.*` — campos do cliente do atendimento (quando disponível).
- `data.*`   — runtime (`hoje`, `agora`, `now_iso`).
- `var.*`    — KVs cadastrados por empresa em `variavel_ambiente`.

Render é puro: chaves não encontradas ficam literais (`{{var.x}}`) — assim
problemas de variável quebrada são visíveis no log/UI sem derrubar o flow.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import structlog
from psycopg import errors as pg_errors
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.models import VariavelAmbiente, VariavelAmbienteInput

logger = structlog.get_logger()


class DuplicateNomeError(ValueError):
    """Outra variável da mesma empresa já usa esse nome."""


#: Mesmo default das colunas de fuso já existentes (migs 135 e 165).
_TZ_PADRAO = "America/Campo_Grande"

#: `%A` do strftime depende do locale do container, que é o C — daí a tabela.
_DIAS_SEMANA = (
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
)


def _expediente_agora(
    local: datetime,
    inicio: time | None,
    fim: time | None,
    dias: Sequence[int] | None,
) -> str:
    """ "ABERTO" / "FECHADO" — ou "" quando a empresa não cadastrou expediente.

    A conta fica aqui, e não no prompt, porque modelo não compara horas de forma
    confiável: no teste com três modelos diferentes, um respondia "estamos fora
    do horário" às 19h (dentro) e outro atendia normalmente à 01h (fora). O
    prompt recebe a conclusão e só escolhe a frase.

    Expediente que cruza a meia-noite (22h às 6h) é suportado invertendo a
    comparação — o dia considerado é o da ABERTURA.
    """
    if inicio is None or fim is None:
        return ""
    dias_validos = set(dias or ()) or {1, 2, 3, 4, 5}
    hora = local.time()
    if inicio <= fim:
        dentro_da_hora = inicio <= hora < fim
        dia_de_referencia = local.isoweekday()
    else:
        dentro_da_hora = hora >= inicio or hora < fim
        # Depois da meia-noite o turno ainda é o que abriu no dia anterior.
        dia_de_referencia = (
            local.isoweekday() if hora >= inicio else (local.isoweekday() - 1 or 7)
        )
    return (
        "ABERTO" if dentro_da_hora and dia_de_referencia in dias_validos else "FECHADO"
    )


def _contexto_de_data(
    now: datetime,
    timezone_empresa: str,
    expediente: tuple[time | None, time | None, Sequence[int] | None] = (
        None,
        None,
        None,
    ),
) -> dict[str, str]:
    """Namespace `data.*` no fuso da empresa.

    `dia_semana` e `fim_de_semana` existem porque prompts de atendimento dizem
    "segunda a sexta" — sem isso o agente teria que deduzir o dia da data ISO,
    e deduzir é justamente o que faz ele errar. `expediente` vai além e entrega
    a conclusão pronta (ver `_expediente_agora`).
    """
    try:
        local = now.astimezone(ZoneInfo(timezone_empresa))
    except (ZoneInfoNotFoundError, ValueError):
        # Fuso inválido no cadastro não pode derrubar o agente: cai no padrão e
        # segue, que é melhor do que ficar sem prompt nenhum.
        logger.warning("timezone_empresa_invalido", timezone=timezone_empresa)
        local = now.astimezone(ZoneInfo(_TZ_PADRAO))
    return {
        "data.hoje": local.date().isoformat(),
        "data.agora": local.strftime("%H:%M"),
        "data.now_iso": local.isoformat(),
        "data.ano": str(local.year),
        "data.dia_semana": _DIAS_SEMANA[local.weekday()],
        "data.fim_de_semana": "sim" if local.weekday() >= 5 else "não",
        "data.fuso": timezone_empresa,
        "data.expediente": _expediente_agora(local, *expediente),
        # O horário cadastrado também vira variável para o prompt poder CITAR a
        # janela ("das 6h às 23h") sem repetir o número à mão. Prompt com o
        # horário escrito fixo contradiz o cálculo assim que alguém muda o
        # cadastro — e o modelo obedece ao texto, não à conclusão.
        "data.expediente_janela": _janela_texto(*expediente),
    }


def _janela_texto(
    inicio: time | None, fim: time | None, dias: Sequence[int] | None
) -> str:
    """Ex.: "segunda a sexta, das 06:00 às 23:00". Vazio se não cadastrado."""
    if inicio is None or fim is None:
        return ""
    dias_validos = sorted(set(dias or ()) or {1, 2, 3, 4, 5})
    nomes = [_DIAS_SEMANA[d - 1].replace("-feira", "") for d in dias_validos]
    if (
        dias_validos == list(range(dias_validos[0], dias_validos[-1] + 1))
        and len(dias_validos) > 1
    ):
        faixa = f"{nomes[0]} a {nomes[-1]}"
    else:
        faixa = ", ".join(nomes)
    return f"{faixa}, das {inicio.strftime('%H:%M')} às {fim.strftime('%H:%M')}"


_SELECT_COLS = (
    "id, empresa_id, nome, valor, descricao, ativo, "
    "created_by_user_id, created_at, updated_at"
)


def _row_to_variavel(row) -> VariavelAmbiente:
    return VariavelAmbiente(
        id=row[0],
        empresa_id=row[1],
        nome=row[2],
        valor=row[3],
        descricao=row[4],
        ativo=row[5],
        created_by_user_id=row[6],
        created_at=row[7],
        updated_at=row[8],
    )


# --- CRUD ---


async def list_variaveis(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    apenas_ativos: bool = False,
) -> list[VariavelAmbiente]:
    where = "empresa_id = %s"
    if apenas_ativos:
        where += " AND ativo"
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {_SELECT_COLS} FROM variavel_ambiente "
            f"WHERE {where} ORDER BY nome ASC",
            (empresa_id,),
        )
        rows = await cur.fetchall()
    return [_row_to_variavel(r) for r in rows]


async def get_variavel_by_id(
    pool: AsyncConnectionPool, empresa_id: int, var_id: int
) -> VariavelAmbiente | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"SELECT {_SELECT_COLS} FROM variavel_ambiente "
            "WHERE id = %s AND empresa_id = %s",
            (var_id, empresa_id),
        )
        row = await cur.fetchone()
    return _row_to_variavel(row) if row else None


async def create_variavel(
    pool: AsyncConnectionPool,
    empresa_id: int,
    data: VariavelAmbienteInput,
    *,
    user_id: str | None = None,
) -> VariavelAmbiente:
    try:
        async with pool.connection() as conn:
            cur = await conn.execute(
                f"""
                INSERT INTO variavel_ambiente
                    (empresa_id, nome, valor, descricao, ativo,
                     created_by_user_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING {_SELECT_COLS}
                """,
                (
                    empresa_id,
                    data.nome,
                    data.valor,
                    data.descricao,
                    data.ativo,
                    user_id,
                ),
            )
            row = await cur.fetchone()
    except pg_errors.UniqueViolation as e:
        raise DuplicateNomeError(f"variável '{data.nome}' já existe na empresa") from e
    assert row is not None
    return _row_to_variavel(row)


async def update_variavel(
    pool: AsyncConnectionPool,
    empresa_id: int,
    var_id: int,
    data: VariavelAmbienteInput,
) -> VariavelAmbiente | None:
    try:
        async with pool.connection() as conn:
            cur = await conn.execute(
                f"""
                UPDATE variavel_ambiente
                   SET nome = %s,
                       valor = %s,
                       descricao = %s,
                       ativo = %s,
                       updated_at = NOW()
                 WHERE id = %s AND empresa_id = %s
                RETURNING {_SELECT_COLS}
                """,
                (
                    data.nome,
                    data.valor,
                    data.descricao,
                    data.ativo,
                    var_id,
                    empresa_id,
                ),
            )
            row = await cur.fetchone()
    except pg_errors.UniqueViolation as e:
        raise DuplicateNomeError(f"variável '{data.nome}' já existe na empresa") from e
    return _row_to_variavel(row) if row else None


async def delete_variavel(
    pool: AsyncConnectionPool, empresa_id: int, var_id: int
) -> bool:
    async with pool.connection() as conn:
        cur = await conn.execute(
            "DELETE FROM variavel_ambiente WHERE id = %s AND empresa_id = %s",
            (var_id, empresa_id),
        )
    return (cur.rowcount or 0) > 0


# --- Render ---


_TEMPLATE_RE = re.compile(
    r"\{\{\s*([a-zA-Z][a-zA-Z0-9_]*\.[a-zA-Z][a-zA-Z0-9_]*)\s*\}\}"
)


def render_template(text: str, ctx: dict[str, str]) -> str:
    """Substitui `{{namespace.key}}` por `ctx[namespace.key]`.

    Chaves ausentes ficam literais — quem ler o texto final consegue ver
    qual var não resolveu (melhor que silenciar com string vazia).
    """
    if not text:
        return text

    def _sub(m: re.Match[str]) -> str:
        key = m.group(1)
        val = ctx.get(key)
        return val if val is not None else m.group(0)

    return _TEMPLATE_RE.sub(_sub, text)


async def build_render_context(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    atendimento_id: int | None = None,
    now: datetime | None = None,
) -> dict[str, str]:
    """Monta o dict de namespaces pra `render_template`.

    Carrega `empresa.*`, `var.*` (ativos), `data.*`, e — quando
    `atendimento_id` é fornecido — `cliente.*` via JOIN. Variáveis cujo
    namespace.chave não existir são deixadas literais pelo renderizador.
    """
    ctx: dict[str, str] = {}
    now = now or datetime.now(UTC)
    timezone_empresa = _TZ_PADRAO
    expediente: tuple[time | None, time | None, Sequence[int] | None] = (
        None,
        None,
        None,
    )

    async with pool.connection() as conn:
        # empresa.*
        cur = await conn.execute(
            "SELECT nome, slug, doc, plano, timezone, "
            "expediente_inicio, expediente_fim, expediente_dias "
            "FROM empresa WHERE id = %s",
            (empresa_id,),
        )
        row = await cur.fetchone()
        if row is not None:
            ctx["empresa.nome"] = row[0] or ""
            ctx["empresa.slug"] = row[1] or ""
            ctx["empresa.doc"] = row[2] or ""
            ctx["empresa.plano"] = row[3] or ""
            timezone_empresa = row[4] or _TZ_PADRAO
            expediente = (row[5], row[6], row[7])

        # data.* — no fuso da empresa, não em UTC (mig 174).
        #
        # Quem lê estas variáveis é um prompt conversando com um cliente, e o
        # cliente vive no fuso dele. Em UTC, um prompt que decide "estamos no
        # horário de atendimento?" recebia 23h às 19h de Mato Grosso do Sul e
        # respondia "fora do horário" no meio do expediente.
        ctx.update(_contexto_de_data(now, timezone_empresa, expediente))

        # menu.* — primeiro menu ativo da empresa (ou conexão genérica).
        # Usado pelo SYSTEM_PROMPT do agente pra avisar cliente como
        # voltar pro menu (ex: "Digite *{{menu.trigger}}* pra trocar setor").
        cur = await conn.execute(
            "SELECT trigger_keywords, atalho FROM menu_chatbot "
            "WHERE empresa_id = %s AND ativo "
            "ORDER BY conexao_id NULLS LAST, id LIMIT 1",
            (empresa_id,),
        )
        row = await cur.fetchone()
        if row is not None:
            triggers = list(row[0] or [])
            atalho = row[1] or ""
            ctx["menu.trigger"] = triggers[0] if triggers else atalho or "menu"
            ctx["menu.triggers"] = (
                ", ".join(triggers) if triggers else (atalho or "menu")
            )
            ctx["menu.atalho"] = atalho or (triggers[0] if triggers else "menu")
        else:
            # Sem menu cadastrado — placeholders genéricos pra prompt não quebrar
            ctx["menu.trigger"] = "menu"
            ctx["menu.triggers"] = "menu"
            ctx["menu.atalho"] = "menu"

        # var.* (apenas ativos)
        cur = await conn.execute(
            "SELECT nome, valor FROM variavel_ambiente WHERE empresa_id = %s AND ativo",
            (empresa_id,),
        )
        for nome, valor in await cur.fetchall():
            ctx[f"var.{nome}"] = valor or ""

        # cliente.* (opcional, só quando temos atendimento)
        if atendimento_id is not None:
            cur = await conn.execute(
                """
                SELECT c.nome, c.telefone, c.email, c.doc
                  FROM atendimento a
                  JOIN cliente c ON c.id = a.cliente_id
                 WHERE a.id = %s AND a.empresa_id = %s
                """,
                (atendimento_id, empresa_id),
            )
            row = await cur.fetchone()
            if row is not None:
                ctx["cliente.nome"] = row[0] or ""
                ctx["cliente.telefone"] = row[1] or ""
                ctx["cliente.email"] = row[2] or ""
                ctx["cliente.doc"] = row[3] or ""

    return ctx
