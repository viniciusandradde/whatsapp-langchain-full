"""Preferência de provider de observabilidade (mig 141).

Existe porque a resolução por env era armadilha operacional: desligar os
containers do Langfuse NÃO muda `settings.langfuse_enabled` (as chaves seguem
no .env), então `/traces` continuava apontando pro host morto e a página
quebrava — sem jeito de trocar sem redeploy.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from whatsapp_langchain.shared.app_setting import (
    CHAVE_OBS_PROVIDER,
    OBS_PROVIDER_VALIDOS,
    get_obs_provider_preferido,
    get_setting,
)


def _pool_devolvendo(valor: Any) -> MagicMock:
    """Pool falso cujo SELECT devolve `valor` (ou None pra 'sem linha')."""
    cur = AsyncMock()
    cur.fetchone = AsyncMock(return_value=(valor,) if valor is not None else None)
    conn = AsyncMock()
    conn.execute = AsyncMock(return_value=cur)
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=conn)
    ctx.__aexit__ = AsyncMock(return_value=None)
    pool = MagicMock()
    pool.connection = MagicMock(return_value=ctx)
    return pool


def _pool_que_falha() -> MagicMock:
    pool = MagicMock()
    pool.connection = MagicMock(side_effect=RuntimeError("banco fora"))
    return pool


class TestValoresValidos:
    def test_conjunto_e_estavel(self) -> None:
        # Gravado no banco: mudar quebra dado existente.
        assert OBS_PROVIDER_VALIDOS == {"auto", "langfuse", "langsmith"}

    def test_chave_e_estavel(self) -> None:
        assert CHAVE_OBS_PROVIDER == "observabilidade.provider"


class TestLeitura:
    async def test_le_valor_gravado(self) -> None:
        assert await get_obs_provider_preferido(_pool_devolvendo("langsmith")) == (
            "langsmith"
        )

    async def test_sem_linha_cai_pra_auto(self) -> None:
        """Instalação anterior à mig 141 não pode virar página quebrada."""
        assert await get_obs_provider_preferido(_pool_devolvendo(None)) == "auto"

    async def test_valor_corrompido_cai_pra_auto(self) -> None:
        """Pior cenário = comportamento de antes da migration, nunca erro."""
        assert await get_obs_provider_preferido(_pool_devolvendo("banana")) == "auto"

    async def test_banco_fora_nao_propaga(self) -> None:
        """Preferência de UI não pode derrubar a página que a consome."""
        assert await get_obs_provider_preferido(_pool_que_falha()) == "auto"

    async def test_get_setting_respeita_default(self) -> None:
        assert await get_setting(_pool_devolvendo(None), "x.y", "padrao") == "padrao"


class TestResolucaoEfetiva:
    """Espelha `_provider_efetivo` de routes/traces.py sem subir a API."""

    @staticmethod
    def _efetivo(preferido: str, *, lf: bool, ls: bool) -> str | None:
        if preferido == "langfuse" and lf:
            return "langfuse"
        if preferido == "langsmith" and ls:
            return "langsmith"
        if lf:
            return "langfuse"
        if ls:
            return "langsmith"
        return None

    def test_escolha_explicita_vence_a_ordem_automatica(self) -> None:
        """O ponto da feature: com os dois configurados, o admin manda."""
        assert self._efetivo("langsmith", lf=True, ls=True) == "langsmith"

    def test_auto_mantem_langfuse_primeiro(self) -> None:
        """Comportamento pré-mig 141 preservado."""
        assert self._efetivo("auto", lf=True, ls=True) == "langfuse"

    def test_escolha_sem_credencial_cai_no_automatico(self) -> None:
        """Melhor mostrar a lista do outro que uma tela vazia sem explicação."""
        assert self._efetivo("langfuse", lf=False, ls=True) == "langsmith"

    def test_nenhum_configurado(self) -> None:
        assert self._efetivo("auto", lf=False, ls=False) is None

    @pytest.mark.parametrize("preferido", ["auto", "langfuse", "langsmith"])
    def test_nunca_estoura_com_valor_valido(self, preferido: str) -> None:
        self._efetivo(preferido, lf=False, ls=False)
