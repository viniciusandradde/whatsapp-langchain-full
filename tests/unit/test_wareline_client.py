"""Testes do WarelineClient com respx mockando todos os endpoints."""

from unittest.mock import AsyncMock, MagicMock

import pytest
import respx
from cryptography.fernet import Fernet
from httpx import Response

from whatsapp_langchain.integrations.wareline.client import WarelineClient
from whatsapp_langchain.integrations.wareline.errors import (
    WarelineNotFoundError,
    WarelineUnavailableError,
)
from whatsapp_langchain.integrations.wareline.models import (
    CriarAgendamentoInput,
    PacienteAgendamentoInput,
)


@pytest.fixture(autouse=True)
def _patch_fernet_key(monkeypatch):
    from pydantic import SecretStr

    from whatsapp_langchain.shared.config import settings

    key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "wareline_encryption_key", SecretStr(key))


@pytest.fixture(autouse=True)
def _patch_credentials_and_token(monkeypatch):
    """Mocka get_credentials + get_or_refresh_token pra não bater DB."""
    from whatsapp_langchain.integrations.wareline.models import (
        WarelineCredentials,
    )

    fake_creds = WarelineCredentials(
        empresa_id=1,
        base_url="https://modulos.test",
        pacientes_base_url="https://services.test",
        username="u",
        password="p",
        client_id="cid",
        client_secret="cs",
    )

    async def fake_get_creds(_pool, _eid):
        return fake_creds

    async def fake_get_token(_pool, _eid):
        return "token-fake-123"

    async def fake_invalidate(_pool, _eid):
        return None

    monkeypatch.setattr(
        "whatsapp_langchain.integrations.wareline.client.get_credentials",
        fake_get_creds,
    )
    monkeypatch.setattr(
        "whatsapp_langchain.integrations.wareline.client.get_or_refresh_token",
        fake_get_token,
    )
    monkeypatch.setattr(
        "whatsapp_langchain.integrations.wareline.client.invalidate_token",
        fake_invalidate,
    )


def _fake_pool() -> MagicMock:
    pool = MagicMock()
    pool.connection.return_value.__aenter__ = AsyncMock()
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool


# ---------- buscar_paciente ----------


@pytest.mark.asyncio
@respx.mock
async def test_buscar_paciente_ok():
    respx.get(
        "https://services.test/services/utilitarios-api/pacientes"
    ).mock(
        return_value=Response(
            200,
            json=[
                {
                    "cpfpac": "11111111111",
                    "codpac": 13335156,
                    "nomepac": "PACIENTE TESTE",
                    "celular": "19999999999",
                }
            ],
        )
    )
    client = WarelineClient(_fake_pool(), empresa_id=1)
    pacientes = await client.buscar_paciente("11111111111")
    assert len(pacientes) == 1
    assert pacientes[0].nome == "PACIENTE TESTE"
    assert pacientes[0].codigo == 13335156
    assert pacientes[0].cpf == "11111111111"


@pytest.mark.asyncio
@respx.mock
async def test_buscar_paciente_404_levanta_not_found():
    respx.get(
        "https://services.test/services/utilitarios-api/pacientes"
    ).mock(return_value=Response(404, json={"erro": "nao_encontrado"}))
    client = WarelineClient(_fake_pool(), empresa_id=1)
    with pytest.raises(WarelineNotFoundError):
        await client.buscar_paciente("99999999999")


@pytest.mark.asyncio
@respx.mock
async def test_buscar_paciente_lista_vazia_levanta_not_found():
    respx.get(
        "https://services.test/services/utilitarios-api/pacientes"
    ).mock(return_value=Response(200, json=[]))
    client = WarelineClient(_fake_pool(), empresa_id=1)
    with pytest.raises(WarelineNotFoundError):
        await client.buscar_paciente("00000000000")


# ---------- listar_agenda_prestador ----------


