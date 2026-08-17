"""Testes dos helpers de Atendimento (M3 CRM Light)."""

import base64
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from whatsapp_langchain.shared.atendimento import (
    SITUACOES,
    _row_to_atendimento,
    claim_atendimento,
    close_atendimento,
    derivar_situacao,
    devolver_atendimento_para_ia,
    get_atendimento_by_id,
    get_mensagem_midia,
    list_atendimento_mensagens,
    list_atendimentos,
    list_atendimentos_by_cliente,
    open_or_attach_atendimento,
    transfer_atendimento,
)


def _row(
    *,
    id_=1,
    empresa_id=1,
    cliente_id=1,
    conexao_id=1,
    agente_atual="vsa_tech",
    status="aguardando",
    assigned_to_user_id=None,
    closed_at=None,
    conexao_nome=None,
    conexao_numero=None,
    conexao_provider=None,
):
    """11 base + 5 mig 047 + 7 mig 061 + 2 coleta + 3 mig 129 + 2 CSAT = 30.

    `aba_id` saiu na mig 150 — os índices a partir de 25 desceram um.
    """
    now = datetime.now(UTC)
    return (
        # Base (0..10)
        id_,
        empresa_id,
        cliente_id,
        conexao_id,
        agente_atual,
        status,
        assigned_to_user_id,
        now,
        closed_at,
        now,
        now,
        # Mig 047 padrão profissional (11..15)
        None,  # protocolo
        0,  # qtde_resposta_invalida
        True,  # iniciado_cliente
        None,  # finalizado_por_user_id
        False,  # solicitou_encerramento
        # Mig 061 triagem (16..22)
        None,  # departamento_id
        None,  # classificacao
        None,  # prioridade
        None,  # sentimento
        None,  # resumo_ia
        False,  # triagem_completa
        None,  # triagem_at
        # Mig 081/082 coleta (23..24)
        None,  # coleta_estado
        None,  # coleta_resumo
        # Mig 129 snapshot do canal (25..27)
        conexao_nome,
        conexao_numero,
        conexao_provider,
        # Mig 073 estado do CSAT (28..29) — lido pelo gate de agrupamento
        None,  # aguardando_avaliacao_at
        None,  # aguardando_comentario_at
    )


def _row_with_cliente(*, nome="Fulano", telefone="+5511999", **kwargs):
    return _row(**kwargs) + (nome, telefone)


#: Quantas colunas o SELECT de `list_atendimento_mensagens` devolve.
#:
#: Existe porque as duas fakes abaixo ficaram desatualizadas em silêncio: a mig
#: 169 acrescentou `transcricao` ao SELECT e ninguém acrescentou à linha falsa,
#: então os testes passaram a estourar `IndexError` e ficaram vermelhos sem
#: ninguém notar (o `make ci` não roda a suíte completa aqui). Com a asserção
#: de tamanho, quem mexer no SELECT descobre no ato — e com uma mensagem que
#: diz o que fazer, em vez de um IndexError no meio do mapeamento.
_COLUNAS_MENSAGEM = 22


def _mock_pool(*results) -> tuple[MagicMock, AsyncMock]:
    cur = AsyncMock()
    fetchone_seq = [r for r in results if not isinstance(r, list)]
    fetchall_seq = [r for r in results if isinstance(r, list)]
    cur.fetchone = AsyncMock(side_effect=fetchone_seq if fetchone_seq else [None])
    cur.fetchall = AsyncMock(side_effect=fetchall_seq if fetchall_seq else [[]])
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cur)
    pool = MagicMock()
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


