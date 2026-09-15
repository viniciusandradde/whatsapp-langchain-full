"""Helpers de Atendimento — fila estruturada de conversas (M3 CRM Light).

Cada inbound resolve um `atendimento` aberto por (empresa, cliente, conexão)
via `open_or_attach_atendimento`. Política:

- Se já existe um aberto (status `aguardando` ou `em_andamento`), **anexa**
  (atualiza `last_message_at` e retorna o id existente).
- Senão, **abre** um novo com status `aguardando`.
- Status final (`resolvido`/`abandonado`) sai do índice parcial único, então
  o próximo inbound abre um atendimento novo.

Painel: `list_atendimentos` aplica 4 tipos de visualização derivados em
runtime — "meus" (atribuídos ao operador), "aguardando" (sem dono),
"grupos" (futuro — placeholder vazio) e "outros" (catch-all dos abertos).
"""

from __future__ import annotations

import base64
import binascii
from typing import TYPE_CHECKING, Any, Literal

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.atendimento_visualizacao import count_unread_para_user
from whatsapp_langchain.shared.models import Atendimento

if TYPE_CHECKING:
    from whatsapp_langchain.shared.models import Conexao

logger = structlog.get_logger()


# Sem alias — usado em RETURNING de INSERT/UPDATE (RETURNING não enxerga alias).
# Ordem: 11 colunas base + 5 mig 047 (padrão profissional) + 7 mig 061
# (triagem) + 2 mig 081/082 (coleta) + 3 mig 129 (snapshot do canal) +
# 2 mig 073 (estado do CSAT) = 30.
#
# `aba_id` (mig 085) saiu na mig 150 — era pinagem manual sem tela, e a aba
# virou filtro salvo por cliente.
#
# Colunas NOVAS entram sempre NO FIM: `_row_to_atendimento` posiciona por
# índice, então inserir no meio reindexaria tudo silenciosamente.
_BARE_COLS = (
    "id, empresa_id, cliente_id, conexao_id, agente_atual, "
    "status, assigned_to_user_id, last_message_at, closed_at, "
    "created_at, updated_at, "
    # Mig 047 padrão profissional
    "protocolo, qtde_resposta_invalida, iniciado_cliente, "
    "finalizado_por_user_id, solicitou_encerramento, "
    # Mig 061 triagem omnichannel
    "departamento_id, classificacao, prioridade, sentimento, "
    "resumo_ia, triagem_completa, triagem_at, "
    # Mig 081/082 wizard coleta
    "coleta_estado, coleta_resumo, "
    # Mig 129 snapshot do canal (persiste após apagar a conexão)
    "conexao_nome, conexao_numero, conexao_provider, "
    # Mig 073 estado do CSAT — lido pelo gate de agrupamento (mig 144)
    "aguardando_avaliacao_at, aguardando_comentario_at"
)
# Com alias `a.` — usado em SELECTs com JOIN.
_BASE_COLS = ", ".join(f"a.{c.strip()}" for c in _BARE_COLS.split(","))
_JOIN_COLS = f"{_BASE_COLS}, c.nome, c.telefone"


def _row_to_atendimento(row, *, with_cliente: bool = False) -> Atendimento:
    # Índices: 0..10 base, 11..15 mig 047, 16..22 mig 061, 23..24 coleta,
    # 25..27 snapshot do canal (mig 129), 28..29 estado do CSAT (mig 073).
    #
    # Os índices a partir de 25 DESCERAM UM ao remover `aba_id` na mig 150. É a
    # razão de o comentário acima mandar acrescentar coluna sempre NO FIM:
    # mexer no meio reindexa tudo, e o erro é silencioso — vira campo trocado,
    # não exceção.
    base_len = 30
    return Atendimento(
        id=row[0],
        empresa_id=row[1],
        cliente_id=row[2],
        conexao_id=row[3],
        agente_atual=row[4],
        status=row[5],
        assigned_to_user_id=row[6],
        last_message_at=row[7],
        closed_at=row[8],
        created_at=row[9],
        updated_at=row[10],
        # Mig 047
        protocolo=row[11],
        qtde_resposta_invalida=row[12] or 0,
        iniciado_cliente=row[13] if row[13] is not None else True,
        finalizado_por_user_id=row[14],
        solicitou_encerramento=row[15] if row[15] is not None else False,
        # Mig 061
        departamento_id=row[16],
        classificacao=row[17],
        prioridade=row[18],
        sentimento=row[19],
        resumo_ia=row[20],
        triagem_completa=row[21] if row[21] is not None else False,
        triagem_at=row[22],
        # Mig 081/082 wizard coleta
        coleta_estado=row[23],
        coleta_resumo=row[24],
        # Mig 129 snapshot do canal (sobrevive ao apagar a conexão)
        conexao_nome=row[25],
        conexao_numero=row[26],
        conexao_provider=row[27],
        # Mig 073 estado do CSAT (lido pelo gate de agrupamento, mig 144)
        aguardando_avaliacao_at=row[28],
        aguardando_comentario_at=row[29],
        # JOIN extras (apenas quando _JOIN_COLS é usado)
        cliente_nome=row[base_len] if with_cliente and len(row) > base_len else None,
        cliente_telefone=row[base_len + 1]
        if with_cliente and len(row) > base_len + 1
        else None,
    )


#: Situação exibida ao operador — o que ele precisa saber para decidir se age.
#:
#: `atendimento.status` sozinho não responde a pergunta que importa: em produção,
#: 77 conversas abertas mostravam "Aguardando" e eram três realidades — a IA
#: conduzindo (~53), a IA muda por whitelist (15) e a IA transferiu sem ninguém
#: pegar (9). Quem via a lista não tinha como distinguir.
#:
#: Deriva de DOIS eixos que já existem no banco (estágio e quem conduz) em vez de
#: uma coluna nova: persistir traria desatualização a cada mudança de whitelist ou
#: de modo da conexão, que acontecem fora do atendimento.
SITUACOES = (
    "resposta_perdida",
    "com_ia",
    "aguardando_humano",
    "em_atendimento",
    "sem_automacao",
    "resolvida",
    "abandonada",
)


