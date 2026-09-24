"""Texto do modelo (HSM) gravado na timeline (mig 202)."""

from whatsapp_langchain.integrations.waba.templates import texto_do_template

HELLO_WORLD = [
    {"text": "Hello World", "type": "HEADER", "format": "TEXT"},
    {"text": "Welcome and congratulations!!", "type": "BODY"},
    {"text": "WhatsApp Business Platform sample message", "type": "FOOTER"},
]


def test_hello_world_cabecalho_corpo_rodape():
    assert texto_do_template(HELLO_WORLD) == (
        "*Hello World*\n\nWelcome and congratulations!!\n\n"
        "_WhatsApp Business Platform sample message_"
    )


def test_troca_variaveis_numeradas_e_nomeadas():
    comps = [
        {"type": "HEADER", "format": "TEXT", "text": "Pedido {{1}}"},
        {"type": "BODY", "text": "Olá {{1}}, seu pedido {{ 2 }} saiu. {{nome}}"},
    ]
    out = texto_do_template(comps, {"1": "Ana", "2": "#42", "nome": "Loja X"})
    assert out == "*Pedido Ana*\n\nOlá Ana, seu pedido #42 saiu. Loja X"


def test_variavel_sem_valor_fica_visivel():
    out = texto_do_template(
        [{"type": "BODY", "text": "Oi {{1}} e {{2}}"}], {"1": "Ana"}
    )
    assert out == "Oi Ana e {{2}}"


def test_cabecalho_de_midia_vira_marcador():
    comps = [{"type": "HEADER", "format": "IMAGE"}, {"type": "BODY", "text": "Veja"}]
    assert texto_do_template(comps) == "[imagem]\n\nVeja"


def test_sem_corpo_devolve_vazio():
    assert texto_do_template([{"type": "HEADER", "format": "TEXT", "text": "x"}]) == ""
    assert texto_do_template(None) == ""