def test_mapeamento_por_indice_nao_desalinhou():
    """Cada coluna cai no campo certo — com valores DISTINTOS.

    `_row_to_atendimento` posiciona por índice. Ao remover `aba_id` na mig 150,
    tudo a partir da posição 25 desceu um, e esse tipo de erro é SILENCIOSO:
    vira campo trocado, não exceção. Um fixture com `None` em tudo passaria
    mesmo desalinhado — daí um valor diferente em cada posição.
    """
    agora = datetime.now(UTC)
    linha = (
        1,
        2,
        3,
        4,
        "agente",
        "aguardando",
        "dono",
        agora,
        None,
        agora,
        agora,
        "PROTO",
        7,
        True,
        "fim",
        False,
        99,
        "classif",
        "alta",
        "positivo",
        "resumo",
        True,
        agora,
        {"c": 1},
        {"r": 2},
        "NOME-CONEXAO",
        "+5567000",
        "evolution",
        agora,
        None,
    )
    assert len(linha) == 30, "a linha do SELECT tem 30 colunas desde a mig 150"

    a = _row_to_atendimento(linha)

    assert a.protocolo == "PROTO"
    assert a.departamento_id == 99
    assert a.coleta_resumo == {"r": 2}
    # As quatro últimas são as que se deslocaram:
    assert a.conexao_nome == "NOME-CONEXAO"
    assert a.conexao_numero == "+5567000"
    assert a.conexao_provider == "evolution"
    assert a.aguardando_avaliacao_at is not None
    assert a.aguardando_comentario_at is None


class TestDerivarSituacao:
    """A regra que traduz o estado real no rótulo que o operador lê.

    Existe porque em produção 77 conversas abertas mostravam "Aguardando" e eram
    três realidades diferentes. Cada teste aqui é uma dessas realidades.
    """

    def _sit(self, **kw):
        base = dict(
            status="aguardando",
            assigned_to_user_id=None,
            departamento_id=None,
            conexao_tipo_atendimento="ia",
            telefone_na_whitelist=False,
        )
        return derivar_situacao(**{**base, **kw})

    def test_conversa_normal_fica_com_a_ia(self):
        assert self._sit() == "com_ia"

    def test_whitelist_nao_pode_parecer_aguardando(self):
        """15 conversas em produção. A IA NUNCA vai responder aquele contato.

        Mostrar "Aguardando" aqui faz o operador supor que o bot está cuidando
        de uma conversa onde o bot está permanentemente mudo.
        """
        assert self._sit(telefone_na_whitelist=True) == "sem_automacao"

    def test_conexao_manual_tambem_e_sem_automacao(self):
        assert self._sit(conexao_tipo_atendimento="manual") == "sem_automacao"

    def test_fila_de_departamento_e_aguardando_humano(self):
        """14 em produção: a IA transferiu e ninguém puxou."""
        assert self._sit(departamento_id=7) == "aguardando_humano"

    def test_dono_humano_vence_a_automacao(self):
        assert (
            self._sit(status="em_andamento", assigned_to_user_id="u1")
            == "em_atendimento"
        )

    def test_silenciada_vence_fila_de_departamento(self):
        """Ordem importa: whitelist + departamento = sem automação.

        Quem está na whitelist não recebe NADA — nem o aviso de fila. Rotular
        como "aguardando humano" prometeria um atendimento que a conversa não
        vai gerar, porque nem o cliente foi avisado.
        """
        assert (
            self._sit(departamento_id=7, telefone_na_whitelist=True) == "sem_automacao"
        )

    def test_resposta_perdida_aparece_e_vence_a_situacao_normal(self):
        """7 casos em 10 dias morriam em silêncio.

        A resposta esgotava as tentativas de envio, o cliente ficava sem retorno
        e ninguém era avisado — só aparecia se alguém abrisse aquela conversa. É
        o único estado em que a falha é NOSSA, não desenho.
        """
        assert self._sit(resposta_perdida=True) == "resposta_perdida"
        # Vence até "sem automação": o envio manual do operador também falha.
        assert (
            self._sit(resposta_perdida=True, telefone_na_whitelist=True)
            == "resposta_perdida"
        )

    def test_operador_na_conversa_silencia_o_alarme(self):
        """Com dono, ele já está vendo — o alarme viraria ruído."""
        assert (
            self._sit(
                status="em_andamento",
                assigned_to_user_id="u1",
                resposta_perdida=True,
            )
            == "em_atendimento"
        )

    def test_conversa_fechada_nao_alarma(self):
        assert self._sit(status="resolvido", resposta_perdida=True) == "resolvida"

    def test_fechada_vence_tudo(self):
        assert self._sit(status="resolvido", telefone_na_whitelist=True) == "resolvida"
        assert self._sit(status="abandonado", departamento_id=7) == "abandonada"

    def test_hibrido_conta_como_automacao_ativa(self):
        """`hibrido` é valor válido (mig 048) mas o gate do worker testa só
        `== "manual"` — o rótulo tem que concordar com o que a conversa faz."""
        assert self._sit(conexao_tipo_atendimento="hibrido") == "com_ia"

    def test_todo_retorno_esta_no_conjunto_declarado(self):
        for combo in [
            {},
            {"telefone_na_whitelist": True},
            {"departamento_id": 7},
            {"status": "em_andamento", "assigned_to_user_id": "u1"},
            {"status": "resolvido"},
            {"status": "abandonado"},
        ]:
            assert self._sit(**combo) in SITUACOES