def derivar_situacao(
    *,
    status: str,
    assigned_to_user_id: str | None,
    departamento_id: int | None,
    conexao_tipo_atendimento: str | None,
    telefone_na_whitelist: bool,
    resposta_perdida: bool = False,
) -> str:
    """Traduz o estado real da conversa no rótulo que o operador lê.

    A ordem das cláusulas é o próprio contrato, e espelha a ordem dos gates em
    `worker/processor.py::process_message`:

    1. **Fechado vence tudo.** Conversa resolvida não tem "quem conduz".
    2. **Dono humano vence automação.** Com `em_andamento` + dono, o worker cala
       o agente (gate em `processor.py:2395`) — a IA não responde mesmo que a
       conexão esteja em modo `ia`.
    3. **Silenciada vence "aguardando".** Conexão em modo manual (mig 132) ou
       número na whitelist (mig 133 — apesar do nome, é lista de BLOQUEIO) não
       recebem NADA automático. Mostrar "Aguardando" aqui faz o operador supor
       que o bot está cuidando de uma conversa onde o bot nunca vai falar.
    4. **Fila de departamento.** A IA transferiu e ninguém puxou: é o estado que
       precisa de gente, e o que o Chatvolt chama de "Humano Solicitado".
    5. Sobrou a IA conduzindo.

    `hibrido` é valor válido em `conexao.tipo_atendimento` (mig 048) mas o gate
    do worker testa só `== "manual"` — então aqui ele conta como automação ativa,
    para o rótulo não contradizer o que a conversa faz.
    """
    if status == "resolvido":
        return "resolvida"
    if status == "abandonado":
        return "abandonada"
    if status == "em_andamento" and assigned_to_user_id:
        return "em_atendimento"
    # Resposta que esgotou as tentativas de envio. Vem ANTES dos demais porque é
    # o único estado em que o cliente ficou sem retorno por FALHA nossa, e não
    # por desenho — e até aqui morria em silêncio: ninguém era avisado, e só
    # aparecia se alguém abrisse aquela conversa. Foram 7 casos em 10 dias.
    #
    # Fica depois de `em_atendimento` de propósito: com um operador na conversa,
    # ele já está vendo e o alarme viraria ruído.
    if resposta_perdida:
        return "resposta_perdida"
    if conexao_tipo_atendimento == "manual" or telefone_na_whitelist:
        return "sem_automacao"
    if departamento_id is not None and not assigned_to_user_id:
        return "aguardando_humano"
    return "com_ia"


async def open_or_attach_atendimento(
    pool: AsyncConnectionPool,
    empresa_id: int,
    cliente_id: int,
    conexao_id: int,
    *,
    agente: str = "vsa_tech",
    conexao: Conexao | None = None,
    iniciado_cliente: bool = True,
    assigned_to_user_id: str | None = None,
) -> tuple[Atendimento, bool]:
    """Abre novo atendimento ou anexa ao já-aberto (fluxo do webhook).

    Usa o índice parcial `idx_atendimento_aberto_unique` (empresa+cliente+conexao
    WHERE status IN aguardando|em_andamento) pra garantir 1 atendimento aberto
    por tupla. Quando já existe, atualiza `last_message_at` e retorna o id
    existente em uma transação curta.

    Conversa ativa (mig 170): `iniciado_cliente=False` marca origem outbound e
    `assigned_to_user_id` faz o atendimento NASCER `em_andamento` e atribuído
    ao operador que iniciou — o gate de handoff do worker cala a IA. Anexar a
    um atendimento já aberto NÃO rouba o dono existente.

    Retorna `(atendimento, was_created)` — o flag permite o caller disparar
    o evento `atendimento.aberto` só quando um row novo foi inserido.
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {_BASE_COLS} FROM atendimento a
             WHERE a.empresa_id = %s
               AND a.cliente_id = %s
               AND a.conexao_id = %s
               AND a.status IN ('aguardando', 'em_andamento')
             FOR UPDATE
            """,
            (empresa_id, cliente_id, conexao_id),
        )
        row = await cur.fetchone()
        if row:
            cur = await conn.execute(
                f"""
                UPDATE atendimento
                   SET last_message_at = NOW(), updated_at = NOW()
                 WHERE id = %s
                RETURNING {_BARE_COLS}
                """,
                (row[0],),
            )
            updated = await cur.fetchone()
            assert updated is not None
            return _row_to_atendimento(updated), False

        # Fix A (prod 2026-06-01): se o cliente tem um atendimento com CSAT
        # PENDENTE (resolvido + aguardando_avaliacao/comentario, ≤24h), a
        # resposta dele anexa NESSE atendimento em vez de abrir um novo. Sem
        # isso, a resposta da pesquisa criava um atendimento novo que, ao ser
        # fechado, re-disparava a pesquisa → loop infinito de CSAT.
        cur = await conn.execute(
            f"""
            SELECT {_BASE_COLS} FROM atendimento a
             WHERE a.empresa_id = %s
               AND a.cliente_id = %s
               AND a.conexao_id = %s
               AND (a.aguardando_avaliacao_at IS NOT NULL
                    OR a.aguardando_comentario_at IS NOT NULL)
               AND COALESCE(a.aguardando_avaliacao_at, a.aguardando_comentario_at)
                   > NOW() - interval '24 hours'
             ORDER BY a.id DESC
             LIMIT 1
             FOR UPDATE
            """,
            (empresa_id, cliente_id, conexao_id),
        )
        csat_row = await cur.fetchone()
        if csat_row:
            cur = await conn.execute(
                f"""
                UPDATE atendimento
                   SET last_message_at = NOW(), updated_at = NOW()
                 WHERE id = %s
                RETURNING {_BARE_COLS}
                """,
                (csat_row[0],),
            )
            updated = await cur.fetchone()
            assert updated is not None
            return _row_to_atendimento(updated), False

        cur = await conn.execute(
            f"""
            INSERT INTO atendimento
                (empresa_id, cliente_id, conexao_id, agente_atual,
                 conexao_nome, conexao_numero, conexao_provider,
                 iniciado_cliente, assigned_to_user_id, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING {_BARE_COLS}
            """,
            (
                empresa_id,
                cliente_id,
                conexao_id,
                agente,
                conexao.display_name if conexao else None,
                conexao.from_number if conexao else None,
                conexao.provider if conexao else None,
                iniciado_cliente,
                assigned_to_user_id,
                "em_andamento" if assigned_to_user_id else "aguardando",
            ),
        )
        new = await cur.fetchone()
    assert new is not None
    return _row_to_atendimento(new), True


#: Abas da lista. As cinco primeiras espelham o Chatvolt; as quatro últimas são
#: as antigas, mantidas por COMPATIBILIDADE — o APK já instalado pede
#: `tipo=aguardando`, e remover o valor devolveria 422 até o usuário atualizar.
TipoVisualizacao = Literal[
    "nao_resolvidas",
    "nao_lidas",
    "humano_solicitado",
    "resolvidas",
    "todas",
    # Deprecados (clientes antigos):
    "meus",
    "aguardando",
    "grupos",
    "outros",
]


