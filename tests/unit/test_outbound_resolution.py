"""Resolução de cliente outbound POR-CONEXÃO (sem instance/número "via código").

Após a refatoração "só via UI", o worker monta o cliente de envio a partir da
`conexao` cadastrada (DB), não de env vars. Cobre:

- `_resolve_outbound_client` monta o client a partir da conexão do DB.
- Sem conexão / sem `conexao_id` → `OutboundError` (caller faz `mark_failed`,
  não envia por uma conexão default).
- `build_outbound_client` (Evolution) exige `instance_name` vindo da conexão —
  NÃO cai mais em `EVOLUTION_INSTANCE_NAME` do env.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from whatsapp_langchain.shared.models import MessageQueue
from whatsapp_langchain.shared.outbound import OutboundError


def _msg(conexao_id: int | None) -> MessageQueue:
    return MessageQueue(
        id=1,
        phone_number="+5511999999999",
        agent_id="vsa_tech",
        thread_id="+5511999999999:vsa_tech",
        incoming_message="Olá!",
        conexao_id=conexao_id,
    )


class TestResolveOutboundClientPerConexao:
    """`_resolve_outbound_client` usa a conexão do DB, não config via env."""

    async def test_builds_client_from_conexao(self):
        from whatsapp_langchain.worker.processor import _resolve_outbound_client

        fake_client = AsyncMock()
        fake_conexao = SimpleNamespace(id=7, provider="evolution")
        with (
            patch(
                "whatsapp_langchain.worker.processor.get_conexao_by_id",
                new=AsyncMock(return_value=fake_conexao),
            ),
            patch(
                "whatsapp_langchain.worker.processor.build_outbound_client",
                new=AsyncMock(return_value=(fake_client, "real")),
            ) as mock_build,
        ):
            client = await _resolve_outbound_client(AsyncMock(), _msg(7))

        assert client is fake_client
        # cliente construído a partir da conexão do DB (id 7), não de env
        assert mock_build.await_args.args[1].id == 7

    async def test_raises_when_conexao_missing(self):
        from whatsapp_langchain.worker.processor import _resolve_outbound_client

        with patch(
            "whatsapp_langchain.worker.processor.get_conexao_by_id",
            new=AsyncMock(return_value=None),
        ):
            with pytest.raises(OutboundError):
                await _resolve_outbound_client(AsyncMock(), _msg(99))

    async def test_raises_when_no_conexao_id(self):
        from whatsapp_langchain.worker.processor import _resolve_outbound_client

        with pytest.raises(OutboundError):
            await _resolve_outbound_client(AsyncMock(), _msg(None))


class TestBuildOutboundClientNoEnvFallback:
    """Evolution: instance_name vem da conexão; sem ele → erro (sem env fallback)."""

    async def test_evolution_requires_instance_from_conexao(self):
        from whatsapp_langchain.shared.outbound import build_outbound_client

        # conexão evolution SEM instance_name (creds e payload vazios)
        conexao = SimpleNamespace(
            id=7,
            provider="evolution",
            waba_phone_id=None,
            from_number="+5511999999999",
            payload_json={},
        )
        with patch(
            "whatsapp_langchain.shared.outbound.get_credentials_decrypted",
            new=AsyncMock(return_value={"api_url": "https://x", "api_key": "k"}),
        ):
            with pytest.raises(OutboundError):
                await build_outbound_client(AsyncMock(), conexao)