def _chamada_da_listagem(conn):
    """A chamada que monta a LISTA, não as de enriquecimento.

    `list_atendimentos` faz consultas adicionais depois da principal (whitelist
    em lote e contador de não lidas), então `await_args` — que é a ÚLTIMA
    chamada — passou a apontar pra outra query. Procurar pelo FROM torna a
    asserção independente de quantas vierem depois.
    """
    for chamada in conn.execute.await_args_list:
        if "FROM atendimento a" in chamada.args[0]:
            return chamada
    raise AssertionError("nenhuma chamada de listagem encontrada")


@pytest.mark.asyncio
async def test_open_or_attach_inserts_when_no_open_row():
    # SELECT FOR UPDATE → None, CSAT pendente SELECT → None, INSERT → row
    # (a 2ª SELECT é o lookup de CSAT pendente — Fix A prod 2026-06-01)
    pool, conn = _mock_pool(None, None, _row(id_=10, status="aguardando"))
    out, was_created = await open_or_attach_atendimento(
        pool, 1, 5, 7, agente="vsa_tech"
    )
    assert was_created is True
    assert out.id == 10
    assert out.status == "aguardando"
    # confirma que o segundo execute foi INSERT
    sql_calls = [c.args[0] for c in conn.execute.await_args_list]
    assert any("SELECT" in s and "FOR UPDATE" in s for s in sql_calls)
    assert any("INSERT INTO atendimento" in s for s in sql_calls)


@pytest.mark.asyncio
async def test_open_or_attach_grava_snapshot_do_canal():
    # Mig 129: passar `conexao=` grava nome/número/provider no INSERT pra
    # persistir após apagar a conexão.
    from types import SimpleNamespace

    pool, conn = _mock_pool(
        None,
        None,
        _row(
            id_=11,
            conexao_nome="Vendas",
            conexao_numero="+55119",
            conexao_provider="evolution",
        ),
    )
    fake_conexao = SimpleNamespace(
        display_name="Vendas", from_number="+55119", provider="evolution"
    )
    out, was_created = await open_or_attach_atendimento(
        pool, 1, 5, 7, conexao=fake_conexao
    )
    assert was_created is True
    assert out.conexao_nome == "Vendas"
    assert out.conexao_numero == "+55119"
    assert out.conexao_provider == "evolution"
    # o INSERT inclui as colunas de snapshot + os valores nos params
    insert_call = next(
        c
        for c in conn.execute.await_args_list
        if "INSERT INTO atendimento" in c.args[0]
    )
    assert "conexao_nome, conexao_numero, conexao_provider" in insert_call.args[0]
    assert "Vendas" in insert_call.args[1]


@pytest.mark.asyncio
async def test_open_or_attach_updates_when_already_open():
    # SELECT retorna row existente, UPDATE retorna row atualizado
    existing = _row(id_=42, status="em_andamento")
    pool, conn = _mock_pool(existing, _row(id_=42, status="em_andamento"))
    out, was_created = await open_or_attach_atendimento(pool, 1, 5, 7)
    assert was_created is False
    assert out.id == 42
    sql_calls = [c.args[0] for c in conn.execute.await_args_list]
    assert any(
        "UPDATE atendimento" in s and "last_message_at = NOW()" in s for s in sql_calls
    )


@pytest.mark.asyncio
async def test_list_atendimentos_meus_requires_user_id():
    pool, _ = _mock_pool([])
    out = await list_atendimentos(pool, 1, tipo="meus", current_user_id=None)
    assert out == []