async def list_atendimentos(
    pool: AsyncConnectionPool,
    empresa_id: int,
    *,
    tipo: TipoVisualizacao,
    current_user_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
    scope_departamento_ids: set[int] | None = None,
    dep_id: int | None = None,
    prioridade: str | None = None,
    q: str | None = None,
    aba_id: int | None = None,
    only_ids: list[int] | None = None,
    assigned_to_user_id: str | None = None,
) -> list[Atendimento]:
    """Lista atendimentos filtrados por tipo de visualização.

    - `meus`: status='em_andamento' AND assigned_to_user_id=current_user_id
    - `aguardando`: status='aguardando'
    - `grupos`: placeholder (vazio até M-grupos chegar)
    - `outros`: status IN aguardando|em_andamento, fora dos meus

    `scope_departamento_ids` (E2.B):
    - None ⇒ sem filtro (vê todos os departamentos da empresa).
    - set vazio ⇒ user com scope mas sem departamento → retorna [].
    - set com IDs ⇒ filtra `WHERE departamento_id ∈ ids`.
      `departamento_id IS NULL` (atendimentos sem departamento) NÃO
      aparece pra users com scope — política de "default-deny" pra
      garantir isolamento.

    Faz LEFT JOIN com cliente pra preencher nome/telefone na resposta.
    """
    if tipo == "grupos":
        return []

    if scope_departamento_ids is not None and not scope_departamento_ids:
        return []

    where = "WHERE a.empresa_id = %s"
    params: list = [empresa_id]

    if tipo == "meus":
        if not current_user_id:
            return []
        where += " AND a.status = 'em_andamento' AND a.assigned_to_user_id = %s"
        params.append(current_user_id)
    elif tipo == "aguardando":
        where += " AND a.status = 'aguardando'"
    elif tipo == "nao_resolvidas":
        where += " AND a.status IN ('aguardando', 'em_andamento')"
    elif tipo == "resolvidas":
        where += " AND a.status = 'resolvido'"
    elif tipo == "humano_solicitado":
        # A IA transferiu pra um setor e ninguém puxou. É o estado que precisa de
        # gente — o "Humano Solicitado" do Chatvolt. Mesmas três condições do
        # gate `na_fila_do_departamento` em `worker/processor.py:2369`, senão a
        # aba mostraria conversa que o worker não considera na fila.
        where += (
            " AND a.status = 'aguardando'"
            " AND a.departamento_id IS NOT NULL"
            " AND a.assigned_to_user_id IS NULL"
        )
    elif tipo == "nao_lidas":
        if not current_user_id:
            return []
        # EXISTS em vez de JOIN + GROUP BY: só interessa se há ALGUMA mensagem
        # nova, e o EXISTS para no primeiro acerto.
        where += """ AND EXISTS (
            SELECT 1 FROM message_queue m
              LEFT JOIN atendimento_visualizacao v
                     ON v.atendimento_id = m.atendimento_id AND v.user_id = %s
             WHERE m.atendimento_id = a.id
               AND m.status = 'done'
               AND m.incoming_message IS NOT NULL AND m.incoming_message <> ''
               AND COALESCE(m.interna, FALSE) = FALSE
               AND (v.ultima_visualizacao_at IS NULL
                    OR m.created_at > v.ultima_visualizacao_at))"""
        params.append(current_user_id)
    elif tipo == "todas":
        pass  # sem filtro de status — é a aba "Todas conversas"
    else:  # outros
        where += " AND a.status IN ('aguardando', 'em_andamento')"
        if current_user_id:
            where += (
                " AND (a.assigned_to_user_id IS NULL OR a.assigned_to_user_id <> %s)"
            )
            params.append(current_user_id)

    if scope_departamento_ids is not None:
        where += " AND a.departamento_id = ANY(%s)"
        params.append(list(scope_departamento_ids))

    # Filtros opcionais Sprint F.2 — admin/atendente refina a lista
    if dep_id is not None:
        where += " AND a.departamento_id = %s"
        params.append(dep_id)
    if prioridade is not None:
        where += " AND a.prioridade = %s"
        params.append(prioridade)
    if assigned_to_user_id is not None:
        where += " AND a.assigned_to_user_id = %s"
        params.append(assigned_to_user_id)
    if q:
        where += " AND (c.nome ILIKE %s OR a.protocolo ILIKE %s)"
        like = f"%{q.strip()}%"
        params.extend([like, like])
    if aba_id is not None:
        # Aba é FILTRO SALVO POR CLIENTE, não pasta de conversas pinadas.
        #
        # Resolver aqui valida a POSSE de quebra: `get_aba` filtra por
        # `user_id`, então um id de aba alheia devolve None e a listagem sai
        # vazia. Antes o filtro era `AND a.aba_id = %s` cru, e bastava chutar o
        # número pra ler a pasta de outro operador.
        if not current_user_id:
            return []
        from whatsapp_langchain.shared.aba import cliente_ids_da_aba, get_aba

        aba = await get_aba(pool, aba_id=aba_id, user_id=current_user_id)
        if aba is None:
            return []
        clientes = await cliente_ids_da_aba(
            pool, filtro=aba.get("filtro") or {}, empresa_id=empresa_id
        )
        if clientes is not None:
            if not clientes:
                return []
            where += " AND a.cliente_id = ANY(%s)"
            params.append(clientes)
    if only_ids is not None:
        if not only_ids:
            # Filtro por tag não bateu nenhum atendimento
            return []
        where += " AND a.id = ANY(%s)"
        params.append(list(only_ids))

    params.extend([limit, offset])
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {_JOIN_COLS}, cx.tipo_atendimento
              FROM atendimento a
              LEFT JOIN cliente c ON c.id = a.cliente_id
              LEFT JOIN conexao cx ON cx.id = a.conexao_id
            {where}
            ORDER BY a.last_message_at DESC, a.id DESC
            LIMIT %s OFFSET %s
            """,  # type: ignore[arg-type]
            tuple(params),
        )
        rows = await cur.fetchall()

    itens = [_row_to_atendimento(r, with_cliente=True) for r in rows]
    # `tipo_atendimento` vem depois das colunas de cliente; `_row_to_atendimento`
    # não o conhece (não é campo de `atendimento`), então é lido aqui pelo índice.
    modos = [r[-1] for r in rows]
    await _preencher_derivados(
        pool, empresa_id, itens, modos, current_user_id=current_user_id
    )
    return itens


#: Corte do preview do card da fila — o suficiente pra saber do que se trata.
_PREVIEW_MAX = 120

_ROTULOS_MIDIA = (
    ("audio", "áudio"),
    ("image", "imagem"),
    ("video", "vídeo"),
    ("pdf", "documento"),
)


def _rotulo_midia(media_type: str | None) -> str:
    mt = (media_type or "").lower()
    for chave, rotulo in _ROTULOS_MIDIA:
        if chave in mt:
            return rotulo
    return "anexo"


def _compactar_preview(texto: str) -> str:
    plano = " ".join(texto.split())
    if len(plano) > _PREVIEW_MAX:
        return plano[: _PREVIEW_MAX - 1] + "…"
    return plano


def derivar_preview(
    *,
    incoming_message: str | None,
    response: str | None,
    response_apagada: bool,
    tem_media: bool,
    media_type: str | None,
    tem_response_media: bool,
    response_media_type: str | None,
) -> str | None:
    """Prévia da última mensagem pro card da fila (leva 2026-08). Pura.

    O lado da RESPOSTA vence quando existe — é o conteúdo mais recente do
    row. Marker interno do worker (`MARKERS_INTERNOS`) não é resposta e cai
    pro lado do cliente; apagada vira o mesmo "Mensagem apagada" da timeline;
    mídia vira rótulo ("📎 áudio") porque o conteúdo não sai da listagem.
    Nota interna nem chega aqui: o SQL do lote já a exclui.
    """
    resp = response
    if resp and resp.startswith(MARKERS_INTERNOS):
        resp = None
    if response_apagada and (resp or tem_response_media):
        return "Mensagem apagada"
    if tem_response_media:
        rotulo = f"📎 {_rotulo_midia(response_media_type)}"
        return _compactar_preview(f"{rotulo} — {resp}") if resp else rotulo
    if resp:
        return _compactar_preview(resp)
    if tem_media:
        rotulo = f"📎 {_rotulo_midia(media_type)}"
        if incoming_message:
            return _compactar_preview(f"{rotulo} — {incoming_message}")
        return rotulo
    if incoming_message:
        return _compactar_preview(incoming_message)
    return None


async def _preencher_derivados(
    pool: AsyncConnectionPool,
    empresa_id: int,
    itens: list[Atendimento],
    modos_conexao: list[str | None],
    *,
    current_user_id: str | None,
) -> None:
    """Preenche `situacao`, `ia_ativa` e `nao_lidas` da página.

    Duas queries para a página INTEIRA, não por linha: a whitelist e o contador
    de não lidas são lookups em lote. Fazer por item transformaria uma listagem
    de 50 em 100 idas ao banco.

    Falha aqui **não derruba a listagem** — a conversa aparece com o rótulo
    otimista (`com_ia`) e sem contador. Uma lista que não carrega é pior que uma
    lista com um selo impreciso, e o operador ainda enxerga a conversa.
    """
    if not itens:
        return

    # Import tardio: `whitelist` puxa `campanha` → `outbound` → de volta este
    # módulo. No topo isso é ImportError de módulo parcialmente inicializado.
    from whatsapp_langchain.shared.whitelist import filtrar_whitelistados

    telefones = [a.cliente_telefone for a in itens if a.cliente_telefone]
    try:
        whitelistados = await filtrar_whitelistados(pool, empresa_id, telefones)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "situacao_whitelist_falhou", empresa_id=empresa_id, erro=str(exc)
        )
        whitelistados = set()

    # Conversas cuja ÚLTIMA mensagem esgotou as tentativas de envio.
    #
    # "Última", e não "qualquer uma": um `EXISTS (status='failed')` acenderia o
    # alarme para sempre. Conferido em produção — a conversa 497 tem uma falha
    # antiga e as SEIS mensagens seguintes entregues; o cliente já foi
    # respondido, e o alarme nunca se apagaria. Olhando só a última, uma resposta
    # posterior bem-sucedida limpa o estado sozinha.
    perdidas: set[int] = set()
    try:
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT atendimento_id FROM (
                    SELECT DISTINCT ON (atendimento_id) atendimento_id, status
                      FROM message_queue
                     WHERE atendimento_id = ANY(%s)
                     ORDER BY atendimento_id, id DESC
                ) ultima
                 WHERE status = 'failed'
                """,
                ([a.id for a in itens],),
            )
            perdidas = {r[0] for r in await cur.fetchall()}
    except Exception as exc:  # noqa: BLE001
        logger.warning("situacao_resposta_perdida_falhou", erro=str(exc))

    # Preview da última mensagem visível, em lote — mesma forma da query de
    # perdidas (DISTINCT ON sobre os ≤50 ids da página), com dois cuidados:
    # nota interna fica fora do preview (WHERE interna=FALSE) e mídia entra
    # como boolean `IS NOT NULL` — o base64 nunca sai do banco na listagem.
    previews: dict[int, str | None] = {}
    try:
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT DISTINCT ON (atendimento_id)
                       atendimento_id, incoming_message, response,
                       response_apagada_at IS NOT NULL,
                       media_url IS NOT NULL, media_type,
                       response_media_url IS NOT NULL, response_media_type
                  FROM message_queue
                 WHERE atendimento_id = ANY(%s)
                   AND COALESCE(interna, FALSE) = FALSE
                 ORDER BY atendimento_id, id DESC
                """,
                ([a.id for a in itens],),
            )
            for r in await cur.fetchall():
                previews[r[0]] = derivar_preview(
                    incoming_message=r[1],
                    response=r[2],
                    response_apagada=bool(r[3]),
                    tem_media=bool(r[4]),
                    media_type=r[5],
                    tem_response_media=bool(r[6]),
                    response_media_type=r[7],
                )
    except Exception as exc:  # noqa: BLE001
        logger.warning("situacao_preview_falhou", erro=str(exc))

    # Tags do cliente, em lote. `cliente_tag` (texto livre) é a tabela VIVA —
    # ver `shared/aba.py::cliente_ids_da_aba` para o porquê da v2 não servir.
    tags_por_cliente: dict[int, list[str]] = {}
    try:
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT cliente_id, tag FROM cliente_tag
                 WHERE cliente_id = ANY(%s)
                 ORDER BY cliente_id, tag
                """,
                ([a.cliente_id for a in itens],),
            )
            for cid, tag in await cur.fetchall():
                tags_por_cliente.setdefault(cid, []).append(tag)
    except Exception as exc:  # noqa: BLE001
        logger.warning("situacao_tags_cliente_falhou", erro=str(exc))

    nao_lidas: dict[int, int] = {}
    if current_user_id:
        try:
            nao_lidas = await count_unread_para_user(
                pool,
                atendimento_ids=[a.id for a in itens],
                user_id=current_user_id,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("situacao_nao_lidas_falhou", erro=str(exc))

    for atd, modo in zip(itens, modos_conexao, strict=False):
        na_whitelist = (
            bool(atd.cliente_telefone) and atd.cliente_telefone in whitelistados
        )
        atd.situacao = derivar_situacao(
            status=atd.status,
            assigned_to_user_id=atd.assigned_to_user_id,
            departamento_id=atd.departamento_id,
            conexao_tipo_atendimento=modo,
            telefone_na_whitelist=na_whitelist,
            resposta_perdida=atd.id in perdidas,
        )
        # Só `com_ia` responde a próxima mensagem. `aguardando_humano` é
        # justamente o gate que CALA o agente (`processor.py:2369`) — marcá-lo
        # como IA ativa faria a UI prometer uma resposta que não vem.
        atd.ia_ativa = atd.situacao == "com_ia"
        atd.nao_lidas = nao_lidas.get(atd.id, 0)
        atd.cliente_tags = tags_por_cliente.get(atd.cliente_id, [])
        atd.ultima_mensagem_preview = previews.get(atd.id)


async def get_atendimento_by_id(
    pool: AsyncConnectionPool, atendimento_id: int
) -> Atendimento | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {_JOIN_COLS}
              FROM atendimento a
              LEFT JOIN cliente c ON c.id = a.cliente_id
             WHERE a.id = %s
            """,
            (atendimento_id,),
        )
        row = await cur.fetchone()
    return _row_to_atendimento(row, with_cliente=True) if row else None


async def list_atendimentos_by_cliente(
    pool: AsyncConnectionPool,
    empresa_id: int,
    cliente_id: int,
    *,
    limit: int = 10,
    exclude_id: int | None = None,
) -> list[Atendimento]:
    """Histórico de atendimentos do cliente — usado por tools do agente (M5.b.1).

    `exclude_id` permite o agente pedir "histórico exceto o atendimento
    atual" pra não se citar a si próprio.
    """
    where = "WHERE a.empresa_id = %s AND a.cliente_id = %s"
    params: list = [empresa_id, cliente_id]
    if exclude_id is not None:
        where += " AND a.id <> %s"
        params.append(exclude_id)
    params.append(limit)
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {_JOIN_COLS}
              FROM atendimento a
              LEFT JOIN cliente c ON c.id = a.cliente_id
            {where}
            ORDER BY a.created_at DESC
            LIMIT %s
            """,  # type: ignore[arg-type]
            tuple(params),
        )
        rows = await cur.fetchall()
    return [_row_to_atendimento(r, with_cliente=True) for r in rows]


