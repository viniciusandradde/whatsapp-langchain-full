"""Testes do resumo diário (mig 135) — lógica pura de agendamento."""

from datetime import UTC, date, datetime, time

from whatsapp_langchain.shared.resumo_diario import ResumoConfig, deve_enviar


def _cfg(**kw) -> ResumoConfig:
    base = dict(
        empresa_id=1,
        telefone="+5567999068963",
        horario=time(22, 30),
        dias=[1, 2, 3, 4, 5],
        tz="America/Campo_Grande",
        last_sent=None,
    )
    base.update(kw)
    return ResumoConfig(**base)


class TestDeveEnviar:
    def test_envia_no_horario_em_dia_util(self):
        # 2026-07-23 é quinta; 22:30 local = 02:30 UTC do dia seguinte (UTC-4)
        now = datetime(2026, 7, 24, 2, 35, tzinfo=UTC)
        assert deve_enviar(_cfg(), now) is True

    def test_nao_envia_antes_do_horario(self):
        # 21:00 local (quinta)
        now = datetime(2026, 7, 24, 1, 0, tzinfo=UTC)
        assert deve_enviar(_cfg(), now) is False

    def test_nao_envia_fim_de_semana(self):
        # sábado 22:35 local (2026-07-25)
        now = datetime(2026, 7, 26, 2, 35, tzinfo=UTC)
        assert deve_enviar(_cfg(), now) is False

    def test_envia_sabado_quando_dia_marcado(self):
        now = datetime(2026, 7, 26, 2, 35, tzinfo=UTC)
        assert deve_enviar(_cfg(dias=[6]), now) is True

    def test_nao_reenvia_no_mesmo_dia(self):
        now = datetime(2026, 7, 24, 2, 35, tzinfo=UTC)
        # last_sent = data LOCAL de hoje (23/07 em Campo Grande)
        assert deve_enviar(_cfg(last_sent=date(2026, 7, 23)), now) is False

    def test_envia_de_novo_no_dia_seguinte(self):
        now = datetime(2026, 7, 25, 2, 35, tzinfo=UTC)  # sexta 22:35 local
        assert deve_enviar(_cfg(last_sent=date(2026, 7, 23)), now) is True

    def test_tz_invalida_cai_no_fallback_sem_quebrar(self):
        now = datetime(2026, 7, 24, 2, 35, tzinfo=UTC)
        assert deve_enviar(_cfg(tz="Fuso/Inexistente"), now) is True

    def test_dias_vazio_nunca_envia(self):
        now = datetime(2026, 7, 24, 2, 35, tzinfo=UTC)
        assert deve_enviar(_cfg(dias=[]), now) is False