@pytest.mark.asyncio
async def test_list_atendimentos_aguardando_filters_status():
    rows = [_row_with_cliente(id_=1, status="aguardando")]
    pool, conn = _mock_pool(rows)
    out = await list_atendimentos(pool, 1, tipo="aguardando")
    assert len(out) == 1
    assert out[0].cliente_nome == "Fulano"
    assert "a.status = 'aguardando'" in _chamada_da_listagem(conn).args[0]


@pytest.mark.asyncio
async def test_list_atendimentos_grupos_returns_empty():
    pool, _ = _mock_pool()
    out = await list_atendimentos(pool, 1, tipo="grupos")
    assert out == []


@pytest.mark.asyncio
async def test_list_atendimentos_outros_excludes_current_user():
    rows = [
        _row_with_cliente(id_=3, status="em_andamento", assigned_to_user_id="other")
    ]
    pool, conn = _mock_pool(rows)
    out = await list_atendimentos(pool, 1, tipo="outros", current_user_id="me")
    assert len(out) == 1
    chamada = _chamada_da_listagem(conn)
    assert "IS NULL OR a.assigned_to_user_id <> %s" in chamada.args[0]
    assert "me" in chamada.args[1]


@pytest.mark.asyncio
async def test_claim_atendimento_sets_em_andamento():
    pool, conn = _mock_pool(
        _row(id_=8, status="em_andamento", assigned_to_user_id="user-x")
    )
    out = await claim_atendimento(pool, 8, "user-x")
    assert out is not None
    assert out.status == "em_andamento"
    assert out.assigned_to_user_id == "user-x"
    sql = conn.execute.await_args.args[0]
    assert "UPDATE atendimento" in sql
    assert "status = 'em_andamento'" in sql


@pytest.mark.asyncio
async def test_claim_returns_none_when_already_closed():
    pool, _ = _mock_pool(None)  # WHERE status IN aberto não bate
    out = await claim_atendimento(pool, 99, "user-x")
    assert out is None


@pytest.mark.asyncio
async def test_devolver_para_ia_limpa_dono_e_volta_pra_aguardando():
    """O inverso do "Atender".

    O gate do worker cala o agente quando o atendimento está `em_andamento` COM
    dono. As duas condições têm que ser desfeitas: limpar só o dono deixaria
    `em_andamento` (e a lista mostraria como se alguém estivesse atendendo);
    mudar só o status deixaria o dono (e o gate continuaria calando a IA).
    """
    pool, conn = _mock_pool(_row(id_=8, status="aguardando", assigned_to_user_id=None))
    out = await devolver_atendimento_para_ia(pool, 8)

    assert out is not None
    assert out.status == "aguardando"
    assert out.assigned_to_user_id is None

    sql = conn.execute.await_args.args[0]
    assert "assigned_to_user_id = NULL" in sql
    assert "status = 'aguardando'" in sql
    # Só atendimento ABERTO: devolver um resolvido o reabriria por cima de quem
    # fechou.
    assert "status IN ('aguardando', 'em_andamento')" in sql


@pytest.mark.asyncio
async def test_devolver_para_ia_nao_mexe_no_departamento():
    """Diferente de `transfer_atendimento_to_departamento`, que também
    desatribui: aqui o departamento é preservado e NADA é enviado ao cliente."""
    pool, conn = _mock_pool(_row(id_=8, status="aguardando"))
    await devolver_atendimento_para_ia(pool, 8)

    sql = conn.execute.await_args.args[0]
    # Só o SET: `departamento_id` aparece legitimamente no RETURNING, porque faz
    # parte de `_BARE_COLS`. Olhar o SQL inteiro media outra coisa.
    atribuicoes = sql[sql.index("SET") : sql.index("WHERE")]
    assert "departamento_id" not in atribuicoes


@pytest.mark.asyncio
async def test_devolver_para_ia_devolve_none_se_ja_fechado():
    pool, _ = _mock_pool(None)  # WHERE status IN aberto não bate
    assert await devolver_atendimento_para_ia(pool, 99) is None


@pytest.mark.asyncio
async def test_close_atendimento_sets_status_and_closed_at():
    pool, conn = _mock_pool(_row(id_=8, status="resolvido"))
    out = await close_atendimento(pool, 8, status="resolvido")
    assert out is not None
    assert out.status == "resolvido"
    sql = conn.execute.await_args.args[0]
    assert "closed_at = NOW()" in sql
    assert conn.execute.await_args.args[1] == ("resolvido", 8)


