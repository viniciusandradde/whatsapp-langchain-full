"""Convite de acesso por WhatsApp — link de definição de senha, não a senha.

O admin cria o usuário e, em vez de copiar a senha gerada e repassar à mão
(o fluxo de hoje, que deixa a senha viva no histórico da conversa para
sempre), manda um link de uso único que expira em 1h — o fluxo de reset do
Better Auth (mig 025), que já existia e estava órfão de tela.

Molde de `resumo_diario._enviar`: conexão ativa da empresa →
`build_outbound_client` → `send_message`. Sem atendimento, sem linha em
`message_queue` — mensagem de sistema, não conversa.

REGRA DE OURO DESTE MÓDULO: **o link nunca entra em log** — nem em
`logger.info`, nem em exceção, nem na auditoria. Quem tem o link define a
senha da conta. A auditoria grava PARA QUAL NÚMERO foi, nunca o quê.
"""

from __future__ import annotations

from datetime import datetime

import structlog
from psycopg_pool import AsyncConnectionPool

from whatsapp_langchain.shared.rls_context import empresa_scope

logger = structlog.get_logger()


class ConviteError(Exception):
    """Falha de convite com mensagem legível para a tela.

    A mensagem NUNCA contém o link — pode (e vai) aparecer em log e em toast.
    """


def _formatar_prazo(expira_em: datetime) -> str:
    """'23:59' no fuso de Campo Grande — prazo curto merece hora, não data."""
    try:
        from zoneinfo import ZoneInfo

        local = expira_em.astimezone(ZoneInfo("America/Campo_Grande"))
        return local.strftime("%H:%M")
    except Exception:  # noqa: BLE001 — fuso é cosmético, não pode derrubar envio
        return expira_em.strftime("%H:%M UTC")


def montar_mensagem(
    *,
    nome: str,
    email: str | None,
    painel_url: str,
    link: str,
    expira_em: datetime,
) -> str:
    """Texto do convite. Curto, com o essencial: quem, onde, o link, o prazo,
    o E-MAIL de login e o pedido de não repassar — o link é a chave da conta.

    O e-mail entra por escrito porque foi o admin quem o escolheu — a pessoa
    não tem como adivinhar com qual endereço entrar (validado no primeiro
    envio real: o convidado criou a senha e parou no login sem saber o
    e-mail). E-mail sintético `@no-email.local` não é digitável por humano —
    nesse caso a linha sai e fica só "seu e-mail", como antes.
    """
    primeiro_nome = (nome or "").strip().split(" ")[0] or "Olá"
    prazo = _formatar_prazo(expira_em)
    email_limpo = (email or "").strip()
    if email_limpo and not email_limpo.endswith("@no-email.local"):
        linha_login = (
            f"Depois é só entrar em {painel_url} com o e-mail "
            f"{email_limpo} e a senha que você criou."
        )
    else:
        linha_login = (
            f"Depois é só entrar em {painel_url} com seu e-mail e a "
            f"senha que você criou."
        )
    return (
        f"Olá, {primeiro_nome}! Seu acesso ao painel foi criado.\n\n"
        f"Crie sua senha neste link (vale até as {prazo} de hoje e "
        f"só funciona uma vez):\n{link}\n\n"
        f"{linha_login}\n\n"
        f"Este link dá acesso à sua conta — não repasse para ninguém."
    )


async def enviar_convite(
    pool: AsyncConnectionPool,
    *,
    empresa_id: int,
    user_id: str,
    link: str,
    expira_em: datetime,
    painel_url: str,
) -> str:
    """Envia o convite no WhatsApp do usuário. Devolve o número de destino.

    Levanta `ConviteError` (mensagem legível, sem link) quando não há como
    enviar: usuário sem telefone, empresa sem conexão ativa, provedor recusou.
    Sucesso grava `auth."user".convite_enviado_at` (mig 167).
    """
    from whatsapp_langchain.shared.conexao import list_conexoes
    from whatsapp_langchain.shared.outbound import build_outbound_client

    async with pool.connection() as conn:
        cur = await conn.execute(
            'SELECT name, telefone, email FROM auth."user" WHERE id = %s',
            (user_id,),
        )
        row = await cur.fetchone()
    if row is None:
        raise ConviteError("Usuário não encontrado.")
    nome, telefone, email = row[0] or "", (row[1] or "").strip(), row[2]
    if not telefone:
        raise ConviteError(
            "O usuário não tem WhatsApp cadastrado. Preencha o telefone "
            "com DDD no cadastro e tente de novo."
        )

    with empresa_scope(empresa_id):
        conexoes = await list_conexoes(pool, empresa_id)
    ativas = [c for c in conexoes if c.status == "active"]
    if not ativas:
        raise ConviteError(
            "A empresa não tem conexão de WhatsApp ativa para enviar o "
            "convite. Compartilhe a senha pelo canal que preferir."
        )

    texto = montar_mensagem(
        nome=nome,
        email=email,
        painel_url=painel_url,
        link=link,
        expira_em=expira_em,
    )

    conexao = ativas[0]  # list_conexoes ordena is_default DESC
    try:
        with empresa_scope(empresa_id):
            client, _mode = await build_outbound_client(pool, conexao)
            await client.send_message(telefone, texto)
    except Exception as exc:
        # str(exc) aqui é seguro: o link não participa da exceção do
        # provedor. O texto da mensagem NÃO entra no raise.
        raise ConviteError(
            f"O WhatsApp recusou o envio ({type(exc).__name__}). "
            f"Confira se o número {telefone} existe no WhatsApp."
        ) from exc

    async with pool.connection() as conn:
        await conn.execute(
            'UPDATE auth."user" SET convite_enviado_at = NOW() WHERE id = %s',
            (user_id,),
        )
        await conn.commit()

    logger.info(
        "convite_acesso_enviado",
        user_id=user_id,
        empresa_id=empresa_id,
        conexao_id=conexao.id,
        telefone=telefone,
        # o link NUNCA aparece aqui — regra de ouro do módulo
    )
    return telefone