@pytest.mark.asyncio
@respx.mock
async def test_listar_agenda_prestador_ok():
    respx.get(
        "https://modulos.test/services/terapias-api/agendas/prestador"
    ).mock(
        return_value=Response(
            200,
            json={
                "content": [
                    {
                        "numAgenda": 5392,
                        "data": "2025-08-05",
                        "horario": "07:00:00",
                        "prestador": {
                            "codprest": "003297",
                            "nomeprest": "DR EXEMPLO",
                        },
                        "centroCusto": {
                            "codcc": "000003",
                            "nome": "CC EXEMPLO",
                        },
                    }
                ],
                "totalElements": 1,
            },
        )
    )
    client = WarelineClient(_fake_pool(), empresa_id=1)
    agendas = await client.listar_agenda_prestador(
        "003297", "2025-08-01", "2025-08-31"
    )
    assert len(agendas) == 1
    assert agendas[0].num_agenda == 5392
    assert agendas[0].prestador.nomeprest == "DR EXEMPLO"


@pytest.mark.asyncio
@respx.mock
async def test_listar_agenda_vazia():
    respx.get(
        "https://modulos.test/services/terapias-api/agendas/prestador"
    ).mock(return_value=Response(200, json={"content": [], "totalElements": 0}))
    client = WarelineClient(_fake_pool(), empresa_id=1)
    agendas = await client.listar_agenda_prestador(
        "999999", "2025-08-01", "2025-08-31"
    )
    assert agendas == []


# ---------- criar_agendamento ----------


@pytest.mark.asyncio
@respx.mock
async def test_criar_agendamento_ok():
    respx.post(
        "https://modulos.test/services/terapias-api/agendas"
    ).mock(
        return_value=Response(
            200,
            json={
                "status": "SUCESSO",
                "mensagem": "Agendamento realizado com sucesso.",
                "dados": {"cod_agendamento": 999888},
            },
        )
    )
    client = WarelineClient(_fake_pool(), empresa_id=1)
    payload = CriarAgendamentoInput(
        cod_agenda=12345,
        paciente=PacienteAgendamentoInput(
            cod_paciente=999,
            nome_paciente="X",
            data_nascimento="1980-01-01",
            cpf_paciente="11111111111",
        ),
        data_marcacao="2025-09-01T10:00:00",
    )
    resp = await client.criar_agendamento(payload)
    assert resp.status == "SUCESSO"
    assert resp.dados is not None
    assert resp.dados["cod_agendamento"] == 999888


# ---------- Retry / 5xx ----------


@pytest.mark.asyncio
@respx.mock
async def test_5xx_retry_3x_eventualmente_levanta_unavailable():
    route = respx.get(
        "https://services.test/services/utilitarios-api/pacientes"
    ).mock(return_value=Response(503, text="upstream down"))
    client = WarelineClient(_fake_pool(), empresa_id=1)
    # Mock asyncio.sleep pra não esperar de verdade
    import whatsapp_langchain.integrations.wareline.client as client_mod

    async def fake_sleep(_):
        return None

    client_mod.asyncio.sleep = fake_sleep  # type: ignore[attr-defined]

    with pytest.raises(WarelineUnavailableError):
        await client.buscar_paciente("11111111111")
    # 1 tentativa inicial + 3 retries = 4
    assert route.call_count == 4


@pytest.mark.asyncio
@respx.mock
async def test_401_invalida_token_e_retenta_1x():
    """401 dispara invalidação do cache + 1 retry. No 2º também 401 → falha."""
    call_count = {"n": 0}

    def respond(_request):
        call_count["n"] += 1
        return Response(401)

    respx.get(
        "https://services.test/services/utilitarios-api/pacientes"
    ).mock(side_effect=respond)

    import whatsapp_langchain.integrations.wareline.client as client_mod

    async def fake_sleep(_):
        return None

    client_mod.asyncio.sleep = fake_sleep  # type: ignore[attr-defined]

    from whatsapp_langchain.integrations.wareline.errors import (
        WarelineAuthError,
    )

    client = WarelineClient(_fake_pool(), empresa_id=1)
    with pytest.raises(WarelineAuthError):
        await client.buscar_paciente("11111111111")
    # 2 chamadas: tentativa inicial (401, invalida) + retry (401 final)
    assert call_count["n"] == 2