@pytest.mark.asyncio
async def test_transfer_atendimento_changes_user():
    pool, conn = _mock_pool(
        _row(id_=8, status="em_andamento", assigned_to_user_id="bob")
    )
    out = await transfer_atendimento(pool, 8, "bob")
    assert out is not None
    assert out.assigned_to_user_id == "bob"
    sql = conn.execute.await_args.args[0]
    assert "assigned_to_user_id = %s" in sql


@pytest.mark.asyncio
async def test_get_atendimento_by_id_joins_cliente():
    pool, _ = _mock_pool(_row_with_cliente(id_=42, nome="Maria", telefone="+551133"))
    out = await get_atendimento_by_id(pool, 42)
    assert out is not None
    assert out.cliente_nome == "Maria"
    assert out.cliente_telefone == "+551133"


@pytest.mark.asyncio
async def test_list_atendimento_mensagens_filters_by_empresa_and_atendimento():
    now = datetime.now(UTC)
    rows = [
        (
            1,
            "vsa_tech",
            "oi",
            None,
            None,
            None,
            None,
            "olá! como posso ajudar?",
            "done",
            now,
            now,
            None,
            None,
            # Sprint 1.3: interna + criado_por_user_id
            False,
            None,
            # Mig 146: mídia enviada pelo OPERADOR (anexo/nota de voz do app).
            None,
            None,
            # Mig 169: transcrição da nota de voz.
            None,
            # Mig 172: apagada + os três insumos da regra de editar/apagar
            # (chave do provedor, provider da conexão e idade em segundos).
            None,
            None,
            None,
            0.0,
        )
    ]
    assert len(rows[0]) == _COLUNAS_MENSAGEM
    pool, conn = _mock_pool(rows)
    out = await list_atendimento_mensagens(pool, 42, 7)
    assert len(out) == 1
    assert out[0]["incoming_message"] == "oi"
    assert out[0]["response"] == "olá! como posso ajudar?"
    # Mensagem só de texto não tem mídia de saída — o campo existe e vem nulo,
    # o que é o que faz a timeline renderizar bolha de texto e não de anexo.
    assert out[0]["response_media_url"] is None
    assert out[0]["response_media_type"] is None
    # Sem chave do provedor não há o que alterar no WhatsApp (mig 172).
    assert out[0]["pode_editar_resposta"] is False
    assert out[0]["pode_apagar_resposta"] is False
    sql = conn.execute.await_args.args[0]
    assert "WHERE mq.empresa_id = %s" in sql
    assert "AND mq.atendimento_id = %s" in sql
    args = conn.execute.await_args.args[1]
    assert args[0] == 7
    assert args[1] == 42


@pytest.mark.asyncio
async def test_incluir_midia_false_nao_seleciona_o_blob():
    """`incluir_midia=False` troca a coluna por `IS NOT NULL`.

    O ponto não é o formato da resposta: é o blob **não sair do Postgres**.
    Mídia é guardada como data-URL base64 na linha (medido em produção: um PDF
    de 5 MB), e `limit=50` numa conversa com anexos devolvia dezenas de MB —
    conversa que não abria no 4G. Selecionar a coluna e descartar depois no
    Python resolveria a resposta HTTP e manteria o custo no banco e na memória
    da API.
    """
    now = datetime.now(UTC)
    rows = [
        (
            1,
            "vsa_tech",
            "olha o comprovante",
            True,  # media_url IS NOT NULL
            "image/jpeg",
            None,
            None,
            "recebido!",
            "done",
            now,
            now,
            None,
            None,
            False,
            None,
            False,  # response_media_url IS NOT NULL
            None,
            None,  # transcricao (mig 169)
            None,  # response_apagada_at (mig 172)
            None,  # message_id
            None,  # provider da conexão
            0.0,  # idade em segundos
        )
    ]
    assert len(rows[0]) == _COLUNAS_MENSAGEM
    pool, conn = _mock_pool(rows)
    out = await list_atendimento_mensagens(pool, 42, 7, incluir_midia=False)

    sql = conn.execute.await_args.args[0]
    assert "media_url IS NOT NULL" in sql
    # A coluna crua não pode aparecer como item selecionado.
    assert "incoming_message, mq.media_url," not in sql

    assert out[0]["media_disponivel"] is True
    assert out[0]["media_url"] is None
    assert out[0]["media_type"] == "image/jpeg"
    assert out[0]["response_media_disponivel"] is False