async def claim_atendimento(
    pool: AsyncConnectionPool, atendimento_id: int, user_id: str
) -> Atendimento | None:
    """Operador "puxa" o atendimento. status → em_andamento, assigned → user."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            UPDATE atendimento
               SET status = 'em_andamento',
                   assigned_to_user_id = %s,
                   updated_at = NOW()
             WHERE id = %s AND status IN ('aguardando', 'em_andamento')
            RETURNING {_BARE_COLS}
            """,
            (user_id, atendimento_id),
        )
        row = await cur.fetchone()
    return _row_to_atendimento(row) if row else None


async def devolver_atendimento_para_ia(
    pool: AsyncConnectionPool, atendimento_id: int
) -> Atendimento | None:
    """Desfaz o "Atender": limpa o dono e volta pra `aguardando`.

    O inverso de [claim_atendimento], e o motivo de existir é que assumir era
    **irreversível**. O gate do worker cala o agente quando o atendimento está
    `em_andamento` COM dono; sem uma volta, um clique errado em "Atender" deixava
    aquela conversa sem IA para sempre — as duas saídas que havia eram `close`
    (dispara pesquisa de satisfação no cliente) e `transfer` (avisa o cliente que
    mudou de setor). Nenhuma das duas serve pra corrigir um clique.

    Diferente de `transfer_atendimento_to_departamento`, que também desatribui:
    aqui **nada é enviado ao cliente** e o departamento é preservado. Para quem
    está do outro lado, nada aconteceu — a IA simplesmente volta a responder.

    Só mexe em atendimento ABERTO: devolver um `resolvido` pra fila o reabriria
    pelas costas de quem fechou.
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            UPDATE atendimento
               SET assigned_to_user_id = NULL,
                   status = 'aguardando',
                   updated_at = NOW()
             WHERE id = %s AND status IN ('aguardando', 'em_andamento')
            RETURNING {_BARE_COLS}
            """,
            (atendimento_id,),
        )
        row = await cur.fetchone()
    return _row_to_atendimento(row) if row else None


