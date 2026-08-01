"""Compatibilidade: `vsa_tech` foi renomeado para `agente`.

Este diretório existe só para atravessar o deploy. `webhook.py` valida
`runtime.template_catalog in list_agents()` a CADA requisição, e
`list_agents()` lê o filesystem — então, entre o deploy do código novo e a
conclusão da migration que reescreve a coluna, um dos dois nomes estaria
inválido e todo o tráfego cairia em `AgentNotFoundError`.

Com o shim, os dois nomes resolvem durante a troca. Ele sai num deploy
posterior, quando nenhuma linha de `agente_ia.template_catalog` disser mais
`vsa_tech`.
"""

from whatsapp_langchain.agents.catalog.agente import build_graph

__all__ = ["build_graph"]
