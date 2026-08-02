"""Integrações externas com sistemas terceiros.

Cada subpacote nesta pasta cobre 1 provider com:
- `credentials.py` — CRUD em tabela específica + cripto
- `token.py` — OAuth/auth token cache
- `client.py` — async HTTP client
- `models.py` — Pydantic schemas
- `errors.py` — exceções tipadas

Pattern: tools do agente (`agents/tools/<provider>.py`) consomem o client
via `runtime.config.configurable` → resolve `empresa_id` → busca credenciais.
"""