async def close_atendimento(
    pool: AsyncConnectionPool,
    atendimento_id: int,
    status: Literal["resolvido", "abandonado"] = "resolvido",
) -> Atendimento | None:
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            UPDATE atendimento
               SET status = %s, closed_at = NOW(), updated_at = NOW()
             WHERE id = %s
            RETURNING {_BARE_COLS}
            """,
            (status, atendimento_id),
        )
        row = await cur.fetchone()
    return _row_to_atendimento(row) if row else None


#: Janela do WhatsApp para editar mensagem já entregue. É regra da plataforma,
#: não nossa — não há como estender.
JANELA_EDICAO_SEG = 15 * 60

#: Janela para "apagar para todos". O WhatsApp aceita cerca de 2 dias, mas as
#: fontes divergem (48h/60h/68h) e a plataforma é quem decide na hora. 48h é
#: corte conservador: esconder cedo é melhor que oferecer um botão que falha.
JANELA_APAGAR_SEG = 48 * 3600


def avaliar_alteracao_resposta(
    *,
    message_id: str | None,
    normalized_input: str | None,
    provider: str | None,
    interna: bool,
    tem_midia: bool,
    apagada: bool,
    idade_seg: float | None,
) -> tuple[bool, bool]:
    """`(pode_editar, pode_apagar)` de uma mensagem que saiu para o cliente.

    Regra única, usada tanto pela listagem (para a UI decidir o que mostrar)
    quanto pelas rotas (que revalidam — o cliente nunca é autoridade).

    Editar e apagar exigem a **chave que o WhatsApp devolveu no envio**, e ela
    só existe no caminho manual: `shared/outbound.py` guarda o retorno do
    provedor em `message_queue.message_id`, enquanto o worker descarta o
    retorno nas dezenas de chamadas de envio da IA. Consequência prática: dá
    para mexer no que o operador digitou, não no que a IA respondeu.

    Cada condição, e por quê:

    - **`message_id`** ausente → não há o que endereçar no WhatsApp.
    - prefixo **`mock-`** → ambiente sem envio real; oferecer a ação seria
      prometer algo que falha na cara do operador.
    - **`manual:`** em `normalized_input` → identifica envio de gente. O
      `manual:system:` (transferência, avisos) é excluído: ninguém "errou de
      digitar" uma mensagem que o sistema montou.
    - **`evolution`** → verificado no binário v2.3.7 de produção: a WABA recusa
      as duas operações com "Method not available on WhatsApp Business API".
    - **nota interna** nunca foi ao cliente; editar no WhatsApp não faz sentido.
    - **mídia** fica de fora: o que existe do outro lado é o arquivo, e a
      edição do WhatsApp é de texto.
    - **já apagada** não se edita nem se apaga de novo.
    """
    if not message_id or message_id.startswith("mock-"):
        return (False, False)
    entrada = normalized_input or ""
    if not entrada.startswith("manual:") or entrada.startswith("manual:system:"):
        return (False, False)
    if provider != "evolution" or interna or tem_midia or apagada:
        return (False, False)
    if idade_seg is None:
        return (False, False)
    return (idade_seg < JANELA_EDICAO_SEG, idade_seg < JANELA_APAGAR_SEG)


async def list_atendimento_mensagens(
    pool: AsyncConnectionPool,
    atendimento_id: int,
    empresa_id: int,
    *,
    limit: int = 200,
    before_id: int | None = None,
    incluir_midia: bool = True,
) -> list[dict]:
    """Lista mensagens do atendimento em ordem cronológica (ASC).

    Filtra por (empresa_id, atendimento_id) na message_queue. Retorna
    dicts simples (sem Pydantic) com os campos relevantes ao painel —
    o tipo `Message` já é um shape público da API admin/chats.

    Devolve as mensagens MAIS RECENTES dentro do `limit`. Antes ordenava
    `created_at ASC LIMIT n`, o que entregava as n mais ANTIGAS: numa conversa
    de 301 mensagens (existem duas assim em produção) o operador abria o drawer
    e não via as 101 últimas — inclusive a mensagem que o cliente acabou de
    mandar. Passa a paginar do fim pro começo, como qualquer timeline de chat.

    `before_id` busca a página anterior (histórico), devolvendo mensagens com
    `id` menor. O cursor é o `id` porque BIGSERIAL é monotônico e `created_at`
    tem default NOW() — as duas ordens coincidem, então não há risco de
    página pular ou repetir item.

    `incluir_midia=False` troca o conteúdo da mídia por um booleano
    (`media_disponivel` / `response_media_disponivel`), e o cliente busca os
    bytes depois em `/mensagens/{id}/midia`.

    **Por que isso existe:** mídia é guardada como data-URL base64 na própria
    linha (o worker embute o que baixa do WhatsApp). Medido em produção: um PDF
    ocupa 5 MB numa linha só, e áudios passam de 100 kB. Com `limit=50`, uma
    conversa com anexos devolve dezenas de MB numa resposta — no 4G do celular
    isso é a diferença entre abrir a conversa e não abrir. O `False` nem SELECTa
    a coluna, então o blob não sai do Postgres nem passa pela memória da API.
    """
    where = ["mq.empresa_id = %s", "mq.atendimento_id = %s"]
    args: list[Any] = [empresa_id, atendimento_id]
    if before_id is not None:
        where.append("mq.id < %s")
        args.append(before_id)
    args.append(limit)

    # Mesmas POSIÇÕES nas duas variantes: o mapeamento abaixo é por índice, e
    # trocar a ordem aqui silenciosamente embaralharia os campos.
    if incluir_midia:
        col_midia_in, col_midia_out = "mq.media_url", "mq.response_media_url"
    else:
        col_midia_in = "(mq.media_url IS NOT NULL)"
        col_midia_out = "(mq.response_media_url IS NOT NULL)"

    async with pool.connection() as conn:
        # LEFT JOIN na conexão (não INNER): a mig 129 desacoplou atendimento de
        # conexão com FK SET NULL, então apagar um número preserva o histórico —
        # e essas linhas teriam sumido da timeline com INNER.
        #
        # A idade sai do banco, não de `datetime.now()` do processo: quem manda
        # nas janelas de 15 min e 48h é o relógio do Postgres, e assim API e
        # rota concordam mesmo com drift de container.
        cur = await conn.execute(
            f"""
            SELECT mq.id, mq.agent_id, mq.incoming_message, {col_midia_in},
                   mq.media_type,
                   mq.normalized_input, mq.media_processing_status,
                   mq.response, mq.status, mq.created_at, mq.processed_at,
                   mq.media_processing_error, mq.error,
                   mq.interna, mq.criado_por_user_id,
                   {col_midia_out}, mq.response_media_type, mq.transcricao,
                   mq.response_apagada_at,
                   mq.message_id, c.provider,
                   EXTRACT(EPOCH FROM (
                       NOW() - COALESCE(mq.processed_at, mq.created_at)
                   ))
              FROM message_queue mq
              LEFT JOIN conexao c ON c.id = mq.conexao_id
             WHERE {" AND ".join(where)}
             ORDER BY mq.id DESC
             LIMIT %s
            """,  # type: ignore[arg-type]
            tuple(args),
        )
        rows = list(reversed(await cur.fetchall()))

    saida: list[dict] = []
    for r in rows:
        pode_editar, pode_apagar = avaliar_alteracao_resposta(
            message_id=r[19],
            normalized_input=r[5],
            provider=r[20],
            interna=bool(r[13]),
            tem_midia=bool(r[15]),
            apagada=r[18] is not None,
            # EXTRACT devolve Decimal; a regra compara com int.
            idade_seg=float(r[21]) if r[21] is not None else None,
        )
        saida.append(
            {
                "id": r[0],
                "agent_id": r[1],
                "incoming_message": r[2],
                # Com `incluir_midia=False` estas posições vêm como booleano do
                # `IS NOT NULL`, e o conteúdo não é devolvido — o cliente busca
                # em `/mensagens/{id}/midia`.
                "media_url": r[3] if incluir_midia else None,
                "media_disponivel": bool(r[3]),
                "media_type": r[4],
                "normalized_input": r[5],
                "media_processing_status": r[6],
                "response": r[7],
                "status": r[8],
                "created_at": r[9].isoformat() if r[9] else None,
                "processed_at": r[10].isoformat() if r[10] else None,
                "media_processing_error": r[11],
                "error": r[12],
                # Sprint 1.3 — notas internas (msg só pra equipe, não enviada)
                "interna": r[13] or False,
                "criado_por_user_id": r[14],
                # Mig 146 — mídia enviada PELO OPERADOR. Separada de media_url,
                # que é inbound: quem renderiza decide o lado da bolha pela
                # origem do campo, e misturar as duas põe a foto do operador do
                # lado do cliente.
                "response_media_url": r[15] if incluir_midia else None,
                "response_media_disponivel": bool(r[15]),
                "response_media_type": r[16],
                # Mig 169 — transcrição da nota de voz PARA O OPERADOR (botão
                # "Transcrever" ou automática por conexão). Não é o
                # normalized_input, que é o input montado pro agente.
                "transcricao": r[17],
                # Mig 172 — apagada para todos no WhatsApp. O texto continua em
                # `response` para auditoria; quem renderiza é que troca por
                # "Mensagem apagada".
                "response_apagada": r[18] is not None,
                # Mig 172 — o que a UI pode oferecer nesta mensagem. Booleanos,
                # e não a chave do provedor (`message_id`): ela não serve ao
                # cliente e não precisa sair daqui.
                "pode_editar_resposta": pode_editar,
                "pode_apagar_resposta": pode_apagar,
            }
        )
    return saida


#: Prefixo que separa metadados dos bytes num data-URL.
_MARCA_BASE64 = ";base64,"


async def get_mensagem_midia(
    pool: AsyncConnectionPool,
    *,
    mensagem_id: int,
    atendimento_id: int,
    empresa_id: int,
    lado: str = "in",
) -> tuple[bytes, str] | None:
    """Bytes de UMA mídia, pra servir sob demanda.

    Contrapartida do `incluir_midia=False`: a lista devolve só o booleano e o
    cliente vem buscar o conteúdo aqui, uma mídia por request. É o que evita
    mandar dezenas de MB numa resposta de 50 mensagens.

    `lado` escolhe a coluna: `in` é o que o cliente mandou (`media_url`), `out` é
    o que o operador mandou (`response_media_url`, mig 146). São colunas
    diferentes de propósito — ver `list_atendimento_mensagens`.

    O filtro carrega `empresa_id` E `atendimento_id` além do id da mensagem: sem
    os dois, um id adivinhado devolveria mídia de outro tenant, e o RLS não
    salvaria porque a conexão do pool é da aplicação.

    Returns:
        `(bytes, mime)`, ou None se a mensagem não existe no escopo, não tem
        mídia naquele lado, ou o conteúdo não está no formato data-URL.
    """
    coluna = "response_media_url" if lado == "out" else "media_url"
    tipo_coluna = "response_media_type" if lado == "out" else "media_type"

    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            SELECT {coluna}, {tipo_coluna}
              FROM message_queue
             WHERE id = %s AND atendimento_id = %s AND empresa_id = %s
            """,
            (mensagem_id, atendimento_id, empresa_id),
        )
        row = await cur.fetchone()

    if row is None or not row[0]:
        return None

    conteudo: str = row[0]
    mime: str = row[1] or "application/octet-stream"

    # O worker embute o que baixa do WhatsApp como `data:<mime>;base64,...`.
    # Conteúdo em outro formato (URL externa de mídia antiga, por exemplo) não é
    # decodificável aqui — devolver None faz o cliente mostrar o rótulo de anexo
    # em vez de bytes corrompidos.
    corte = conteudo.find(_MARCA_BASE64)
    if not conteudo.startswith("data:") or corte < 0:
        return None

    try:
        dados = base64.b64decode(conteudo[corte + len(_MARCA_BASE64) :], validate=True)
    except (ValueError, binascii.Error):
        logger.warning(
            "midia_base64_invalida",
            mensagem_id=mensagem_id,
            atendimento_id=atendimento_id,
            lado=lado,
        )
        return None
    return dados, mime


