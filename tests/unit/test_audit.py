"""Tests pra audit log helpers (Fase 0.1)."""

from __future__ import annotations

from whatsapp_langchain.shared.audit import diff_dicts


def test_diff_dicts_pega_so_mudancas():
    before = {"nome": "João", "email": "j@x.com", "score": 50}
    after = {"nome": "João", "email": "joao@x.com", "score": 60}
    out = diff_dicts(before, after)
    assert out == {
        "before": {"email": "j@x.com", "score": 50},
        "after": {"email": "joao@x.com", "score": 60},
    }


def test_diff_dicts_campos_adicionados():
    before = {"nome": "X"}
    after = {"nome": "X", "telefone": "+55..."}
    out = diff_dicts(before, after)
    assert out == {
        "before": {"telefone": None},
        "after": {"telefone": "+55..."},
    }


def test_diff_dicts_campos_removidos():
    before = {"nome": "X", "obsoleto": "valor"}
    after = {"nome": "X"}
    out = diff_dicts(before, after)
    assert out == {
        "before": {"obsoleto": "valor"},
        "after": {"obsoleto": None},
    }


def test_diff_dicts_iguais():
    same = {"a": 1, "b": "txt"}
    assert diff_dicts(same, same) == {"before": {}, "after": {}}


def test_diff_dicts_none_inputs():
    assert diff_dicts(None, {"a": 1}) == {"before": {"a": None}, "after": {"a": 1}}
    assert diff_dicts({"a": 1}, None) == {"before": {"a": 1}, "after": {"a": None}}
    assert diff_dicts(None, None) == {"before": {}, "after": {}}
