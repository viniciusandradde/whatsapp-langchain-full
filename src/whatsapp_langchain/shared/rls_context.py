"""Sprint A.2.4 — Context vars de RLS para propagação implícita.

Propaga `empresa_id` (ou bypass) da request middleware até qualquer
`pool.connection()` chamado durante o handler. Implementação via
`contextvars.ContextVar` (asyncio-safe, isolado por task).

Pipeline:

    request → install_rls_context_middleware → set_request_context(empresa)
                                                 │
                                                 ▼
    route handler → pool.connection() → RlsAwarePool intercepta
                                          → lê context var
                                          → SET app.empresa_id na conn
                                          → yields conn
                                          → finally: limpa context na conn
                                            antes de devolver pro pool

Worker (sem request HTTP): chama `set_request_context()` diretamente no
início de cada `process_message()` ou usa `with_empresa_context()` helper
explícito (já existente em shared/db.py).

Cleanup no finally evita vazamento: conexão volta pro pool com
`app.empresa_id=''` (modo permissive), próxima request seta o seu.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Final

_empresa_var: Final[ContextVar[int | None]] = ContextVar(
    "rls_empresa_id", default=None
)
_bypass_var: Final[ContextVar[bool]] = ContextVar("rls_bypass", default=False)


def set_request_context(
    empresa_id: int | None = None, *, bypass: bool = False
) -> None:
    """Seta o context da request. Chamado pelo middleware no início."""
    _empresa_var.set(empresa_id)
    _bypass_var.set(bypass)


def get_request_context() -> tuple[int | None, bool]:
    """Retorna (empresa_id, bypass) do contextvar atual."""
    return _empresa_var.get(), _bypass_var.get()


def clear_request_context() -> None:
    """Reset pro default. Útil em testes."""
    _empresa_var.set(None)
    _bypass_var.set(False)


@contextmanager
def empresa_scope(empresa_id: int | None = None, *, bypass: bool = False):
    """Context manager pra setar context em bloco (testes, scripts ad-hoc).

    Uso:
        with empresa_scope(empresa_id=42):
            async with pool.connection() as conn:
                await conn.execute("SELECT * FROM cliente")  # filtrado
    """
    prev_empresa = _empresa_var.get()
    prev_bypass = _bypass_var.get()
    set_request_context(empresa_id, bypass=bypass)
    try:
        yield
    finally:
        _empresa_var.set(prev_empresa)
        _bypass_var.set(prev_bypass)
