"""Conversa ativa 1:1 — operador inicia contato com um número (mig 170).

Até aqui atendimento só nascia de mensagem inbound no webhook. Este módulo
orquestra o caminho outbound-first (paridade ZigChat `criarAlterarAtendimento`):
compliance do disparo (opt-out + teto diário anti-ban) → upsert do cliente →
atendimento nascendo ATRIBUÍDO ao operador (`iniciado_cliente=False`; o gate
de handoff do worker cala a IA) → primeira mensagem (texto no Evolution,
template HSM aprovado em WABA — a "janela de 24h" aqui é régua por
provider, não cálculo temporal).

A whitelist ("números sem IA") NÃO bloqueia: ela cala respostas AUTOMÁTICAS;
contato iniciado por humano é exatamente o caso de uso dela.
"""

from __future__ import annotations

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.atendimento import open_or_attach_atendimento
from whatsapp_langchain.shared.campanha import normalize_phone
from whatsapp_langchain.shared.cliente import upsert_cliente
from whatsapp_langchain.shared.conexao import get_conexao_by_id, get_conexao_padrao
from whatsapp_langchain.shared.conexao_quota import incr_uso_hoje, quota_status
from whatsapp_langchain.shared.models import Atendimento
from whatsapp_langchain.shared.opt_out import telefones_suprimidos
from whatsapp_langchain.shared.outbound import (
    send_outbound_manual,
    send_template_by_id,
)

logger = structlog.get_logger()


class ConversaAtivaError(Exception):
    """Erro de negócio com frase pt-BR acionável e status HTTP sugerido."""

    def __init__(self, mensagem: str, status: int = 400) -> None:
        super().__init__(mensagem)
        self.status = status


async def iniciar_conversa(
    pool: AsyncConnectionPool,
    *,
    empresa_id: int,
    user_id: str,
    conexao_id: int | None,
    telefone: str,
    mensagem: str | None = None,
    template_id: int | None = None,
    variaveis: dict[str, str] | None = None,
    nome: str | None = None,
) -> tuple[Atendimento, bool]:
    """Inicia (ou continua) uma conversa ativa e envia a primeira mensagem.

    Retorna `(atendimento, was_created)`. Se já existia atendimento aberto para
    (cliente, conexão), anexa a ele — sem roubar o dono — e só envia a mensagem
    (semântica `continuar_atendimento` do ZigChat).

    Falha no ENVIO com atendimento recém-criado desfaz o atendimento órfão:
    conversa vazia na fila é pior que o erro na cara do operador, que pode
    corrigir e tentar de novo.
    """
    tel = normalize_phone(telefone)
    if tel is None:
        raise ConversaAtivaError("Telefone inválido. Informe DDD e número.")

    # Sem conexão escolhida, o servidor usa a padrão da empresa — a tela não
    # pergunta "por qual número?" toda vez; quem quiser trocar marca outra
    # como padrão em /connections.
    if conexao_id is None:
        conexao = await get_conexao_padrao(pool, empresa_id)
        if conexao is None:
            raise ConversaAtivaError("Nenhuma conexão ativa nesta empresa.", status=409)
        conexao_id = conexao.id
    else:
        conexao = await get_conexao_by_id(pool, conexao_id)
    if conexao is None or conexao.empresa_id != empresa_id:
        raise ConversaAtivaError("Conexão não encontrada.", status=404)
    if conexao.status != "active":
        raise ConversaAtivaError("Esta conexão está desativada.", status=409)

    eh_template = conexao.provider == "waba"
    if eh_template and not template_id:
        raise ConversaAtivaError(
            "Esta conexão exige um template aprovado para iniciar conversa."
        )
    if not eh_template and not (mensagem or "").strip():
        raise ConversaAtivaError("Escreva a primeira mensagem.")

    # Compliance do disparo, reusada: quem pediu pra não receber, não recebe —
    # nem de campanha, nem de contato "manual".
    if await telefones_suprimidos(pool, empresa_id, [tel]):
        raise ConversaAtivaError(
            "Esse número pediu para não receber mensagens (opt-out).",
            status=409,
        )
    quota = await quota_status(pool, conexao)
    if quota.restante is not None and quota.restante <= 0:
        raise ConversaAtivaError(
            f"Teto diário de envios desta conexão atingido ({quota.motivo}). "
            "Tente amanhã ou use outra conexão.",
            status=409,
        )

    cliente = await upsert_cliente(pool, empresa_id, tel, nome=nome)
    atendimento, was_created = await open_or_attach_atendimento(
        pool,
        empresa_id,
        cliente.id,
        conexao_id,
        agente=conexao.default_agent_id or "vsa_tech",
        conexao=conexao,
        iniciado_cliente=False,
        assigned_to_user_id=user_id,
    )

    try:
        if eh_template:
            assert template_id is not None
            await send_template_by_id(
                pool,
                conexao_id=conexao_id,
                empresa_id=empresa_id,
                to=tel,
                template_id=template_id,
                variables=variaveis,
                atendimento_id=atendimento.id,
                user_id=user_id,
            )
        else:
            assert mensagem is not None
            await send_outbound_manual(
                pool,
                atendimento_id=atendimento.id,
                empresa_id=empresa_id,
                user_id=user_id,
                conteudo=mensagem.strip(),
            )
    except Exception as e:
        if was_created:
            async with pool.connection() as conn:
                await conn.execute(
                    "DELETE FROM atendimento WHERE id = %s AND empresa_id = %s",
                    (atendimento.id, empresa_id),
                )
        logger.warning(
            "conversa_ativa_envio_falhou",
            empresa_id=empresa_id,
            conexao_id=conexao_id,
            atendimento_id=atendimento.id,
            desfeito=was_created,
            erro=type(e).__name__,
        )
        raise ConversaAtivaError(
            f"Não foi possível enviar a mensagem: {e}", status=502
        ) from e

    async with pool.connection() as conn:
        await incr_uso_hoje(conn, empresa_id, conexao_id)

    logger.info(
        "conversa_ativa_iniciada",
        empresa_id=empresa_id,
        atendimento_id=atendimento.id,
        conexao_id=conexao_id,
        was_created=was_created,
        via_template=eh_template,
        actor_user_id=user_id,
    )
    return atendimento, was_created
