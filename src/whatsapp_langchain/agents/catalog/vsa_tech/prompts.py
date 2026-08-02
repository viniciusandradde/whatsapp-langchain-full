"""Compatibilidade — o loader importa `catalog.<template>.prompts` por nome.

Sem este arquivo o `import_module` falharia dentro de um `try/except` que só
emite warning, e o agente subiria **sem system prompt**, respondendo como se
nada tivesse acontecido.
"""

from whatsapp_langchain.agents.catalog.agente.prompts import SYSTEM_PROMPT

__all__ = ["SYSTEM_PROMPT"]