async def transfer_atendimento(
    pool: AsyncConnectionPool, atendimento_id: int, new_user_id: str
) -> Atendimento | None:
    """Transfere o atendimento para outro operador (mantém em_andamento)."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            UPDATE atendimento
               SET assigned_to_user_id = %s,
                   status = 'em_andamento',
                   updated_at = NOW()
             WHERE id = %s
            RETURNING {_BARE_COLS}
            """,
            (new_user_id, atendimento_id),
        )
        row = await cur.fetchone()
    return _row_to_atendimento(row) if row else None


async def transfer_atendimento_to_departamento(
    pool: AsyncConnectionPool, atendimento_id: int, departamento_id: int
) -> Atendimento | None:
    """Transfere o atendimento pra um departamento — limpa o atendente atual e
    volta o status pra 'aguardando' (atendimento entra na fila do depto, qualquer
    atendente do depto pode puxar via `claim`).
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            UPDATE atendimento
               SET departamento_id = %s,
                   assigned_to_user_id = NULL,
                   status = 'aguardando',
                   updated_at = NOW()
             WHERE id = %s
            RETURNING {_BARE_COLS}
            """,
            (departamento_id, atendimento_id),
        )
        row = await cur.fetchone()
    return _row_to_atendimento(row) if row else None


# --- Triagem omnichannel (mig 061) ---


