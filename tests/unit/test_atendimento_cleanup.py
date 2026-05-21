"""Tests dos helpers de cleanup de atendimentos zumbis."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from whatsapp_langchain.shared.atendimento_cleanup import (
    DEFAULT_DIAS_MAX_AGUARDANDO,
    DEFAULT_DIAS_MAX_SEM_RESPOSTA,
    cleanup_zumbis,
    get_cleanup_config,
    preview_zumbis,
)


def _mock_pool(*results) -> tuple[MagicMock, AsyncMock]:
    cur = AsyncMock()
    fetchone_seq = [r for r in results if not isinstance(r, list)]
    fetchall_seq = [r for r in results if isinstance(r, list)]
    cur.fetchone = AsyncMock(side_effect=fetchone_seq if fetchone_seq else [None])
    cur.fetchall = AsyncMock(side_effect=fetchall_seq if fetchall_seq else [[]])
    conn = MagicMock()
    conn.execute = AsyncMock(return_value=cur)
    conn.commit = AsyncMock()
    pool = MagicMock()
    pool.connection.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.connection.return_value.__aexit__ = AsyncMock(return_value=None)
    return pool, conn


@pytest.mark.asyncio
async def test_get_cleanup_config_defaults():
    """Empresa sem config retorna defaults."""
    pool, _ = _mock_pool(({},))
    cfg = await get_cleanup_config(pool, 1)
    assert cfg["enabled"] is True
    assert cfg["dias_max_aguardando"] == DEFAULT_DIAS_MAX_AGUARDANDO
    assert cfg["dias_max_sem_resposta"] == DEFAULT_DIAS_MAX_SEM_RESPOSTA


@pytest.mark.asyncio
async def test_get_cleanup_config_override():
    """Empresa com config customizada respeita valores."""
    custom = {
        "cleanup_atendimento": {
            "enabled": True,
            "dias_max_aguardando": 5.0,
            "dias_max_sem_resposta": 2.0,
        }
    }
    pool, _ = _mock_pool((custom,))
    cfg = await get_cleanup_config(pool, 1)
    assert cfg["dias_max_aguardando"] == 5.0
    assert cfg["dias_max_sem_resposta"] == 2.0


@pytest.mark.asyncio
async def test_get_cleanup_config_disabled():
    """enabled=false desativa cleanup."""
    custom = {"cleanup_atendimento": {"enabled": False}}
    pool, _ = _mock_pool((custom,))
    cfg = await get_cleanup_config(pool, 1)
    assert cfg["enabled"] is False


@pytest.mark.asyncio
async def test_preview_zumbis_disabled_returns_zero():
    """Empresa com cleanup desabilitado nunca retorna zumbis."""
    custom = {"cleanup_atendimento": {"enabled": False}}
    pool, _ = _mock_pool((custom,))
    r = await preview_zumbis(pool, 1)
    assert r["enabled"] is False
    assert r["total"] == 0


@pytest.mark.asyncio
async def test_preview_zumbis_conta_corretamente():
    """Conta aguardando e em_andamento separadamente."""
    pool, _ = _mock_pool(
        ({},),  # config (defaults)
        (5, 3),  # query counts: 5 aguardando + 3 em_andamento
    )
    r = await preview_zumbis(pool, 1)
    assert r["enabled"] is True
    assert r["aguardando_zumbi"] == 5
    assert r["em_andamento_zumbi"] == 3
    assert r["total"] == 8


@pytest.mark.asyncio
async def test_cleanup_zumbis_dry_run_nao_executa_update():
    """dry_run=True retorna preview sem UPDATE."""
    pool, conn = _mock_pool(
        ({},),  # config p/ cleanup_zumbis
        ({},),  # config p/ preview_zumbis (chamado internamente)
        (7, 2),  # preview counts
    )
    r = await cleanup_zumbis(pool, 1, dry_run=True)
    assert r["dry_run"] is True
    assert r["total"] == 9
    # Verifica que NÃO houve UPDATE (só SELECTs)
    sqls = [c.args[0] for c in conn.execute.await_args_list]
    assert not any("UPDATE atendimento" in s for s in sqls)


@pytest.mark.asyncio
async def test_cleanup_zumbis_real_executa_update_e_commit():
    """dry_run=False executa UPDATE com commit."""
    pool, conn = _mock_pool(
        ({},),  # config
        [(10,), (11,)],  # ids aguardando fechados
        [(20,)],  # ids em_andamento fechados
    )
    # Mock dispatch_event pra não tentar contactar hooks reais
    from unittest.mock import patch
    with patch(
        "whatsapp_langchain.shared.hook_dispatcher.dispatch_event",
        new=AsyncMock(),
    ):
        r = await cleanup_zumbis(pool, 1, dry_run=False)
    assert r["dry_run"] is False
    assert r["aguardando_fechados"] == 2
    assert r["em_andamento_fechados"] == 1
    assert r["total"] == 3
    conn.commit.assert_awaited_once()
    sqls = [c.args[0] for c in conn.execute.await_args_list]
    assert any("UPDATE atendimento" in s and "abandonado" in s for s in sqls)


@pytest.mark.asyncio
async def test_cleanup_zumbis_disabled_pula():
    """enabled=false não roda UPDATE."""
    custom = {"cleanup_atendimento": {"enabled": False}}
    pool, conn = _mock_pool((custom,))
    r = await cleanup_zumbis(pool, 1, dry_run=False)
    assert r["enabled"] is False
    assert r["total"] == 0
    # Só 1 query (config), nenhum UPDATE
    sqls = [c.args[0] for c in conn.execute.await_args_list]
    assert not any("UPDATE atendimento" in s for s in sqls)
