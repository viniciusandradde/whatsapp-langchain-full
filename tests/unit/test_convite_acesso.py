"""Convite de acesso por WhatsApp — mensagem e caminhos de falha.

A regra de ouro do módulo está testada aqui: **o link nunca vaza** para
exceção nem para o texto de erro que a tela mostra. Se um refactor fizer o
link aparecer num `str(exc)`, estes testes quebram antes de produção.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from whatsapp_langchain.shared.convite_acesso import (
    ConviteError,
    enviar_convite,
    montar_mensagem,
)

LINK = "https://painel.example/reset-password?token=SEGREDO-abc123"
EXPIRA = datetime(2026, 8, 13, 22, 30, tzinfo=UTC)


class TestMensagem:
    def test_contem_o_essencial(self) -> None:
        msg = montar_mensagem(
            nome="Maria Souza",
            email="maria@empresa.com.br",
            painel_url="https://painel.example",
            link=LINK,
            expira_em=EXPIRA,
        )
        assert "Maria" in msg  # primeiro nome, não o completo
        assert "Maria Souza" not in msg
        assert LINK in msg
        assert "https://painel.example" in msg
        assert "uma vez" in msg
        assert "não repasse" in msg

    def test_email_de_login_esta_na_mensagem(self) -> None:
        """Aprendido no primeiro envio real: o convidado criou a senha e
        parou no login sem saber COM QUAL e-mail entrar — quem escolheu o
        endereço foi o admin, não ele."""
        msg = montar_mensagem(
            nome="Maria",
            email="maria@empresa.com.br",
            painel_url="https://x",
            link=LINK,
            expira_em=EXPIRA,
        )
        assert "maria@empresa.com.br" in msg

    def test_email_sintetico_fica_de_fora(self) -> None:
        """`user-<uuid>@no-email.local` não é digitável por humano — a linha
        cai no genérico "seu e-mail" em vez de mandar a pessoa digitar isso."""
        msg = montar_mensagem(
            nome="Maria",
            email="user-abc123@no-email.local",
            painel_url="https://x",
            link=LINK,
            expira_em=EXPIRA,
        )
        assert "no-email.local" not in msg
        assert "seu e-mail" in msg

    def test_prazo_no_fuso_local(self) -> None:
        """22:30 UTC = 18:30 em Campo Grande — o prazo tem que ser o local,
        senão a pessoa acha que tem 4h a mais do que tem."""
        msg = montar_mensagem(
            nome="Maria",
            email="m@x.com",
            painel_url="https://x",
            link=LINK,
            expira_em=EXPIRA,
        )
        assert "18:30" in msg
        assert "22:30" not in msg

    def test_nome_vazio_nao_quebra(self) -> None:
        msg = montar_mensagem(
            nome="", email=None, painel_url="https://x", link=LINK, expira_em=EXPIRA
        )
        assert LINK in msg


def _pool_com_user(row):
    cur = AsyncMock()
    cur.fetchone = AsyncMock(return_value=row)
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cur)
    conn.commit = AsyncMock()
    pool = MagicMock()
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool


class TestFalhas:
    async def test_usuario_inexistente(self) -> None:
        with pytest.raises(ConviteError, match="não encontrado"):
            await enviar_convite(
                _pool_com_user(None),
                empresa_id=1,
                user_id="ghost",
                link=LINK,
                expira_em=EXPIRA,
                painel_url="https://x",
            )

    async def test_usuario_sem_telefone(self) -> None:
        with pytest.raises(ConviteError, match="WhatsApp cadastrado") as exc:
            await enviar_convite(
                _pool_com_user(("Maria", None, "m@x.com")),
                empresa_id=1,
                user_id="u1",
                link=LINK,
                expira_em=EXPIRA,
                painel_url="https://x",
            )
        assert LINK not in str(exc.value)

    async def test_empresa_sem_conexao_ativa(self, monkeypatch) -> None:
        from whatsapp_langchain.shared import conexao as m_conexao

        monkeypatch.setattr(m_conexao, "list_conexoes", AsyncMock(return_value=[]))
        with pytest.raises(ConviteError, match="conexão de WhatsApp ativa") as exc:
            await enviar_convite(
                _pool_com_user(("Maria", "+5567999990000", "m@x.com")),
                empresa_id=1,
                user_id="u1",
                link=LINK,
                expira_em=EXPIRA,
                painel_url="https://x",
            )
        assert LINK not in str(exc.value)

    async def test_provedor_recusa_sem_vazar_link(self, monkeypatch) -> None:
        """A exceção do provedor vira ConviteError legível — e mesmo que o
        provedor eco-e o payload no erro dele, o NOSSO raise não carrega o
        texto da mensagem."""
        from whatsapp_langchain.shared import conexao as m_conexao
        from whatsapp_langchain.shared import outbound as m_outbound

        conexao_fake = MagicMock(status="active", id=7)
        monkeypatch.setattr(
            m_conexao, "list_conexoes", AsyncMock(return_value=[conexao_fake])
        )
        client = MagicMock()
        client.send_message = AsyncMock(side_effect=RuntimeError("400 bad"))
        monkeypatch.setattr(
            m_outbound,
            "build_outbound_client",
            AsyncMock(return_value=(client, "real")),
        )
        with pytest.raises(ConviteError, match="recusou o envio") as exc:
            await enviar_convite(
                _pool_com_user(("Maria", "+5567999990000", "m@x.com")),
                empresa_id=1,
                user_id="u1",
                link=LINK,
                expira_em=EXPIRA,
                painel_url="https://x",
            )
        assert LINK not in str(exc.value)
        assert "SEGREDO" not in str(exc.value)


class TestAuditoria:
    def test_acao_registrada_no_catalogo(self) -> None:
        """`member.convite` precisa estar em VALID_ACTIONS — fora dele a
        auditoria grava com warning de typo, e ninguém percebe."""
        from whatsapp_langchain.shared.audit_governanca import VALID_ACTIONS

        assert "member.convite" in VALID_ACTIONS