_PRIORIDADES_VALIDAS = {"baixa", "media", "alta", "urgente"}
_SENTIMENTOS_VALIDOS = {"positivo", "neutro", "negativo", "frustrado"}


async def set_classificacao(
    pool: AsyncConnectionPool,
    atendimento_id: int,
    *,
    prioridade: str,
    sentimento: str,
    classificacao: str,
) -> Atendimento | None:
    """Registra classificação da triagem feita pelo agente IA.

    Idempotente — pode ser chamada múltiplas vezes pra re-classificar.
    Atualiza `triagem_at = NOW()`. Levanta `ValueError` em valores inválidos
    (mesmos do CHECK da migration 061).
    """
    if prioridade not in _PRIORIDADES_VALIDAS:
        raise ValueError(
            f"prioridade inválida: {prioridade!r} (use {_PRIORIDADES_VALIDAS})"
        )
    if sentimento not in _SENTIMENTOS_VALIDOS:
        raise ValueError(
            f"sentimento inválido: {sentimento!r} (use {_SENTIMENTOS_VALIDOS})"
        )
    classificacao_clean = (classificacao or "").strip()[:120] or None
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"""
            UPDATE atendimento
               SET prioridade = %s,
                   sentimento = %s,
                   classificacao = %s,
                   triagem_at = NOW(),
                   updated_at = NOW()
             WHERE id = %s
            RETURNING {_BARE_COLS}
            """,
            (prioridade, sentimento, classificacao_clean, atendimento_id),
        )
        row = await cur.fetchone()
    return _row_to_atendimento(row) if row else None


