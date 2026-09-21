"""Disponibilidade real dos modelos em uso (21/09/2026) — regras puras e o
fallback do runtime, sem rede e sem banco.

Contexto: o agente da VSA ficou mudo das 08:20 às 10:00 com 404 "No allowed
providers" — o OpenRouter roteou `deepseek-v4.1-flash` para uma versão datada
servida só por provedores fp4, barrados pelo piso da ADR-001. A lista de
endpoints do apelido seguia com 22 provedores: só a chamada real revela.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from whatsapp_langchain.shared.ia_alertas import (
    AGENTE_FALHAS_JANELA_MIN,
    TIPOS_INDISPONIVEL,
    avaliar_condicoes,
    formatar_alerta,
    modelo_fora_de_circulacao,
)
from whatsapp_langchain.shared.llm import (
    ChatOpenAIResiliente,
    SondaModelo,
    classificar_sonda,
    erro_e_sem_provedor_permitido,
)

_ERRO_404 = (
    "Error code: 404 - {'error': {'message': \"No allowed providers are available "
    "for the selected model. Providers serving deepseek/deepseek-v4.1-flash-20260910: "
    "morph, relace\", 'code': 404}}"
)


# --- classificação da sonda ---------------------------------------------------


def test_sonda_responde_e_ok():
    s = classificar_sonda("google/gemini-3.1-flash-lite", 200, "", None)
    assert s.ok and not s.inexistente and not s.transitorio


def test_sonda_sem_provedor_permitido_mas_responde_sem_piso():
    s = classificar_sonda("deepseek/deepseek-v4.1-flash", 404, _ERRO_404, 200)
    assert not s.ok and s.sem_provedor_permitido and not s.inexistente
    assert "piso de quantização" in s.motivo


def test_sonda_sem_provedor_nem_sem_piso_e_inexistente():
    s = classificar_sonda("deepseek/deepseek-v4.1-flash", 404, _ERRO_404, 404)
    assert s.inexistente and not s.sem_provedor_permitido


def test_sonda_modelo_removido_e_saldo_e_transitorio():
    assert classificar_sonda("x/y", 404, "model not found", None).inexistente
    assert classificar_sonda("x/y", 400, "invalid model id", None).inexistente
    # 400 por parâmetro (modelo de áudio recusando texto puro) NÃO é indisponível —
    # deu falso "não existe" com openai/gpt-audio-mini em produção (21/09)
    audio = classificar_sonda(
        "openai/gpt-audio-mini", 400, "audio output requires modalities", None
    )
    assert audio.ok and not audio.inexistente and not audio.transitorio
    saldo = classificar_sonda("x/y", 402, "insufficient credits", None)
    assert saldo.ok and not saldo.inexistente  # não é culpa do modelo
    assert classificar_sonda("x/y", 429, "rate", None).transitorio
    assert classificar_sonda("x/y", 503, "", None).transitorio
    assert classificar_sonda("x/y", None, "", None).transitorio


def test_detecta_o_404_pelo_texto():
    assert erro_e_sem_provedor_permitido(RuntimeError(_ERRO_404))
    assert not erro_e_sem_provedor_permitido(
        RuntimeError("Error code: 404 - not found")
    )


# --- condições da Saúde de IA ---------------------------------------------------


_BASE = {"latencia_p50": 500.0, "throughput_p50": 40.0, "tinha_endpoints": True}
_SNAP = {
    "uptime_30m": 99.9,
    "latencia_p50": 500.0,
    "throughput_p50": 40.0,
    "endpoints": 22,
    "endpoints_permitidos": 9,
}
_OP = {"chamadas": 0, "erros": 0}


def _sonda(**kw) -> SondaModelo:
    base = dict(slug="deepseek/deepseek-v4.1-flash", ok=False, codigo=404, motivo="x")
    base.update(kw)
    return SondaModelo(**base)


def test_sonda_inexistente_abre_modelo_indisponivel_mesmo_com_endpoints_listados():
    achados = avaliar_condicoes(
        _SNAP, _BASE, _OP, _sonda(inexistente=True, motivo="sem provedor disponível")
    )
    assert [a["tipo"] for a in achados] == ["modelo_indisponivel"]
    assert achados[0]["detalhe"]["origem"] == "sonda"


def test_sonda_sem_piso_abre_sem_provedor_permitido_uma_vez():
    snap = {**_SNAP, "endpoints_permitidos": 0}
    achados = avaliar_condicoes(snap, _BASE, _OP, _sonda(sem_provedor_permitido=True))
    assert [a["tipo"] for a in achados] == ["sem_provedor_permitido"]


def test_catalogo_sem_endpoint_no_piso_abre_sem_sonda():
    snap = {**_SNAP, "endpoints_permitidos": 0}
    achados = avaliar_condicoes(snap, _BASE, _OP, None)
    assert [a["tipo"] for a in achados] == ["sem_provedor_permitido"]
    assert achados[0]["detalhe"]["origem"] == "catalogo"
    # a sonda respondendo com piso vence o catálogo desatualizado
    assert avaliar_condicoes(snap, _BASE, _OP, _sonda(ok=True, codigo=200)) == []


def test_sonda_transitoria_nao_muda_nada():
    assert avaliar_condicoes(_SNAP, _BASE, _OP, _sonda(transitorio=True)) == []


def test_textos_nomeiam_quem_usa_e_sem_termo_tecnico():
    usos = ["agente atendimento-cliente · VSA Tecnologia LTDA (1)"]
    t = formatar_alerta(
        "deepseek/deepseek-v4.1-flash",
        "modelo_indisponivel",
        {"motivo": "sem provedor disponível"},
        usos,
    )
    assert "modelo padrão" in t and "VSA Tecnologia LTDA (1)" in t
    t2 = formatar_alerta(
        "agente:1:atendimento-cliente",
        "agente_falhando",
        {
            "agente": "atendimento-cliente",
            "empresa": "VSA",
            "empresa_id": 1,
            "falhas": 5,
            "erro": "404",
        },
    )
    assert f"{AGENTE_FALHAS_JANELA_MIN} min" in t2 and "5 mensagens" in t2
    assert " pra " not in t and " pro " not in t


def test_fora_de_circulacao_so_para_os_tipos_certos():
    ind = {
        "a/x": "modelo_indisponivel:sem provedor disponível",
        "b/y": "sem_provedor_permitido:só fp4",
        "c/z": "modelo_sumiu:Modelo sem endpoints",
    }
    assert modelo_fora_de_circulacao("a/x", ind)
    assert modelo_fora_de_circulacao("c/z", ind)
    assert not modelo_fora_de_circulacao("b/y", ind)  # degrada, mas responde
    assert not modelo_fora_de_circulacao("d/w", ind)
    assert not modelo_fora_de_circulacao(None, ind)
    assert TIPOS_INDISPONIVEL == {"modelo_indisponivel", "modelo_sumiu"}


# --- fallback do runtime --------------------------------------------------------


def _resultado(texto: str) -> ChatResult:
    return ChatResult(generations=[ChatGeneration(message=AIMessage(content=texto))])


async def test_fallback_repete_sem_piso_no_404_de_provedor():
    modelo = ChatOpenAIResiliente(
        model="deepseek/deepseek-v4.1-flash",
        api_key="x",
        base_url="http://localhost:1",
        extra_body={"provider": {"quantizations": ["fp8"]}},
    )
    chamadas: list[dict | None] = []

    async def _fake(self, messages, stop=None, run_manager=None, **kw):
        chamadas.append(self.extra_body)
        if self.extra_body:
            raise RuntimeError(_ERRO_404)
        return _resultado("ok sem piso")

    with patch("langchain_openai.ChatOpenAI._agenerate", new=_fake):
        r = await modelo._agenerate([HumanMessage(content="oi")])
    assert r.generations[0].message.content == "ok sem piso"
    assert chamadas == [{"provider": {"quantizations": ["fp8"]}}, None]
    # o modelo original continua com o piso para a próxima chamada
    assert modelo.extra_body == {"provider": {"quantizations": ["fp8"]}}


async def test_fallback_nao_engole_outros_erros_nem_repete_sem_piso():
    modelo = ChatOpenAIResiliente(
        model="google/gemini-3.1-flash-lite", api_key="x", base_url="http://localhost:1"
    )
    with (
        patch(
            "langchain_openai.ChatOpenAI._agenerate",
            new=AsyncMock(side_effect=RuntimeError(_ERRO_404)),
        ),
        pytest.raises(RuntimeError),
    ):
        await modelo._agenerate(
            [HumanMessage(content="oi")]
        )  # sem extra_body: não há o que relaxar
    com_piso = ChatOpenAIResiliente(
        model="deepseek/x",
        api_key="x",
        base_url="http://localhost:1",
        extra_body={"provider": {}},
    )
    with (
        patch(
            "langchain_openai.ChatOpenAI._agenerate",
            new=AsyncMock(side_effect=RuntimeError("Error code: 429 - rate limited")),
        ),
        pytest.raises(RuntimeError),
    ):
        await com_piso._agenerate([HumanMessage(content="oi")])
