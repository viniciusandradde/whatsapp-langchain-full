"""E-mail institucional na allowlist não é mascarado (agente precisa fornecê-lo)."""

import importlib

import whatsapp_langchain.shared.guardrails.pii_redactor as pii


def _reload(monkeypatch, dominios: str):
    monkeypatch.setenv("EMAIL_ALLOWLIST_DOMINIOS", dominios)
    importlib.reload(pii)
    return pii


class TestEmailAllowlist:
    def test_institucional_preservado(self, monkeypatch):
        m = _reload(monkeypatch, "unigran.br")
        r = m.redact_pii("mande para biomedicina@unigran.br", mode="mask")
        assert "biomedicina@unigran.br" in r.text
        assert r.counts.get("email", 0) == 0

    def test_subdominio_institucional_preservado(self, monkeypatch):
        m = _reload(monkeypatch, "unigran.br")
        r = m.redact_pii("suporte@areaacademica.unigran.br", mode="mask")
        assert "suporte@areaacademica.unigran.br" in r.text

    def test_email_pessoal_ainda_mascarado(self, monkeypatch):
        m = _reload(monkeypatch, "unigran.br")
        r = m.redact_pii("meu email é joao.silva@gmail.com", mode="mask")
        assert "gmail.com" not in r.text or "@***" in r.text
        assert r.counts["email"] == 1

    def test_sem_allowlist_mascara_tudo(self, monkeypatch):
        m = _reload(monkeypatch, "")
        r = m.redact_pii("x@unigran.br", mode="mask")
        assert r.counts["email"] == 1


def teardown_module():
    importlib.reload(pii)
