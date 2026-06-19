"""Testes unitários do jitter anti-ban + resolução de variáveis (Task 6.4)."""

from whatsapp_langchain.shared.campanha import (
    _MEDIA_MIN_INTERVAL_MS,
    _apply_tokens,
    _jitter_delay_s,
    _piso_midia,
    _proxima_conexao,
    _resolve_template_vars,
)


class TestProximaConexao:
    """Round-robin do pool de números com teto diário (mig 130)."""

    def test_alterna_em_ordem(self):
        pool = [10, 20, 30]
        rest = {10: None, 20: None, 30: None}  # ilimitado
        seq = []
        rr = 0
        for _ in range(6):
            cid, rr = _proxima_conexao(pool, rest, rr)
            seq.append(cid)
        assert seq == [10, 20, 30, 10, 20, 30]

    def test_pula_quem_zerou(self):
        pool = [10, 20, 30]
        rest = {10: 0, 20: 5, 30: 0}  # só o 20 tem capacidade
        cid, rr = _proxima_conexao(pool, rest, 0)
        assert cid == 20
        cid2, _ = _proxima_conexao(pool, rest, rr)
        assert cid2 == 20  # continua só no 20

    def test_todas_zeradas_retorna_none(self):
        pool = [10, 20]
        assert _proxima_conexao(pool, {10: 0, 20: 0}, 0) is None

    def test_pool_de_um(self):
        cid, rr = _proxima_conexao([10], {10: None}, 0)
        assert cid == 10 and rr == 0


class TestApplyTokens:
    def test_nome_primeiro(self):
        assert _apply_tokens("Olá {{nome}}!", "João Silva") == "Olá João!"

    def test_variaveis_csv_chaves_e_colchetes(self):
        out = _apply_tokens(
            "{{nome}} da {{empresa}} / [cidade]",
            "Maria Souza",
            {"empresa": "ACME", "cidade": "SP"},
        )
        assert out == "Maria da ACME / SP"

    def test_sem_nome_token_vira_vazio(self):
        assert _apply_tokens("Oi {{nome}}", None) == "Oi "

    def test_texto_vazio(self):
        assert _apply_tokens("", "João") == ""


class TestResolveTemplateVars:
    def test_resolve_posicional_com_contexto(self):
        base = {"1": "Olá {{nome}}", "2": "Pedido [num]"}
        out = _resolve_template_vars(base, "Ana Lima", {"num": "123"})
        assert out == {"1": "Olá Ana", "2": "Pedido 123"}

    def test_base_vazia(self):
        assert _resolve_template_vars(None, "X") == {}


class TestJitterDelay:
    def test_dentro_da_faixa(self):
        for _ in range(1000):
            d = _jitter_delay_s(3000, 8000)
            assert 3.0 <= d <= 8.0

    def test_min_maior_que_max_troca(self):
        for _ in range(200):
            d = _jitter_delay_s(8000, 3000)
            assert 3.0 <= d <= 8.0

    def test_zero_ou_none(self):
        assert _jitter_delay_s(0, 0) == 0.0
        assert _jitter_delay_s(None, None) == 0.0

    def test_fixo_quando_min_eq_max(self):
        assert _jitter_delay_s(500, 500) == 0.5


class TestPisoMidia:
    """Piso de intervalo anti-ban pra mídia (mig 127 — item 5 do best-practices)."""

    def test_sem_midia_nao_mexe(self):
        assert _piso_midia(3000, 8000, False) == (3000, 8000)

    def test_midia_abaixo_do_piso_sobe(self):
        min_ms, max_ms = _piso_midia(3000, 5000, True)
        assert min_ms == _MEDIA_MIN_INTERVAL_MS
        assert max_ms >= min_ms  # max ajustado pra não ficar abaixo do novo min

    def test_midia_acima_do_piso_mantem(self):
        # já está acima do piso → não reduz
        assert _piso_midia(10000, 20000, True) == (10000, 20000)

    def test_piso_eh_8s(self):
        assert _MEDIA_MIN_INTERVAL_MS == 8000


class TestCampanhaCreateAntiBan:
    """Validação do modelo de criação com campos anti-ban (migs 120/121)."""

    def _model(self):
        from whatsapp_langchain.server.routes.campanha import CampanhaCreate

        return CampanhaCreate

    def test_aceita_jitter_e_kill_switch(self):
        m = self._model()(
            nome="Promo",
            mensagem="Olá",
            telefones=["+5511999999999"],
            intervalo_min_ms=5000,
            intervalo_max_ms=15000,
            kill_switch_pct=25,
        )
        assert m.intervalo_min_ms == 5000
        assert m.intervalo_max_ms == 15000
        assert m.kill_switch_pct == 25

    def test_min_maior_que_max_rejeita(self):
        import pytest

        with pytest.raises(ValueError, match="intervalo_min_ms"):
            self._model()(
                nome="Promo",
                mensagem="Olá",
                telefones=["+5511999999999"],
                intervalo_min_ms=15000,
                intervalo_max_ms=5000,
            )

    def test_anti_ban_opcional(self):
        # sem os campos → None (cai nos defaults do banco/helper)
        m = self._model()(nome="Promo", mensagem="Olá", telefones=["+5511999999999"])
        assert m.intervalo_min_ms is None
        assert m.kill_switch_pct is None


class TestSendComRetry:
    """Retry anti-ban de envio (transitório → re-tenta; esgota → re-levanta)."""

    async def test_sucesso_na_segunda_tentativa(self):
        import structlog

        from whatsapp_langchain.shared.campanha import _send_com_retry

        chamadas = {"n": 0}

        async def fn():
            chamadas["n"] += 1
            if chamadas["n"] < 2:
                raise RuntimeError("Connection Closed")
            return "MID-OK"

        # patch sleep pra não esperar de verdade
        import whatsapp_langchain.shared.campanha as camp_mod

        async def _noop(*_a, **_k):
            return None

        orig = camp_mod.asyncio.sleep
        camp_mod.asyncio.sleep = _noop
        try:
            r = await _send_com_retry(fn, log=structlog.get_logger(), phone="+551199")
        finally:
            camp_mod.asyncio.sleep = orig
        assert r == "MID-OK"
        assert chamadas["n"] == 2

    async def test_esgota_e_relevanta(self):
        import pytest as _pytest
        import structlog

        import whatsapp_langchain.shared.campanha as camp_mod
        from whatsapp_langchain.shared.campanha import _send_com_retry

        async def fn():
            raise RuntimeError("Connection Closed")

        async def _noop(*_a, **_k):
            return None

        orig = camp_mod.asyncio.sleep
        camp_mod.asyncio.sleep = _noop
        try:
            with _pytest.raises(RuntimeError, match="Connection Closed"):
                await _send_com_retry(
                    fn, log=structlog.get_logger(), phone="+551199", tentativas=3
                )
        finally:
            camp_mod.asyncio.sleep = orig