async def count_fila_departamento(
    pool: AsyncConnectionPool,
    *,
    empresa_id: int,
    departamento_id: int,
    atendimento_id: int,
) -> int:
    """Posição (1-based) do atendimento na fila do departamento.

    Conta atendimentos abertos (aguardando|em_andamento) no mesmo dep
    que foram atualizados ANTES (last_message_at <=) do atendimento_id
    em questão. Posição 1 = próximo a ser atendido. Útil pra mensagem
    "Você está na posição N da fila".
    """
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            SELECT COUNT(*) FROM atendimento a
              JOIN atendimento self ON self.id = %s
             WHERE a.empresa_id = %s
               AND a.departamento_id = %s
               AND a.status IN ('aguardando', 'em_andamento')
               AND a.assigned_to_user_id IS NULL
               AND a.last_message_at <= self.last_message_at
            """,
            (atendimento_id, empresa_id, departamento_id),
        )
        row = await cur.fetchone()
    return int(row[0]) if row else 1


async def complete_triagem(
    pool: AsyncConnectionPool,
    atendimento_id: int,
    *,
    departamento_id: int,
    resumo_ia: str,
    prioridade: str | None = None,
) -> Atendimento | None:
    """Marca triagem completa: vincula depto, salva resumo, opcional prioridade.

    Setado por `transfer_to_human` ao final da triagem. Não toca em
    classificacao/sentimento (set_classificacao já cuida disso). Define
    `triagem_completa=TRUE` e `triagem_at` se ainda não setado.
    """
    if prioridade is not None and prioridade not in _PRIORIDADES_VALIDAS:
        raise ValueError(f"prioridade inválida: {prioridade!r}")
    sets = [
        "departamento_id = %s",
        "resumo_ia = %s",
        "triagem_completa = TRUE",
        "triagem_at = COALESCE(triagem_at, NOW())",
        "updated_at = NOW()",
    ]
    params: list = [departamento_id, resumo_ia]
    if prioridade is not None:
        sets.insert(2, "prioridade = %s")
        params.insert(2, prioridade)
    params.append(atendimento_id)
    async with pool.connection() as conn:
        cur = await conn.execute(
            f"UPDATE atendimento SET {', '.join(sets)} WHERE id = %s "  # type: ignore[arg-type]
            f"RETURNING {_BARE_COLS}",
            tuple(params),
        )
        row = await cur.fetchone()
    return _row_to_atendimento(row) if row else None


# ============================================================
# Wizard de coleta multi-pergunta (mig 081/082)
# ============================================================


async def get_coleta_estado(
    pool: AsyncConnectionPool, atendimento_id: int
) -> dict | None:
    """Lê apenas o coleta_estado de um atendimento (1 query rápida)."""
    async with pool.connection() as conn:
        cur = await conn.execute(
            "SELECT coleta_estado FROM atendimento WHERE id = %s",
            (atendimento_id,),
        )
        row = await cur.fetchone()
    if not row:
        return None
    return row[0]


async def set_coleta_estado(
    pool: AsyncConnectionPool, atendimento_id: int, estado: dict | None
) -> None:
    """Sobrescreve coleta_estado. Passe None pra limpar."""
    import json as _json

    payload = _json.dumps(estado, ensure_ascii=False) if estado else None
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE atendimento SET coleta_estado = %s::jsonb, "
            "updated_at = NOW() WHERE id = %s",
            (payload, atendimento_id),
        )


async def clear_coleta_estado(pool: AsyncConnectionPool, atendimento_id: int) -> None:
    """Limpa o estado runtime (chama após gravar resumo final)."""
    await set_coleta_estado(pool, atendimento_id, None)


async def set_coleta_resumo(
    pool: AsyncConnectionPool, atendimento_id: int, resumo: dict
) -> None:
    """Grava snapshot final do wizard pro drawer exibir."""
    import json as _json

    payload = _json.dumps(resumo, ensure_ascii=False)
    async with pool.connection() as conn:
        await conn.execute(
            "UPDATE atendimento SET coleta_resumo = %s::jsonb, "
            "updated_at = NOW() WHERE id = %s",
            (payload, atendimento_id),
        )


# Prefixos que o worker grava em `message_queue.response` quando PULA o agente
# (worker/processor.py). Mensagem nesse estado ficou sem resposta pro cliente,
# então é candidata a reprocesso.
#
# `[handoff humano` fica de fora de propósito: ali um atendente assumiu a
# conversa, e reprocessar faria a IA responder por cima dele.
MARKERS_REPROCESSAVEIS = ("[modo manual", "[whitelist", "[IA sem agente cadastrado")

# TODOS os prefixos internos que o worker grava em `response` no lugar de uma
# resposta real (worker/processor.py). Nada disso foi enviado ao cliente —
# nunca pode aparecer como conteúdo (preview da fila, timeline). Mesma lista
# que o drawer web filtra ao montar bolhas; mudou lá, muda aqui.
MARKERS_INTERNOS = (
    "[handoff humano",
    "[modo manual",
    "[whitelist",
    "[fila do departamento",
    "[resposta superada",
    "[IA sem agente cadastrado",
)


async def reenfileirar_mensagem(
    pool: AsyncConnectionPool,
    empresa_id: int,
    atendimento_id: int,
    message_id: int,
) -> bool:
    """Devolve uma mensagem pra fila pro agente responder.

    Espelha o reset que antes era feito à mão no Postgres: zera o estado de
    processamento e solta a linha pro claim do worker.

    O `WHERE` é a trava anti-duplicata — só atualiza se a linha AINDA estiver
    num estado reprocessável. Dois operadores clicando junto: o primeiro
    reenfileira, o segundo não acha linha e recebe False, em vez de o cliente
    receber a mesma resposta duas vezes.

    Também confina por empresa e atendimento (anti-tenant escape).

    Returns:
        True se reenfileirou; False se a linha não estava mais elegível.
    """
    like_markers = [f"{m}%" for m in MARKERS_REPROCESSAVEIS]
    async with pool.connection() as conn:
        cur = await conn.execute(
            """
            UPDATE message_queue
               SET status = 'queued',
                   attempts = 0,
                   response = NULL,
                   error = NULL,
                   processed_at = NULL,
                   lease_until = NULL,
                   process_after = NOW(),
                   updated_at = NOW()
             WHERE id = %s
               AND empresa_id = %s
               AND atendimento_id = %s
               AND (status = 'failed' OR response LIKE ANY(%s))
            RETURNING id
            """,
            (message_id, empresa_id, atendimento_id, like_markers),
        )
        row = await cur.fetchone()
        await conn.commit()

    reenfileirou = row is not None
    logger.info(
        "mensagem_reenfileirada" if reenfileirou else "reenfileirar_sem_efeito",
        message_id=message_id,
        atendimento_id=atendimento_id,
        empresa_id=empresa_id,
    )
    return reenfileirou
