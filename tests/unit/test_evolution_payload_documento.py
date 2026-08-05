"""O nome do arquivo no payload do Evolution (mig 164).

Arquivo separado de `test_evolution_webhook.py` de propósito: aquele monta um
`TestClient` no import, o que trava a suíte fora do container. Aqui só se testa
a função pura de extração — que é onde o `fileName` era descartado.
"""

from whatsapp_langchain.server.routes.evolution_webhook import (
    _extract_message_payload,
)


def test_documento_traz_o_nome_do_arquivo():
    """`fileName` vinha no payload desde sempre e era jogado fora.

    Sem ele o worker adivinhava a extensão pelo mime, e a adivinhação mandava
    planilha para `doc.bin` — recusado pelo extrator (atendimento 1018-000664).
    """
    texto, url, mime, nome = _extract_message_payload(
        {
            "documentMessage": {
                "url": "https://mmg.whatsapp.net/x",
                "mimetype": "application/msword",
                "fileName": "Proposta Comercial.doc",
                "caption": "segue a proposta",
            }
        }
    )

    assert texto == "segue a proposta"
    assert url == "https://mmg.whatsapp.net/x"
    assert mime == "application/msword"
    assert nome == "Proposta Comercial.doc"


def test_documento_sem_nome_devolve_none():
    """Nome ausente ou vazio não pode virar string vazia.

    `""` passaria pelo `filename or inferido` do worker como valor válido e
    zeraria a inferência por mime.
    """
    _, _, _, nome = _extract_message_payload(
        {
            "documentMessage": {
                "url": "https://mmg.whatsapp.net/x",
                "mimetype": "application/pdf",
                "fileName": "   ",
            }
        }
    )
    assert nome is None


def test_audio_nao_tem_nome():
    """Nota de voz não tem nome — e citar `doc.ogg` seria pior que "um áudio"."""
    _, url, mime, nome = _extract_message_payload(
        {"audioMessage": {"url": "https://mmg.whatsapp.net/a", "mimetype": "audio/ogg"}}
    )
    assert url is not None
    assert mime == "audio/ogg"
    assert nome is None


def test_texto_puro_segue_com_quatro_campos():
    """A tupla cresceu de 3 para 4 — o caminho de texto tem que acompanhar."""
    texto, url, mime, nome = _extract_message_payload({"conversation": "bom dia"})
    assert texto == "bom dia"
    assert (url, mime, nome) == (None, None, None)


def test_tipo_nao_suportado_segue_com_quatro_campos():
    assert _extract_message_payload({"stickerMessage": {}}) == ("", None, None, None)
