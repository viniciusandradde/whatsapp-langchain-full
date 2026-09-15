"""`_montar_configurable` — o configurable do invoke leva referência, não conteúdo.

O `AsyncPostgresSaver` copia o configurable inteiro pra `checkpoints.metadata`
a cada checkpoint do run. Um `data:...;base64` de áudio ali virou 1,9 GB em
produção (2026-09-15, uma linha com 71 MB). Estes testes travam a regra: só
URL http(s) passa; o resto vira None e a referência `message_queue_id` vai no
lugar, pra `agents/tools/midia.py` resolver na hora.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from whatsapp_langchain.shared.models import MessageQueue
from whatsapp_langchain.worker.processor import _montar_configurable

_BASE64_AUDIO = "data:audio/ogg;base64," + "A" * 200_000


def _msg(**kw) -> MessageQueue:
    base = dict(
        id=42,
        empresa_id=1018,
        atendimento_id=7,
        phone_number="+5511999999999",
        agent_id="vsa_tech",
        thread_id="+5511999999999:vsa_tech",
        incoming_message="",
    )
    base.update(kw)
    return MessageQueue(**base)


def test_base64_inline_nao_entra_no_configurable():
    cfg = _montar_configurable(
        _msg(media_url=_BASE64_AUDIO, media_type="audio/ogg"), None
    )
    assert cfg["media_url"] is None
    assert cfg["message_queue_id"] == 42
    assert cfg["media_type"] == "audio/ogg"


def test_url_http_passa_intacta():
    cfg = _montar_configurable(
        _msg(media_url="https://media.example.com/a.ogg", media_type="audio/ogg"),
        None,
    )
    assert cfg["media_url"] == "https://media.example.com/a.ogg"
    assert cfg["message_queue_id"] == 42


def test_sem_midia_continua_com_referencia():
    cfg = _montar_configurable(_msg(), None)
    assert cfg["media_url"] is None
    assert cfg["media_type"] is None
    assert cfg["message_queue_id"] == 42


def test_chaves_de_escopo_preservadas():
    cfg = _montar_configurable(_msg(), None)
    assert cfg["thread_id"] == "+5511999999999:vsa_tech"
    assert cfg["user_id"] == "+5511999999999"
    assert cfg["empresa_id"] == 1018
    assert cfg["atendimento_id"] == 7


def test_base_conhecimento_ids_vem_do_runtime():
    runtime = SimpleNamespace(base_conhecimento_ids=[3, 5])
    assert _montar_configurable(_msg(), runtime)["base_conhecimento_ids"] == [3, 5]
    assert _montar_configurable(_msg(), None)["base_conhecimento_ids"] == []


def test_configurable_cabe_em_1kb_mesmo_com_midia_inline():
    """Guarda geral: o que vai pro checkpoint tem que ser pequeno, sempre."""
    cfg = _montar_configurable(
        _msg(media_url=_BASE64_AUDIO, media_type="audio/ogg"),
        SimpleNamespace(base_conhecimento_ids=list(range(20))),
    )
    assert len(json.dumps(cfg)) < 1024
