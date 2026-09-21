"""Regras puras da saúde das conexões (mig 196) — sem banco, sem rede."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from whatsapp_langchain.shared.saude_conexoes import (
    ECO_FALHAS_MIN,
    ECO_INTERVALO_MIN,
    ECO_TIMEOUT_MIN,
    HISTORICO_MIN_DIAS,
    SILENCIO_PISO_H,
    SILENCIO_TETO_H,
    SONDAS_RUINS_MIN,
    Achado,
    ConexaoMonitorada,
    ResultadoSonda,
    Silencio,
    SinaisConexao,
    avaliar_conexao,
    calcular_limite_silencio,
    calcular_silencio,
    decidir_eco,
    descrever_desconexao,
    duracao_humana,
    esperadas_na_janela,
    formatar_linha,
    hora_ativa,
    monitoravel,
    montar_mensagem,
    sonda_devida,
)

TZ = "America/Campo_Grande"  # UTC-4, sem horário de verão


def _utc(ano: int, mes: int, dia: int, hora: int, minuto: int = 0) -> datetime:
    return datetime(ano, mes, dia, hora, minuto, tzinfo=UTC)


def _local(ano: int, mes: int, dia: int, hora: int, minuto: int = 0) -> datetime:
    """Hora de Campo Grande expressa em UTC (UTC-4)."""
    return _utc(ano, mes, dia, hora + 4, minuto)


def _baseline_comercial(por_hora: float = 4.0) -> dict[tuple[int, int], float]:
    """Cliente que só recebe em dia útil das 8 às 18 h locais."""
    return {(dow, h): por_hora for dow in range(1, 6) for h in range(8, 18)}


def _conexao(**kw) -> ConexaoMonitorada:
    base = dict(
        id=4,
        empresa_id=1018,
        empresa_nome="Luis Fernando Macorini",
        tz=TZ,
        provider="evolution",
        display_name="Luis_prod",
        from_number="+556799068963",
        instance_name="empresa1_luis_prod",
        tipo_atendimento="ia",
        connection_state="open",
        state_message=None,
        ultimo_health_check_at=None,
        ultimo_health_check_ok=None,
        sonda_falhas_seguidas=0,
        desconexao_codigo=None,
        desconexao_em=None,
        ultimo_inbound_em=_local(2026, 9, 16, 9, 27),
    )
    base.update(kw)
    return ConexaoMonitorada(**base)


def _sinais(**kw) -> SinaisConexao:
    base = dict(
        connection_state="open",
        desconexao_codigo=None,
        desconexao_em=None,
        sonda=None,
        sonda_falhas_seguidas=0,
        silencio=None,
        ultimo_inbound_em=_local(2026, 9, 22, 8, 0),
        eco_falhas_seguidas=0,
    )
    base.update(kw)
    return SinaisConexao(**base)


def _sonda(ok: bool, motivo: str = "conexão responde") -> ResultadoSonda:
    return ResultadoSonda(
        ok=ok,
        estado="open",
        responde=ok,
        latencia_ms=120 if ok else None,
        motivo=motivo,
    )


# --- silêncio ----------------------------------------------------------------


def test_silencio_nao_julga_sem_historico_ou_sem_mensagem():
    terca_14h = _local(2026, 9, 22, 14)
    assert (
        calcular_silencio(
            _baseline_comercial(), 5.0, _local(2026, 9, 22, 8), terca_14h, TZ
        )
        is None
    )
    assert calcular_silencio(_baseline_comercial(), 20.0, None, terca_14h, TZ) is None


def test_silencio_em_horario_comercial_soma_as_horas_locais():
    # terça 08:00 → 14:00 local = 6 h × 4/h = 24 esperadas
    s = calcular_silencio(
        _baseline_comercial(), 20.0, _local(2026, 9, 22, 8), _local(2026, 9, 22, 14), TZ
    )
    assert s is not None
    assert s.esperadas == 24.0
    assert s.horas == 6.0


def test_silencio_de_fim_de_semana_nao_alerta():
    # sábado 10:00 → domingo 18:00 local: nenhuma hora útil na baseline
    s = calcular_silencio(
        _baseline_comercial(),
        20.0,
        _local(2026, 9, 19, 10),
        _local(2026, 9, 20, 18),
        TZ,
    )
    assert s is not None
    assert s.esperadas == 0.0


def test_silencio_conta_fracao_da_hora_das_pontas():
    # 08:30 → 09:00 local = meia hora de uma hora com 4 → 2
    s = calcular_silencio(
        _baseline_comercial(),
        20.0,
        _local(2026, 9, 22, 8, 30),
        _local(2026, 9, 22, 9),
        TZ,
    )
    assert s is not None
    assert s.esperadas == 2.0


def test_silencio_limita_a_janela_a_sete_dias():
    ultimo = _local(2026, 9, 1, 8)
    agora = _local(2026, 9, 22, 8)
    s = calcular_silencio(_baseline_comercial(), 20.0, ultimo, agora, TZ)
    assert s is not None
    assert s.horas == 24 * 7
    # 5 dias úteis × 10 h × 4 = 200 na última semana
    assert s.esperadas == 200.0


def test_fuso_invalido_cai_no_padrao():
    s = calcular_silencio(
        _baseline_comercial(),
        20.0,
        _local(2026, 9, 22, 8),
        _local(2026, 9, 22, 14),
        "Marte/Olympus",
    )
    assert s is not None and s.esperadas == 24.0
    assert (
        esperadas_na_janela({}, _local(2026, 9, 22, 8), _local(2026, 9, 22, 14), TZ)
        == 0.0
    )


# --- decisão -----------------------------------------------------------------


def test_uma_sonda_ruim_nao_abre_duas_abrem():
    ruim = _sonda(False, "sem resposta do WhatsApp em 8 s")
    assert avaliar_conexao(_sinais(sonda=ruim, sonda_falhas_seguidas=1)) == []
    achados = avaliar_conexao(
        _sinais(
            sonda=ruim,
            sonda_falhas_seguidas=SONDAS_RUINS_MIN,
            desconexao_em=_utc(2026, 9, 22, 12),
        )
    )
    assert [a.tipo for a in achados] == ["conexao_caida"]
    assert achados[0].detalhe["origem"] == "sonda"
    assert achados[0].detalhe["motivo"] == "sem resposta do WhatsApp em 8 s"


def test_aparelho_desvinculado_abre_na_hora_sem_esperar_sonda():
    achados = avaliar_conexao(
        _sinais(
            connection_state="disconnected",
            desconexao_codigo=401,
            desconexao_em=_utc(2026, 9, 16, 13),
        )
    )
    assert [a.tipo for a in achados] == ["conexao_caida"]
    assert achados[0].detalhe["origem"] == "evento"
    assert achados[0].detalhe["motivo"] == "aparelho desvinculado no celular"


def test_queda_transitoria_nao_abre_sozinha():
    # 428 = a Evolution reconecta sozinha; sem sondas ruins, nada a avisar
    assert (
        avaliar_conexao(_sinais(connection_state="disconnected", desconexao_codigo=428))
        == []
    )


def test_silencio_nunca_abre_episodio_mesmo_acima_do_normal():
    """mig 198: 38 silêncios ≥ 1 h/mês saudáveis na VSA — silêncio é gatilho
    do eco, não alerta. Nem com a sonda dizendo que responde."""
    desde = _local(2026, 9, 22, 8)
    sil = Silencio(
        24.0, 6.0, desde, 20.0, limite_normal_h=2.0, hora_ativa=True, horas_ativas=6.0
    )
    assert sil.acima_do_normal
    assert avaliar_conexao(_sinais(silencio=sil, sonda=_sonda(True))) == []


def test_regua_empirica_do_silencio():
    assert calcular_limite_silencio([1.0, 3.7], HISTORICO_MIN_DIAS - 1) is None
    assert calcular_limite_silencio([], 20.0) is None
    # VSA: maior silêncio saudável 3,7 h → 5,5 h; 1h26 não é acima do normal
    assert calcular_limite_silencio([0.2, 1.5, 3.7], 20.0) == pytest.approx(5.55)
    assert calcular_limite_silencio([0.1, 0.5], 20.0) == SILENCIO_PISO_H
    assert calcular_limite_silencio([40.0], 20.0) == SILENCIO_TETO_H
    sil = Silencio(8.5, 1.43, _local(2026, 9, 21, 16, 36), 21.0, 5.55, True, 1.43)
    assert not sil.acima_do_normal
    # fora de hora ativa (madrugada) nunca é "acima do normal"
    assert not Silencio(
        0.0, 9.0, _utc(2026, 9, 22, 2), 21.0, 5.55, False
    ).acima_do_normal
    assert Silencio(
        0.0, 6.0, _local(2026, 9, 21, 8), 21.0, 5.55, True, 6.0
    ).acima_do_normal
    # 9 h de relógio mas só 1 h ativa (atravessou a noite): não é acima
    assert not Silencio(
        0.0, 9.0, _local(2026, 9, 21, 8), 21.0, 5.55, True, 1.0
    ).acima_do_normal


def test_horas_ativas_entre_ignora_a_noite():
    from whatsapp_langchain.shared.saude_conexoes import horas_ativas_entre

    base = {(1, h): 4.0 for h in range(8, 18)} | {(2, h): 4.0 for h in range(8, 18)}
    # segunda 17:45 → terça 08:30: 15 min + 30 min ativos, a noite vale zero
    assert horas_ativas_entre(
        base, _local(2026, 9, 21, 17, 45), _local(2026, 9, 22, 8, 30), TZ
    ) == pytest.approx(0.75)
    assert (
        horas_ativas_entre(base, _local(2026, 9, 21, 9), _local(2026, 9, 21, 12), TZ)
        == 3.0
    )
    assert (
        horas_ativas_entre({}, _local(2026, 9, 21, 9), _local(2026, 9, 21, 12), TZ)
        == 0.0
    )


def test_hora_ativa_le_a_baseline_local():
    base = {(2, 9): 4.0, (2, 22): 0.1}
    assert hora_ativa(base, _local(2026, 9, 22, 9) + timedelta(minutes=30), TZ)
    assert not hora_ativa(base, _utc(2026, 9, 23, 2, 10), TZ)
    assert not hora_ativa(base, _local(2026, 9, 26, 9), TZ)  # sábado sem linha


def test_decidir_eco():
    now = _local(2026, 9, 22, 10)
    acima = Silencio(20.0, 6.0, _local(2026, 9, 22, 4), 20.0, 2.0, True, 6.0)
    normal = Silencio(2.0, 0.5, _local(2026, 9, 22, 9, 30), 20.0, 2.0, True, 0.5)
    # só Evolution com eco ligado
    assert decidir_eco(_conexao(provider="waba"), acima, True, now) == "nada"
    assert decidir_eco(_conexao(eco_ativo=False), acima, True, now) == "nada"
    # silêncio acima do normal + sonda OK → enviar; sonda ruim não (a sonda já decide)
    assert decidir_eco(_conexao(), acima, True, now) == "enviar"
    assert decidir_eco(_conexao(), acima, False, now) == "nada"
    assert decidir_eco(_conexao(), normal, True, now) == "nada"
    # intervalo mínimo entre ecos
    recente = now - timedelta(minutes=ECO_INTERVALO_MIN - 5)
    assert decidir_eco(_conexao(ultimo_eco_em=recente), acima, True, now) == "nada"
    antigo = now - timedelta(minutes=ECO_INTERVALO_MIN + 5)
    assert decidir_eco(_conexao(ultimo_eco_em=antigo), acima, True, now) == "enviar"
    # eco em voo: aguarda dentro do prazo, falha depois
    em_voo = _conexao(eco_pendente_id="ABC", eco_enviado_em=now - timedelta(minutes=1))
    assert decidir_eco(em_voo, acima, True, now) == "aguardar"
    vencido = _conexao(
        eco_pendente_id="ABC",
        eco_enviado_em=now - timedelta(minutes=ECO_TIMEOUT_MIN + 1),
    )
    assert decidir_eco(vencido, acima, True, now) == "falhou"
    # pedido pós-reconexão força o envio mesmo sem silêncio
    assert decidir_eco(_conexao(eco_solicitado_em=now), None, None, now) == "enviar"


def test_ecos_sem_retorno_abrem_caida_e_sonda_tem_prioridade():
    ultimo = _local(2026, 9, 22, 4)
    assert avaliar_conexao(_sinais(eco_falhas_seguidas=ECO_FALHAS_MIN - 1)) == []
    achados = avaliar_conexao(
        _sinais(eco_falhas_seguidas=ECO_FALHAS_MIN, ultimo_inbound_em=ultimo)
    )
    assert [a.tipo for a in achados] == ["conexao_caida"]
    assert achados[0].detalhe["origem"] == "eco"
    assert "não recebe mensagens" in achados[0].detalhe["motivo"]
    # sonda ruim × 2 vence o eco: um só achado, origem sonda
    achados = avaliar_conexao(
        _sinais(
            sonda=_sonda(False, "Evolution informou conexão fechada"),
            sonda_falhas_seguidas=3,
            eco_falhas_seguidas=5,
        )
    )
    assert len(achados) == 1 and achados[0].detalhe["origem"] == "sonda"


# --- textos ------------------------------------------------------------------


def test_descrever_desconexao():
    assert (
        descrever_desconexao(401, "disconnected") == "aparelho desvinculado no celular"
    )
    assert descrever_desconexao(403, "disconnected") == "número bloqueado pelo WhatsApp"
    assert (
        descrever_desconexao(440, "disconnected") == "sessão aberta em outro aparelho"
    )
    assert descrever_desconexao(515, "disconnected") == "reinício pedido pelo WhatsApp"
    assert descrever_desconexao(None, "disconnected") == "conexão fechada"
    assert descrever_desconexao(None, "open") == "conectada"
    assert descrever_desconexao(None, "qr_pending") == "aguardando pareamento"
    assert descrever_desconexao(999, "error") == "erro na conexão"


def test_duracao_humana():
    assert duracao_humana(timedelta(minutes=35)) == "35 min"
    assert duracao_humana(timedelta(hours=6)) == "6 h"
    assert duracao_humana(timedelta(hours=3, minutes=5)) == "3 h 05 min"
    assert duracao_humana(timedelta(days=4, hours=12)) == "4 dias e 12 h"
    assert duracao_humana(timedelta(days=1)) == "1 dia"


def _sem_termo_tecnico(texto: str) -> None:
    assert "_" not in texto, texto
    assert " pro " not in f" {texto} " and " pra " not in f" {texto} ", texto


def test_linha_de_conexao_caida_nomeia_cliente_e_motivo():
    c = _conexao(connection_state="disconnected", desconexao_codigo=401)
    agora = _utc(2026, 9, 21, 9, 30)
    linha = formatar_linha(
        c,
        [
            (
                "conexao_caida",
                {
                    "motivo": "aparelho desvinculado no celular",
                    "desde": _utc(2026, 9, 16, 13, 28).isoformat(),
                },
            )
        ],
        now_utc=agora,
    )
    assert linha.startswith("Luis Fernando Macorini (1018) · Luis prod +556799068963: ")
    assert "aparelho desvinculado no celular — desde 16/09 09:28" in linha
    assert "última mensagem recebida 16/09 09:27" in linha
    _sem_termo_tecnico(linha)


def test_linha_de_silencio_traz_esperadas_e_o_estado_da_conexao():
    c = _conexao(ultimo_inbound_em=_local(2026, 9, 22, 8))
    agora = _local(2026, 9, 22, 14)
    linha = formatar_linha(
        c,
        [
            (
                "sem_atividade",
                {
                    "esperadas": 24.0,
                    "horas": 6.0,
                    "desde": _local(2026, 9, 22, 8).isoformat(),
                    "sonda_ok": True,
                },
            )
        ],
        now_utc=agora,
    )
    assert "sem mensagens há 6 h (esperadas ≈ 24) · conexão responde" in linha
    _sem_termo_tecnico(linha)
    linha2 = formatar_linha(
        c,
        [
            (
                "sem_atividade",
                {
                    "esperadas": 24.0,
                    "desde": _local(2026, 9, 22, 8).isoformat(),
                    "sonda_ok": False,
                },
            )
        ],
        now_utc=agora,
    )
    assert "conexão sem resposta" in linha2


def test_mensagem_agrupa_por_conexao_e_ordena_por_empresa():
    a = _conexao(
        id=9,
        empresa_id=1024,
        empresa_nome="Andreia",
        display_name="Loja",
        from_number="+5567999",
    )
    b = _conexao()
    agora = _utc(2026, 9, 22, 18)
    linhas = montar_mensagem(
        [
            (
                a,
                "sem_atividade",
                {
                    "esperadas": 12.0,
                    "desde": _utc(2026, 9, 22, 12).isoformat(),
                    "sonda_ok": True,
                },
            ),
            (
                b,
                "conexao_caida",
                {
                    "motivo": "conexão fechada",
                    "desde": _utc(2026, 9, 22, 17).isoformat(),
                },
            ),
            (
                b,
                "sem_atividade",
                {
                    "esperadas": 40.0,
                    "desde": _utc(2026, 9, 22, 12).isoformat(),
                    "sonda_ok": False,
                },
            ),
        ],
        now_utc=agora,
    )
    assert len(linhas) == 2
    assert linhas[0].startswith("Luis Fernando Macorini (1018)")
    assert "conexão fechada" in linhas[0] and "sem mensagens" in linhas[0]
    assert linhas[1].startswith("Andreia (1024) · Loja +5567999")
    for li in linhas:
        _sem_termo_tecnico(li)


def test_mensagem_de_normalizado():
    c = _conexao()
    agora = _utc(2026, 9, 21, 10)
    linhas = montar_mensagem(
        [
            (c, "conexao_caida", {"criado_em": _utc(2026, 9, 16, 22).isoformat()}),
            (c, "sem_atividade", {"criado_em": _utc(2026, 9, 16, 22).isoformat()}),
        ],
        resolvido=True,
        now_utc=agora,
    )
    assert linhas == [
        "Luis Fernando Macorini (1018) · Luis prod +556799068963: "
        "conectada de novo (ficou 4 dias e 12 h fora) · voltou a receber mensagens · "
        "última mensagem recebida 16/09 09:27"
    ]


# --- sonda e elegibilidade ---------------------------------------------------


def test_sonda_devida_por_provedor():
    agora = _utc(2026, 9, 22, 12)
    assert sonda_devida(_conexao(), agora) is True
    waba = _conexao(
        provider="waba", ultimo_health_check_at=agora - timedelta(minutes=30)
    )
    assert sonda_devida(waba, agora) is False
    assert sonda_devida(
        _conexao(provider="waba", ultimo_health_check_at=agora - timedelta(minutes=61)),
        agora,
    )
    assert sonda_devida(_conexao(provider="waba", ultimo_health_check_at=None), agora)


def test_conexao_nunca_pareada_nao_e_incidente():
    assert (
        monitoravel(_conexao(connection_state="qr_pending", ultimo_inbound_em=None))
        is False
    )
    # já recebeu antes e caiu para qr_pending (esperando reparear) → segue monitorada
    assert monitoravel(_conexao(connection_state="qr_pending")) is True
    assert (
        monitoravel(_conexao(connection_state="open", ultimo_inbound_em=None)) is True
    )
    assert isinstance(Achado("conexao_caida", {}), Achado)
