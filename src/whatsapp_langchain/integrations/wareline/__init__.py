"""Integração Wareline ConecteHub (Hospital Mackenzie).

API REST com OAuth2 password grant (JWT 5min TTL). 4 endpoints:
- POST /services/auth/.../openid-connect/token (auth)
- GET /services/utilitarios-api/pacientes?cpfpac=X (paciente)
- GET /services/terapias-api/agendas/prestador (agenda do prestador)
- POST /services/terapias-api/agendas (criar agendamento)

Documentação completa em `docs/agentes/AgendamentoWareline.html`.
"""

from whatsapp_langchain.integrations.wareline.client import WarelineClient
from whatsapp_langchain.integrations.wareline.errors import (
    WarelineAuthError,
    WarelineError,
    WarelineNotFoundError,
    WarelineUnavailableError,
)
from whatsapp_langchain.integrations.wareline.models import (
    AgendaItem,
    AgendamentoResponse,
    CriarAgendamentoInput,
    Paciente,
)

__all__ = [
    "WarelineClient",
    "WarelineError",
    "WarelineAuthError",
    "WarelineNotFoundError",
    "WarelineUnavailableError",
    "Paciente",
    "AgendaItem",
    "CriarAgendamentoInput",
    "AgendamentoResponse",
]
