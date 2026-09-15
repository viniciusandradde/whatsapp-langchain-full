"""Gate do modo IA: conexão em ia/híbrido exige agente da empresa cadastrado.

TODO aprovado 2026-08-20 (incidente 2026-08-19): ligar a IA sem agente na
empresa fazia o worker cair no template de exemplo do catálogo (vsa_tech) e
responder com um prompt genérico da VSA Tech. O critério do gate é o mesmo do
runtime: `resolve_agente_runtime` devolver None = cairia no legacy → bloqueia.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from whatsapp_langchain.shared.atendimento import (
    MARKERS_INTERNOS,
    MARKERS_REPROCESSAVEIS,
)
from whatsapp_langchain.shared.conexao import validar_agente_da_empresa_para_ia

pytestmark = pytest.mark.asyncio

_PATCH_RESOLVE = "whatsapp_langchain.shared.agente.resolve_agente_runtime"


class TestValidarAgenteParaIA:
    async def test_modo_manual_nunca_exige_agente(self) -> None:
        # Sem agente algum, mas manual não invoca ninguém → sem erro.
        with patch(_PATCH_RESOLVE, new=AsyncMock(return_value=None)) as m:
            erro = await validar_agente_da_empresa_para_ia(
                MagicMock(), 1, "manual", "vsa_tech"
            )
        assert erro is None
        m.assert_not_awaited()  # nem consulta o runtime

    async def test_ia_sem_agente_da_empresa_bloqueia(self) -> None:
        with patch(_PATCH_RESOLVE, new=AsyncMock(return_value=None)):
            erro = await validar_agente_da_empresa_para_ia(
                MagicMock(), 1, "ia", "vsa_tech"
            )
        assert erro is not None
        assert "agente" in erro.lower() and "autom" in erro.lower()

    async def test_ia_com_agente_da_empresa_passa(self) -> None:
        with patch(_PATCH_RESOLVE, new=AsyncMock(return_value=object())):
            erro = await validar_agente_da_empresa_para_ia(
                MagicMock(), 1, "ia", "atendimento-cliente"
            )
        assert erro is None

    async def test_hibrido_tambem_exige_agente(self) -> None:
        with patch(_PATCH_RESOLVE, new=AsyncMock(return_value=None)):
            erro = await validar_agente_da_empresa_para_ia(
                MagicMock(), 1, "hibrido", "vsa_tech"
            )
        assert erro is not None

    async def test_slug_vazio_com_ia_bloqueia(self) -> None:
        with patch(_PATCH_RESOLVE, new=AsyncMock(return_value=None)) as m:
            erro = await validar_agente_da_empresa_para_ia(MagicMock(), 1, "ia", None)
        assert erro is not None
        # chama resolve com string vazia (nunca None) — get_agente_by_slug espera str
        assert m.await_args.args[2] == ""


class TestMarcadorSemAgente:
    """O marcador do worker tem que estar registrado nas listas de propósito
    único, senão a bolha vaza pra timeline e a mensagem não reenfileira."""

    def test_esta_nos_markers_internos(self) -> None:
        assert "[IA sem agente cadastrado" in MARKERS_INTERNOS

    def test_e_reprocessavel(self) -> None:
        # Cadastrar o agente e reenfileirar deve voltar a IA (como manual→ia).
        assert "[IA sem agente cadastrado" in MARKERS_REPROCESSAVEIS

    def test_marcador_do_processor_bate_com_o_prefixo(self) -> None:
        from whatsapp_langchain.worker.processor import (
            _MARKERS_SISTEMA,
            SEM_AGENTE_MARKER,
        )

        assert SEM_AGENTE_MARKER.startswith("[IA sem agente cadastrado")
        assert SEM_AGENTE_MARKER in _MARKERS_SISTEMA
