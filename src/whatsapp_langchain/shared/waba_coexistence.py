"""WhatsApp Coexistence — o que chega do WhatsApp Business do celular (mig 200).

Coexistence é um MODO do provider `waba` (`conexao.waba_mode`): o cliente
continua usando o WhatsApp Business no celular e o ChatNexus recebe/responde
pela Cloud API. A Meta entrega pelo mesmo `/webhook/waba` três campos a mais:

- `smb_message_echoes` — o que a empresa mandou pelo celular. Vira linha de
  SAÍDA `done` na timeline (`manual:app:…`, origem `whatsapp_business_app`) e
  **pausa a IA** até alguém clicar "Devolver à IA" (decisão do dono, 22/09):
  o atendimento fica `em_andamento` com o dono sentinela `HUMANO_APP`, e o gate
  de handoff do worker (`worker/processor.py`) cala o agente — o mesmo
  mecanismo do "Atender" do painel, sem regra nova de retomada.
- `history` — até 180 dias de conversas, **só texto**, num atendimento já
  `resolvido` por cliente ("histórico importado"), sem abrir conversa na fila.
- `smb_app_state_sync` — contatos do celular → `upsert_cliente(nome)`.

Nada daqui passa por `enqueue_or_buffer`: tudo entra `status='done'`, que o
`claim_next` nunca pega. É o backend que garante "sem IA", não o prompt.
"""

from __future__ import annotations

from typing import Final

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.integrations.waba.models import (
    WabaAccountUpdate,
    WabaContato,
    WabaEcho,
    WabaHistoricoLote,
)
from whatsapp_langchain.integrations.waba.webhook import ERRO_HISTORICO_RECUSADO
from whatsapp_langchain.shared.atendimento import (
    claim_atendimento,
    open_or_attach_atendimento,
)
from whatsapp_langchain.shared.cliente import upsert_cliente
from whatsapp_langchain.shared.conexao import (
    list_conexoes_by_waba_account_id,
    record_health_check,
    set_connection_state,
)
from whatsapp_langchain.shared.models import Conexao
from whatsapp_langchain.shared.outbound import _persist_outbound_row

logger = structlog.get_logger()

#: Dono sentinela do atendimento quando a empresa respondeu pelo celular.
#: `assigned_to_user_id` não tem FK nem CHECK e toda leitura é LEFT JOIN no
#: `auth."user"` — a conversa não some das listas; a tela mostra o rótulo.
HUMANO_APP: Final = "whatsapp_business_app"

#: `origem_resposta` (mig 144) das linhas vindas do app.
ORIGEM_APP: Final = "whatsapp_business_app"

#: `user_id` do `_persist_outbound_row` → `normalized_input='manual:app:…'`.
#: A timeline mostra "WhatsApp Business (celular)" para o prefixo `manual:app:`.
USUARIO_APP: Final = "app:whatsapp_business"
USUARIO_APP_HISTORICO: Final = "app:historico"

#: `normalized_input` das linhas de CLIENTE importadas do histórico. Fica fora
#: do predicado de "recebida" da saúde das conexões e do push do app.
MARCA_HISTORICO_INBOUND: Final = "historico:whatsapp_business_app"

MSG_HISTORICO_RECUSADO: Final = (
    "O histórico de conversas não foi compartilhado no WhatsApp Business."
)

_ROTULO_MIDIA: Final = {
    "image": "imagem",
    "video": "vídeo",
    "document": "documento",
    "audio": "áudio",
    "sticker": "figurinha",
}


def texto_do_eco(eco: WabaEcho) -> str | None:
    """Texto que vai para a timeline. None = eco que não vira bolha.

    Mídia (v1): a legenda + a indicação do tipo — os bytes ficam para depois.
    `revoke`/`edit` e tipos desconhecidos sem texto: só log.
    """
    rotulo = _ROTULO_MIDIA.get(eco.type)
    if rotulo:
        aviso = f"[{rotulo} enviado pelo celular]"
        return f"{eco.text}\n{aviso}" if eco.text else aviso
    return eco.text or None


