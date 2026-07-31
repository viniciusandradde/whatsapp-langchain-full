"""Operações de fila no PostgreSQL.

Módulo compartilhado entre API e Worker para manipular a tabela message_queue.
A API insere mensagens (enqueue), o Worker consome (claim) e
finaliza (mark_done/failed).

O debounce agrupa mensagens rápidas do mesmo remetente: se o usuário
envia 3 mensagens em 2 segundos, elas são concatenadas em uma única
entrada na fila.

A janela de agrupamento (mig 144) é UNIFORME e vem da conexão
(`grouping_seconds`): toda mensagem espera esse tempo, e o que chegar junto vira
uma resposta só. Fluxo guiado (menu/coleta/CSAT) e agrupamento desligado usam a
janela curta `buffer_seconds`.

Houve uma tentativa de dar janela curta à PRIMEIRA mensagem, pra respondê-la na
hora, e longa apenas às de follow-up. Medido em produção, era justamente isso que
deixava o fragmento passar: a row da primeira era reivindicada em 2s e o
"Boa tarde!" que chegava em 6,4s não tinha mais onde mesclar, porque row
reivindicada não aceita merge. Três fragmentos de saudação, três respostas.

O intervalo entre reivindicar a row e a resposta sair (~7s) segue fora do alcance
do debounce — quem cobre esse buraco é `existe_mensagem_mais_nova`, chamada pelo
worker antes de enviar.

Uso:
    from whatsapp_langchain.shared.queue import enqueue_or_buffer

    result = await enqueue_or_buffer(pool, phone="+55...", body="Olá")
    message = await claim_next(pool, lease_seconds=60)
"""

import hashlib
from datetime import UTC, datetime, timedelta

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.models import Atendimento, EnqueueResult, MessageQueue

logger = structlog.get_logger()

# Origens de resposta que caracterizam FLUXO GUIADO: o bot fez uma pergunta
# específica e espera uma resposta única ("digite 1", "nota de 0 a 10", o CPF
# do wizard). Mensagem que chega logo depois de uma dessas não é fragmento de
# pensamento — é a resposta ao prompt, e alongar a janela ali só faria o bot
# parecer travado. Gravadas em `message_queue.origem_resposta` pelo worker.
ORIGENS_FLUXO_GUIADO = frozenset({"menu", "workflow", "coleta", "csat", "aprovacao"})


