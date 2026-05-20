"""Integração Evolution API (WhatsApp não-oficial, Baileys).

Submódulos:
- `admin`: ops admin (create/connect/disconnect/QR de instances)
- `client`: re-export do `EvolutionClient` (outbound de mensagens)

`EvolutionClient` continua em `worker.evolution_client` (não movido pra evitar
quebrar imports espalhados). Re-exportamos aqui pra novos callers usarem
o namespace `integrations.evolution`.
"""

from whatsapp_langchain.worker.evolution_client import EvolutionClient

__all__ = ["EvolutionClient"]
