"""Integração WhatsApp Cloud API (Meta WABA).

Submódulos:
- `models`: Pydantic shapes da Graph API
- `oauth`: Embedded Signup OAuth Web flow (1-clique)
- `client`: Outbound + storage de credenciais cifradas
- `webhook`: Inbound (HMAC validation + payload normalize)
- `templates`: Message Templates (HSM) — submeter/listar/sync/enviar
"""