async def registrar_eco(pool: AsyncConnectionPool, conexao: Conexao, eco: WabaEcho):
    """Grava o eco como saída do operador e pausa a IA daquela conversa.

    Devolve o `Atendimento` usado, ou None quando o eco não vira bolha.
    """
    texto = texto_do_eco(eco)
    if texto is None:
        logger.info(
            "waba_coexistence_echo_ignorado",
            conexao_id=conexao.id,
            tipo=eco.type,
        )
        return None

    cliente = await upsert_cliente(pool, conexao.empresa_id, eco.to_number)
    atendimento, criado = await open_or_attach_atendimento(
        pool,
        empresa_id=conexao.empresa_id,
        cliente_id=cliente.id,
        conexao_id=conexao.id,
        agente=conexao.default_agent_id,
        conexao=conexao,
        iniciado_cliente=False,
        assigned_to_user_id=HUMANO_APP,
    )
    # Anexar a um atendimento aberto não troca o dono (regra do
    # open_or_attach). Sem dono = com a IA → a empresa assumiu pelo celular.
    # Com um operador do painel → fica com ele.
    if not criado and not atendimento.assigned_to_user_id:
        atendimento = await claim_atendimento(pool, atendimento.id, HUMANO_APP) or (
            atendimento
        )

    await _persist_outbound_row(
        pool,
        empresa_id=conexao.empresa_id,
        conexao_id=conexao.id,
        atendimento_id=atendimento.id,
        phone_number=eco.to_number,
        agent_id=conexao.default_agent_id,
        response=texto,
        user_id=USUARIO_APP,
        provider_message_id=eco.message_id,
        origem_resposta=ORIGEM_APP,
    )
    logger.info(
        "waba_coexistence_echo_received",
        conexao_id=conexao.id,
        empresa_id=conexao.empresa_id,
        atendimento_id=atendimento.id,
        tipo=eco.type,
        ia_pausada=atendimento.assigned_to_user_id == HUMANO_APP,
    )
    return atendimento


async def sincronizar_contato(
    pool: AsyncConnectionPool, conexao: Conexao, contato: WabaContato
) -> bool:
    """Contato do celular → cliente. Só `add` (a edição chega como `add`).

    `upsert_cliente` nunca sobrescreve nome já preenchido — o que o operador
    editou no painel continua valendo.
    """
    if contato.action != "add":
        return False
    await upsert_cliente(
        pool, conexao.empresa_id, contato.phone_number, nome=contato.nome
    )
    return True


async def importar_historico(
    pool: AsyncConnectionPool, conexao: Conexao, lote: WabaHistoricoLote
) -> int:
    """Importa um lote do histórico (só texto). Devolve quantas linhas entraram.

    Cada conversa vai para UM atendimento `resolvido` por cliente e conexão
    (o dono e quem fechou = `HUMANO_APP`), criado direto — `open_or_attach`
    abriria conversa na fila. A deduplicação por wamid acontece na MESMA
    transação que grava as linhas: reentrega do lote não duplica, e falha no
    meio não deixa wamid marcado sem a mensagem.
    """
    if ERRO_HISTORICO_RECUSADO in lote.erros:
        await set_connection_state(
            pool,
            conexao.id,
            state=conexao.connection_state,
            message=MSG_HISTORICO_RECUSADO,
        )
        logger.info(
            "waba_coexistence_history_recusado",
            conexao_id=conexao.id,
            empresa_id=conexao.empresa_id,
        )
        return 0

    total = 0
    for conversa in lote.conversas:
        mensagens = [m for m in conversa.mensagens if m.text and m.message_id]
        if not mensagens:
            continue
        cliente = await upsert_cliente(
            pool, conexao.empresa_id, conversa.cliente_number
        )
        total += await _gravar_conversa_historico(
            pool, conexao, cliente.id, conversa.cliente_number, mensagens
        )

    logger.info(
        "waba_coexistence_history_received",
        conexao_id=conexao.id,
        empresa_id=conexao.empresa_id,
        phase=lote.phase,
        chunk_order=lote.chunk_order,
        progress=lote.progress,
        conversas=len(lote.conversas),
        importadas=total,
    )
    return total