async def detectar_fluxo_guiado(
    pool: AsyncConnectionPool,
    *,
    phone_number: str,
    agent_id: str,
    atendimento: Atendimento | None = None,
) -> bool:
    """True quando o bot está esperando a resposta a um prompt específico.

    Chamada pelos webhooks pra decidir se a mensagem entra na janela longa de
    agrupamento. Em fluxo guiado ela NÃO entra: ali cada mensagem do cliente é
    uma resposta única e deliberada ("digite 1", a nota do CSAT, o CPF do
    wizard), e alongar a janela só faria o bot parecer travado — num wizard de
    5 perguntas o atraso se multiplicaria por 5.

    Três sinais, do mais barato pro mais caro:
    1. wizard de coleta em curso (`coleta_estado`, já carregado no atendimento);
    2. CSAT aguardando nota ou comentário (idem, mig 073);
    3. a última resposta automática do thread veio de menu/workflow/coleta/CSAT
       (`message_queue.origem_resposta`, mig 144) — 1 SELECT indexado.

    Só o item 3 vai ao banco, e só quando os dois primeiros não decidiram.
    """
    if atendimento is not None:
        if atendimento.coleta_estado:
            return True
        if atendimento.aguardando_avaliacao_at or atendimento.aguardando_comentario_at:
            return True

    # Fail-safe: esta função roda em TODO webhook inbound. Se a query falhar
    # — coluna ainda inexistente porque o código subiu antes da migration,
    # timeout, o que for — o custo de errar aqui é uma janela de 8s a mais num
    # menu. O custo de propagar a exceção é o webhook devolver 500 e a
    # mensagem do cliente se perder. Não é escolha difícil.
    try:
        async with pool.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT origem_resposta FROM message_queue
                 WHERE phone_number = %s
                   AND agent_id = %s
                   AND origem_resposta IS NOT NULL
                 ORDER BY id DESC
                 LIMIT 1
                """,
                (phone_number, agent_id),
            )
            row = await cursor.fetchone()
    except Exception as exc:  # noqa: BLE001 — degradar é melhor que 500
        logger.warning("fluxo_guiado_lookup_failed", phone=phone_number, error=str(exc))
        return False

    return bool(row) and row[0] in ORIGENS_FLUXO_GUIADO


async def existe_mensagem_mais_nova(
    pool: AsyncConnectionPool,
    *,
    phone_number: str,
    agent_id: str,
    message_id: int,
) -> bool:
    """True se chegou mensagem mais nova deste contato enquanto o agente pensava.

    Usada pelo worker imediatamente ANTES de enviar a resposta do agente. O
    agrupamento no enqueue não cobre o intervalo entre a row ser reivindicada e
    a resposta sair (~7s medidos em produção): mensagem que chega nesse buraco
    não pode mais mesclar, porque row reivindicada não aceita merge. O resultado
    era uma resposta por fragmento.

    Quando devolve True, o worker engole a resposta e deixa o turno seguinte
    responder tudo — o contexto já está no checkpointer. Medido em produção:
    mata 8 de 55 respostas sem adicionar um segundo de espera.

    Contrapartida assumida: o agente já rodou, então a resposta descartada
    permanece no histórico do checkpointer. O turno seguinte enxerga uma fala do
    assistente que o cliente nunca leu, e pode se referir a ela. Aceitável pro
    caso dominante (fragmento de saudação); some se o agente for reescrito pra
    consultar a fila antes de invocar o modelo.
    """
    # Fail-safe invertido em relação a `detectar_fluxo_guiado`: na dúvida,
    # ENVIA. Resposta duplicada é ruído; resposta engolida por engano é o
    # cliente sem atendimento.
    try:
        async with pool.connection() as conn:
            cursor = await conn.execute(
                """
                SELECT 1 FROM message_queue
                 WHERE phone_number = %s
                   AND agent_id = %s
                   AND id > %s
                   AND status IN ('queued', 'processing')
                 LIMIT 1
                """,
                (phone_number, agent_id, message_id),
            )
            return await cursor.fetchone() is not None
    except Exception as exc:  # noqa: BLE001 — na dúvida, envia
        logger.warning("supersede_lookup_failed", message_id=message_id, error=str(exc))
        return False


def _resolver_janela(
    *,
    buffer_seconds: float,
    grouping_seconds: float,
    is_guided_flow: bool,
) -> float:
    """Escolhe a janela de debounce desta mensagem — UNIFORME.

    A janela vale pra TODA mensagem, inclusive a primeira do turno. A versão
    anterior dava janela curta à primeira e longa às de follow-up, mas era
    justamente isso que deixava o fragmento passar: medido em produção, a row da
    primeira mensagem era reivindicada em 2s e o "Boa tarde!" que chegava em 6,4s
    não tinha mais onde mesclar — row reivindicada não aceita merge. Resultado:
    três fragmentos de saudação, três respostas.

    Janela uniforme também é o que o mercado faz (n8n 10s, adapter Telegram do
    hermes-agent 0,6/2s, openclaw); a exceção da primeira mensagem era nossa.

    Só encurta em dois casos, ambos decididos sem I/O:
    - agrupamento desligado (`grouping_seconds <= 0`) → comportamento pré-mig 144;
    - fluxo guiado → menu/coleta/CSAT esperando resposta a um prompt, onde
      alongar faria o bot parecer travado.
    """
    if grouping_seconds <= 0 or is_guided_flow:
        return buffer_seconds
    return grouping_seconds


def _com_teto(
    janela: float, inicio_do_lote: datetime, grouping_max_seconds: float
) -> datetime:
    """`process_after` da row, limitado pelo teto do lote.

    Sem o teto a janela desliza a cada mensagem nova e um cliente tagarela
    empurra a resposta indefinidamente. O teto conta da PRIMEIRA mensagem do
    lote, então o atraso máximo é conhecido e não depende do quanto a pessoa
    digita.
    """
    return min(
        datetime.now(UTC) + timedelta(seconds=janela),
        inicio_do_lote + timedelta(seconds=grouping_max_seconds),
    )


async def enqueue_or_buffer(
    pool: AsyncConnectionPool,
    phone_number: str,
    agent_id: str,
    body: str,
    media_url: str | None = None,
    media_type: str | None = None,
    to_number: str | None = None,
    message_id: str | None = None,
    buffer_seconds: float = 2.0,
    empresa_id: int = 1,
    conexao_id: int | None = None,
    atendimento_id: int | None = None,
    grouping_seconds: float = 0.0,
    grouping_max_seconds: float = 45.0,
    is_guided_flow: bool = False,
) -> EnqueueResult:
    """Insere mensagem na fila ou agrupa com mensagem pendente (debounce).

    Regras de debounce (Fase 3):
    - Debounce somente para texto (media_url IS NULL).
    - Concorrência protegida por pg_advisory_xact_lock(hash(phone+agent)).

    Janela de agrupamento (mig 144), quando `grouping_seconds > 0`:
    - UNIFORME: toda mensagem espera `grouping_seconds`, inclusive a primeira.
    - Fluxo guiado (`is_guided_flow`) nunca alonga — ali cada mensagem é a
      resposta a uma pergunta do bot, não fragmento.
    - Toda espera é limitada por `grouping_max_seconds` contados da PRIMEIRA
      mensagem do lote, então cliente tagarela não empurra a resposta pra
      sempre.
    - Mídia deixa de furar o debounce: ela ABSORVE o texto pendente do mesmo
      phone+agent (o texto vira o `body` da row de mídia e a row de texto some),
      pra que texto+áudio produzam uma resposta só em vez de duas.

    Com `grouping_seconds <= 0` o comportamento é exatamente o anterior à mig
    144 — inclusive o flush de texto na chegada de mídia. É o desligamento de
    emergência, e por isso precisa continuar sendo um no-op fiel.

    Múltiplas mídias (NumMedia > 1) seguem como N rows independentes com o
    mesmo message_id, processadas em ordem de created_at pelo worker — a
    absorção resolve texto→mídia, não mídia→mídia.

    Args:
        pool: Pool de conexões do psycopg.
        phone_number: Telefone do remetente (E.164).
        agent_id: ID do agente que vai processar.
        body: Texto da mensagem.
        media_url: URL de mídia anexada (opcional).
        media_type: MIME type da mídia (opcional).
        to_number: Número destinatário (opcional).
        message_id: ID externo da mensagem no provider (opcional).
        buffer_seconds: Janela curta — vale só com agrupamento desligado ou em
            fluxo guiado. Default: 2.0.
        grouping_seconds: Janela de agrupamento (por conexão). 0 desliga.
        grouping_max_seconds: Teto da espera, contado da 1ª mensagem do lote.
        is_guided_flow: True quando o bot espera resposta a um prompt
            (menu/workflow/coleta/CSAT) — força a janela curta.

    Returns:
        EnqueueResult com message_id e se foi buffered.
    """
    thread_id = f"{phone_number}:{agent_id}"
    has_media = media_url is not None

    # Hash determinístico para pg_advisory_xact_lock.
    # Usa os 8 bytes iniciais do SHA-256 convertidos para int64 signed,
    # garantindo chave única por phone+agent sem risco de colisão prática.
    lock_key = int.from_bytes(
        hashlib.sha256(thread_id.encode()).digest()[:8],
        byteorder="big",
        signed=True,
    )

    async with pool.connection() as conn:
        # Sprint A.2.3 — seta RLS context da empresa antes de qualquer
        # query. Webhook handlers nem sempre passam pelo middleware
        # (X-Empresa-Id ausente em webhooks externos), então a função
        # seta o context na conexão diretamente — `false` = session-level
        # (vale até a conn voltar pro pool, que limpa via wrapper).
        await conn.execute(
            "SELECT set_config('app.empresa_id', %s, false)",
            (str(empresa_id),),
        )
        # Lock transacional: serializa debounce para o mesmo phone+agent.
        # Liberado automaticamente no commit/rollback da transação.
        await conn.execute("SELECT pg_advisory_xact_lock(%s)", (lock_key,))

        if has_media:
            inicio_do_lote = datetime.now(UTC)

            if grouping_seconds <= 0:
                # Agrupamento desligado: comportamento pré-mig 144. Flush do
                # texto pendente (antecipa o process_after) pra que o worker o
                # processe ANTES da mídia, via ordenação por created_at.
                flushed = await conn.execute(
                    """
                    UPDATE message_queue
                    SET process_after = NOW(),
                        updated_at = NOW()
                    WHERE phone_number = %s
                      AND agent_id = %s
                      AND status = 'queued'
                      AND process_after > NOW()
                      AND media_url IS NULL
                    """,
                    (phone_number, agent_id),
                )
                if flushed.rowcount and flushed.rowcount > 0:
                    logger.info(
                        "text_flushed_for_media",
                        phone=phone_number,
                        agent_id=agent_id,
                        flushed_count=flushed.rowcount,
                    )
                process_after_midia = inicio_do_lote
            else:
                # Absorção: o texto pendente vira o `body` desta row de mídia e
                # a row de texto é removida. DELETE ... RETURNING num statement
                # só porque `claim_next` não pega o advisory lock — entre um
                # SELECT e um DELETE separados o worker poderia reivindicar a
                # row. Se o worker chegou primeiro, o DELETE não acha nada e a
                # mídia segue como row independente (degrada, não quebra).
                cursor = await conn.execute(
                    """
                    DELETE FROM message_queue
                     WHERE id = (
                         SELECT id FROM message_queue
                          WHERE phone_number = %s
                            AND agent_id = %s
                            AND status = 'queued'
                            AND process_after > NOW()
                            AND media_url IS NULL
                          ORDER BY created_at DESC
                          LIMIT 1
                          FOR UPDATE SKIP LOCKED
                     )
                    RETURNING incoming_message, created_at
                    """,
                    (phone_number, agent_id),
                )
                absorvido = await cursor.fetchone()
                if absorvido:
                    texto_pendente, criado_em = absorvido
                    # `preprocess_incoming_message` monta
                    # `body + "\n[Transcrição de áudio]: ..."`, então o texto
                    # absorvido entra naturalmente no mesmo turno do agente.
                    body = "\n".join(p for p in [texto_pendente, body] if p)
                    inicio_do_lote = criado_em
                    logger.info(
                        "text_absorbed_by_media",
                        phone=phone_number,
                        agent_id=agent_id,
                    )

                janela = _resolver_janela(
                    buffer_seconds=buffer_seconds,
                    grouping_seconds=grouping_seconds,
                    is_guided_flow=is_guided_flow,
                )
                process_after_midia = _com_teto(
                    janela, inicio_do_lote, grouping_max_seconds
                )

            cursor = await conn.execute(
                """
                INSERT INTO message_queue
                    (empresa_id, conexao_id, atendimento_id, message_id,
                     phone_number, to_number, agent_id, thread_id,
                     incoming_message, media_url, media_type, process_after)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    empresa_id,
                    conexao_id,
                    atendimento_id,
                    message_id,
                    phone_number,
                    to_number,
                    agent_id,
                    thread_id,
                    body,
                    media_url,
                    media_type,
                    process_after_midia,
                ),
            )
            row = await cursor.fetchone()
            assert row is not None
            new_id = row[0]
            await conn.commit()

            logger.info(
                "media_message_enqueued",
                message_id=new_id,
                phone=phone_number,
                agent_id=agent_id,
            )
            return EnqueueResult(message_id=new_id, is_buffered=False)

        # Texto: debounce normal (agrupa com texto pendente se existir)
        janela = _resolver_janela(
            buffer_seconds=buffer_seconds,
            grouping_seconds=grouping_seconds,
            is_guided_flow=is_guided_flow,
        )

        # Busca texto pendente para debounce (media_url IS NULL garante
        # que não debounce texto dentro de uma mensagem de mídia)
        cursor = await conn.execute(
            """
            SELECT id, incoming_message, created_at
            FROM message_queue
            WHERE phone_number = %s
              AND agent_id = %s
              AND status = 'queued'
              AND process_after > NOW()
              AND media_url IS NULL
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (phone_number, agent_id),
        )
        existing = await cursor.fetchone()

        if existing:
            # Debounce: concatena texto e estende o timer — mas o teto conta da
            # criação DESTA row, que é a primeira mensagem do lote.
            existing_id, existing_body, existing_created_at = existing
            new_body = f"{existing_body}\n{body}"
            process_after = _com_teto(janela, existing_created_at, grouping_max_seconds)

            await conn.execute(
                """
                UPDATE message_queue
                SET incoming_message = %s,
                    process_after = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (new_body, process_after, existing_id),
            )
            await conn.commit()

            logger.info(
                "message_buffered",
                message_id=existing_id,
                phone=phone_number,
                agent_id=agent_id,
            )
            return EnqueueResult(message_id=existing_id, is_buffered=True)

        # Nova mensagem de texto na fila. Esta row ABRE o lote, então o teto
        # coincide com a janela e só passa a morder nos merges seguintes.
        process_after = _com_teto(janela, datetime.now(UTC), grouping_max_seconds)
        cursor = await conn.execute(
            """
            INSERT INTO message_queue
                (empresa_id, conexao_id, atendimento_id, message_id,
                 phone_number, to_number, agent_id, thread_id,
                 incoming_message, media_url, media_type, process_after)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (
                empresa_id,
                conexao_id,
                atendimento_id,
                message_id,
                phone_number,
                to_number,
                agent_id,
                thread_id,
                body,
                None,
                None,
                process_after,
            ),
        )
        row = await cursor.fetchone()
        assert row is not None
        new_id = row[0]
        await conn.commit()

        logger.info(
            "message_enqueued",
            message_id=new_id,
            phone=phone_number,
            agent_id=agent_id,
        )
        return EnqueueResult(message_id=new_id, is_buffered=False)


async def claim_next(
    pool: AsyncConnectionPool,
    lease_seconds: int = 60,
) -> MessageQueue | None:
    """Busca e reserva a próxima mensagem pronta para processamento.

    Usa FOR UPDATE SKIP LOCKED para concorrência segura entre múltiplos workers.
    Só retorna mensagens com process_after <= NOW() (debounce concluído) e
    dentro do limite de tentativas.

    Sprint A.2.6: cross-tenant por design (worker precisa ver fila de TODAS
    as empresas). Caller (`worker/consumer.py::claim_next_message`) deve
    envolver em `empresa_scope(None, bypass=True)`. Mantemos essa função
    sem bypass embutido pra que tests com mock de pool não precisem mexer
    em contextvars globais.

    Args:
        pool: Pool de conexões do psycopg.
        lease_seconds: Segundos de lock para o worker processar.

    Returns:
        MessageQueue se houver mensagem disponível, None caso contrário.
    """
    lease_until = datetime.now(UTC) + timedelta(seconds=lease_seconds)

    async with pool.connection() as conn:
        # Evita mensagens presas eternamente em processing após crash:
        # se o lease expirou e não há mais tentativas, marca como failed.
        await conn.execute(
            """
            UPDATE message_queue
            SET status = 'failed',
                error = COALESCE(
                    error,
                    'Processing lease expired after max attempts'
                ),
                processed_at = NOW(),
                updated_at = NOW()
            WHERE status = 'processing'
              AND lease_until IS NOT NULL
              AND lease_until <= NOW()
              AND attempts >= max_attempts
            """
        )

        cursor = await conn.execute(
            """
            UPDATE message_queue
            SET status = 'processing',
                lease_until = %s,
                attempts = attempts + 1,
                updated_at = NOW()
            WHERE id = (
                SELECT id FROM message_queue
                WHERE (
                    status = 'queued'
                    AND process_after <= NOW()
                    AND attempts < max_attempts
                )
                OR (
                    status = 'processing'
                    AND lease_until IS NOT NULL
                    AND lease_until <= NOW()
                    AND attempts < max_attempts
                )
                ORDER BY created_at ASC
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            )
            RETURNING id, empresa_id, atendimento_id, message_id, phone_number,
                      to_number, agent_id, thread_id, incoming_message,
                      media_url, media_type, normalized_input,
                      media_processing_status, media_processing_error,
                      status, process_after, attempts, max_attempts,
                      lease_until, response, error,
                      created_at, updated_at, processed_at,
                      conexao_id,
                      (
                          SELECT provider FROM conexao
                          WHERE id = message_queue.conexao_id
                      ) AS conexao_provider
            """,
            (lease_until,),
        )
        row = await cursor.fetchone()
        await conn.commit()

        if row is None:
            return None

        message = MessageQueue(
            id=row[0],
            empresa_id=row[1],
            atendimento_id=row[2],
            message_id=row[3],
            phone_number=row[4],
            to_number=row[5],
            agent_id=row[6],
            thread_id=row[7],
            incoming_message=row[8],
            media_url=row[9],
            media_type=row[10],
            normalized_input=row[11],
            media_processing_status=row[12],
            media_processing_error=row[13],
            status=row[14],
            process_after=row[15],
            attempts=row[16],
            max_attempts=row[17],
            lease_until=row[18],
            response=row[19],
            error=row[20],
            created_at=row[21],
            updated_at=row[22],
            processed_at=row[23],
            conexao_id=row[24],
            conexao_provider=row[25],
        )

        logger.info(
            "message_claimed",
            message_id=message.id,
            phone=message.phone_number,
            agent_id=message.agent_id,
            attempt=message.attempts,
        )
        return message


async def renew_lease(
    pool: AsyncConnectionPool,
    message_id: int,
    attempts: int,
    lease_seconds: int,
) -> bool:
    """Renova o lease de uma mensagem em processamento (R7 — fencing de lease).

    Estende `lease_until` enquanto o worker ainda processa, pra que uma
    invocação longa do agente (> lease: IA + mídia + guardrails) NÃO dispare
    reclaim por outro worker — o que geraria resposta DUPLICADA ao cliente em
    deploy multi-worker. O fence por `attempts` garante que só o dono atual do
    claim renova: se outro worker já reivindicou (attempts incrementado pelo
    claim dele), o UPDATE não afeta nenhuma linha e retornamos False.

    Returns:
        True se renovou (ainda é o dono do lease); False se perdeu (reclaimado).
    """
    async with pool.connection() as conn:
        cursor = await conn.execute(
            """
            UPDATE message_queue
            SET lease_until = NOW() + make_interval(secs => %s),
                updated_at = NOW()
            WHERE id = %s
              AND attempts = %s
              AND status = 'processing'
            RETURNING id
            """,
            (lease_seconds, message_id, attempts),
        )
        row = await cursor.fetchone()
        await conn.commit()
    return row is not None


async def mark_done(
    pool: AsyncConnectionPool,
    message_id: int,
    response: str,
    normalized_input: str | None = None,
    media_processing_status: str | None = None,
    media_processing_error: str | None = None,
    origem_resposta: str | None = None,
) -> None:
    """Marca mensagem como processada com sucesso.

    Args:
        pool: Pool de conexões do psycopg.
        message_id: ID da mensagem na fila.
        response: Resposta gerada pelo agente.
        normalized_input: Texto normalizado enviado ao agente.
        media_processing_status: Resultado do pré-processamento de mídia.
        media_processing_error: Erro do pré-processamento de mídia, se houver.
        origem_resposta: Quem produziu a resposta — `agente`, `menu`,
            `workflow`, `coleta`, `csat` ou `opt_out` (mig 144). É o que permite
            ao enqueue reconhecer fluxo guiado e não alongar a janela ali.
            None quando não houve resposta automática (whitelist, modo manual).
    """
    async with pool.connection() as conn:
        await conn.execute(
            """
            UPDATE message_queue
            SET status = 'done',
                response = %s,
                normalized_input = COALESCE(%s, normalized_input),
                media_processing_status = COALESCE(%s, media_processing_status),
                media_processing_error = COALESCE(%s, media_processing_error),
                origem_resposta = %s,
                processed_at = NOW(),
                updated_at = NOW()
            WHERE id = %s
            """,
            (
                response,
                normalized_input,
                media_processing_status,
                media_processing_error,
                origem_resposta,
                message_id,
            ),
        )
        await conn.commit()

    logger.info("message_done", message_id=message_id)


async def mark_failed(
    pool: AsyncConnectionPool,
    message_id: int,
    error: str,
) -> None:
    """Marca mensagem como falha.

    Se ainda tem tentativas restantes, volta para 'queued' para retry.
    Caso contrário, marca como 'failed' definitivamente.

    Args:
        pool: Pool de conexões do psycopg.
        message_id: ID da mensagem na fila.
        error: Descrição do erro.
    """
    async with pool.connection() as conn:
        # Verifica se ainda tem tentativas
        cursor = await conn.execute(
            "SELECT attempts, max_attempts FROM message_queue WHERE id = %s",
            (message_id,),
        )
        row = await cursor.fetchone()

        if row and row[0] < row[1]:
            # Ainda tem tentativas: volta para a fila com backoff progressivo
            # Cada tentativa espera attempts * 5s antes de ser reprocessada
            backoff_seconds = row[0] * 5
            next_retry_at = datetime.now(UTC) + timedelta(seconds=backoff_seconds)
            await conn.execute(
                """
                UPDATE message_queue
                SET status = 'queued',
                    error = %s,
                    lease_until = NULL,
                    process_after = NOW() + make_interval(secs => %s),
                    updated_at = NOW()
                WHERE id = %s
                """,
                (error, backoff_seconds, message_id),
            )
            logger.warning(
                "message_retry",
                message_id=message_id,
                attempt=row[0],
                max_attempts=row[1],
                backoff_seconds=backoff_seconds,
                next_retry_at=next_retry_at.isoformat(),
                error=error,
            )
        else:
            # Sem tentativas: falha definitiva
            await conn.execute(
                """
                UPDATE message_queue
                SET status = 'failed',
                    error = %s,
                    processed_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
                """,
                (error, message_id),
            )
            logger.error(
                "message_failed",
                message_id=message_id,
                error=error,
            )

        await conn.commit()


async def upsert_conversation(
    pool: AsyncConnectionPool,
    phone_number: str,
    agent_id: str,
    last_message: str,
    empresa_id: int = 1,
) -> None:
    """Atualiza ou cria registro de conversa (escopado por empresa).

    Usado após cada mensagem processada para manter o histórico
    de conversas atualizado (para o painel admin).
    """
    thread_id = f"{phone_number}:{agent_id}"

    async with pool.connection() as conn:
        await conn.execute(
            """
            INSERT INTO conversations (
                empresa_id, phone_number, agent_id, thread_id,
                last_message, last_message_at, message_count)
            VALUES (%s, %s, %s, %s, %s, NOW(), 1)
            ON CONFLICT (phone_number, agent_id) DO UPDATE SET
                last_message = EXCLUDED.last_message,
                last_message_at = NOW(),
                message_count = conversations.message_count + 1,
                updated_at = NOW()
            """,
            (empresa_id, phone_number, agent_id, thread_id, last_message),
        )
        await conn.commit()


async def reset_thread_checkpoint(pool, phone_number: str, agent_id: str) -> int:
    """Apaga o checkpoint LangGraph do thread (phone:agent).

    Usado quando o agente "decora" um pattern errado nas últimas N
    mensagens (ex: respondeu "não tenho info" sem chamar tool, e o
    modelo passa a replicar). Limpar o checkpoint força próxima
    mensagem a começar do zero com prompt + tools atuais.

    Não toca em:
    - `message_queue` (histórico de mensagens enfileiradas)
    - `conversations` (resumo pra UI)
    - `langgraph.store` (memórias semânticas cross-thread)
    - `cliente_memoria` (memória estruturada por cliente)

    Retorna o total de rows removidas (somando as 3 tabelas LangGraph).
    """
    thread_id = f"{phone_number}:{agent_id}"
    total = 0
    async with pool.connection() as conn:
        for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
            cur = await conn.execute(
                f"DELETE FROM {table} WHERE thread_id = %s",
                (thread_id,),
            )
            total += cur.rowcount or 0
        await conn.commit()
    return total
