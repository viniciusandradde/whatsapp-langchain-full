"""Exceções tipadas pra integração Wareline.

Hierarquia:
    WarelineError (base)
    ├── WarelineConfigError   — credenciais ausentes/inválidas no DB
    ├── WarelineAuthError     — OAuth falhou (401 do provider)
    ├── WarelineNotFoundError — recurso não existe (404)
    └── WarelineUnavailableError — 5xx, timeout, rede
"""

from __future__ import annotations


class WarelineError(Exception):
    """Base pra qualquer falha na integração Wareline."""


class WarelineConfigError(WarelineError):
    """Credenciais ausentes no DB ou Fernet key não configurado."""


class WarelineAuthError(WarelineError):
    """OAuth retornou 401 — credenciais erradas ou desabilitadas."""


class WarelineNotFoundError(WarelineError):
    """Recurso não encontrado (paciente, agenda, prestador)."""


class WarelineUnavailableError(WarelineError):
    """Provider down: 5xx, timeout, erro de rede."""