async def _gravar_conversa_historico(
    pool: AsyncConnectionPool,
    conexao: Conexao,
    cliente_id: int,
    telefone: str,
    mensagens: list,
) -> int:
    agente = conexao.default_agent_id
    thread_id = f"{telefone}:{agente}"
    mensagens = sorted(mensagens, key=lambda m: m.timestamp)
    async with pool.connection() as conn:
        async with conn.transaction():
            cur = await conn.execute(
                "INSERT INTO waba_wamid_processado (wamid)"
                " SELECT unnest(%s::text[])"
                " ON CONFLICT (wamid) DO NOTHING RETURNING wamid",
                ([m.message_id for m in mensagens],),
            )
            novos = {r[0] for r in await cur.fetchall()}
            mensagens = [m for m in mensagens if m.message_id in novos]
            if not mensagens:
                return 0

            atendimento_id = await _atendimento_historico(
                conn, conexao, cliente_id, mensagens
            )
            for m in mensagens:
                await conn.execute(
                    """
                    INSERT INTO message_queue
                        (empresa_id, conexao_id, atendimento_id, message_id,
                         phone_number, agent_id, thread_id,
                         incoming_message, response, normalized_input,
                         origem_resposta, status, created_at, process_after,
                         processed_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            'done', %s, %s, %s)
                    """,
                    (
                        conexao.empresa_id,
                        conexao.id,
                        atendimento_id,
                        m.message_id,
                        telefone,
                        agente,
                        thread_id,
                        "" if m.da_empresa else m.text,
                        m.text if m.da_empresa else None,
                        (
                            f"manual:{USUARIO_APP_HISTORICO}"
                            if m.da_empresa
                            else MARCA_HISTORICO_INBOUND
                        ),
                        ORIGEM_APP if m.da_empresa else None,
                        m.timestamp,
                        m.timestamp,
                        m.timestamp,
                    ),
                )
    return len(mensagens)


async def _atendimento_historico(conn, conexao: Conexao, cliente_id: int, mensagens):
    """Atendimento `resolvido` do histórico deste cliente — reusa ou cria."""
    primeira, ultima = mensagens[0].timestamp, mensagens[-1].timestamp
    cur = await conn.execute(
        """
        SELECT id FROM atendimento
         WHERE empresa_id = %s AND cliente_id = %s AND conexao_id = %s
           AND status = 'resolvido' AND finalizado_por_user_id = %s
         ORDER BY id LIMIT 1
         FOR UPDATE
        """,
        (conexao.empresa_id, cliente_id, conexao.id, HUMANO_APP),
    )
    row = await cur.fetchone()
    if row:
        await conn.execute(
            """
            UPDATE atendimento
               SET created_at = LEAST(created_at, %s),
                   last_message_at = GREATEST(COALESCE(last_message_at, %s), %s),
                   updated_at = NOW()
             WHERE id = %s
            """,
            (primeira, ultima, ultima, row[0]),
        )
        return row[0]
    cur = await conn.execute(
        """
        INSERT INTO atendimento
            (empresa_id, cliente_id, conexao_id, agente_atual,
             conexao_nome, conexao_numero, conexao_provider,
             iniciado_cliente, assigned_to_user_id, finalizado_por_user_id,
             status, created_at, last_message_at, closed_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, FALSE, %s, %s,
                'resolvido', %s, %s, %s)
        RETURNING id
        """,
        (
            conexao.empresa_id,
            cliente_id,
            conexao.id,
            conexao.default_agent_id,
            conexao.display_name,
            conexao.from_number,
            conexao.provider,
            HUMANO_APP,
            HUMANO_APP,
            primeira,
            ultima,
            ultima,
        ),
    )
    novo = await cur.fetchone()
    assert novo is not None
    return novo[0]


async def processar_account_update(
    pool: AsyncConnectionPool, evento: WabaAccountUpdate
) -> int:
    """`PARTNER_REMOVED` → conexão desconectada. Devolve quantas mudaram.

    O monitor de saúde (mig 196) e o banner de conexão já avisam a partir do
    `connection_state` + `ultimo_health_check_ok`. Outros eventos: só log.
    """
    if evento.event != "PARTNER_REMOVED":
        logger.info("waba_coexistence_account_update", evento=evento.event)
        return 0
    from whatsapp_langchain.shared.rls_context import set_request_context

    alteradas = 0
    for conexao in await list_conexoes_by_waba_account_id(pool, evento.waba_account_id):
        if evento.phone_number and conexao.from_number != evento.phone_number:
            continue
        set_request_context(conexao.empresa_id)
        motivo = "Desconectado no WhatsApp Business"
        if evento.reason:
            motivo += f" ({_motivo_desconexao(evento.reason)})"
        await set_connection_state(
            pool, conexao.id, state="disconnected", message=motivo + "."
        )
        await record_health_check(pool, conexao.id, ok=False, message=motivo + ".")
        alteradas += 1
        logger.warning(
            "waba_coexistence_account_update",
            evento=evento.event,
            conexao_id=conexao.id,
            empresa_id=conexao.empresa_id,
            reason=evento.reason,
            initiated_by=evento.initiated_by,
        )
    return alteradas


_MOTIVOS: Final = {
    "PRIMARY_INACTIVITY": "o celular ficou muito tempo sem uso",
}


def _motivo_desconexao(reason: str) -> str:
    return _MOTIVOS.get(
        reason, "motivo informado pela Meta: " + reason.replace("_", " ").lower()
    )