@pytest.mark.asyncio
async def test_get_mensagem_midia_decodifica_data_url():
    dados = b"\x89PNG\r\n\x1a\n conteudo binario"
    data_url = "data:image/png;base64," + base64.b64encode(dados).decode()
    pool, conn = _mock_pool((data_url, "image/png"))

    out = await get_mensagem_midia(
        pool, mensagem_id=9, atendimento_id=42, empresa_id=7, lado="in"
    )

    assert out == (dados, "image/png")
    # Escopo: id da mensagem sozinho deixaria adivinhar mídia de outro tenant, e
    # o RLS não protegeria — a conexão do pool é a da aplicação.
    args = conn.execute.await_args.args[1]
    assert args == (9, 42, 7)


@pytest.mark.asyncio
async def test_get_mensagem_midia_lado_out_le_a_coluna_do_operador():
    dados = b"ogg-fake"
    data_url = "data:audio/ogg;base64," + base64.b64encode(dados).decode()
    pool, conn = _mock_pool((data_url, "audio/ogg"))

    out = await get_mensagem_midia(
        pool, mensagem_id=9, atendimento_id=42, empresa_id=7, lado="out"
    )

    assert out == (dados, "audio/ogg")
    sql = conn.execute.await_args.args[0]
    # `out` é o que o OPERADOR mandou (mig 146). Ler `media_url` aqui devolveria
    # a mídia do cliente no lugar da dele.
    assert "response_media_url" in sql
    assert "SELECT media_url" not in sql


@pytest.mark.asyncio
async def test_get_mensagem_midia_devolve_none_fora_do_formato_data_url():
    """Conteúdo que não é data-URL não é decodificável — melhor None que lixo.

    Devolver bytes de uma string que não é base64 faria o cliente renderizar
    imagem corrompida; com None ele mostra o rótulo de anexo.
    """
    pool, _ = _mock_pool(("https://exemplo.com/arquivo.jpg", "image/jpeg"))
    assert (
        await get_mensagem_midia(pool, mensagem_id=9, atendimento_id=42, empresa_id=7)
        is None
    )


@pytest.mark.asyncio
async def test_get_mensagem_midia_devolve_none_quando_nao_ha_linha():
    pool, _ = _mock_pool(None)
    assert (
        await get_mensagem_midia(pool, mensagem_id=999, atendimento_id=42, empresa_id=7)
        is None
    )


# --- list_atendimentos_by_cliente (M5.b.1) ---


@pytest.mark.asyncio
async def test_list_atendimentos_by_cliente_filters_empresa_e_cliente():
    pool, conn = _mock_pool([_row_with_cliente(id_=10), _row_with_cliente(id_=11)])
    out = await list_atendimentos_by_cliente(pool, 1, 5)
    assert [a.id for a in out] == [10, 11]
    sql = conn.execute.await_args.args[0]
    assert "WHERE a.empresa_id = %s AND a.cliente_id = %s" in sql
    params = conn.execute.await_args.args[1]
    assert params[0] == 1
    assert params[1] == 5


@pytest.mark.asyncio
async def test_list_atendimentos_by_cliente_exclude_id():
    pool, conn = _mock_pool([_row_with_cliente(id_=11)])
    await list_atendimentos_by_cliente(pool, 1, 5, exclude_id=99, limit=3)
    sql = conn.execute.await_args.args[0]
    params = conn.execute.await_args.args[1]
    assert "AND a.id <> %s" in sql
    assert 99 in params
    assert params[-1] == 3  # limit


@pytest.mark.asyncio
async def test_list_atendimentos_by_cliente_orders_desc_by_created_at():
    pool, conn = _mock_pool([])
    await list_atendimentos_by_cliente(pool, 1, 5)
    sql = conn.execute.await_args.args[0]
    assert "ORDER BY a.created_at DESC" in sql
