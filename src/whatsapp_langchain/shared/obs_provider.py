"""Qual provedor de observabilidade usar — preferência da UI + disponibilidade.

Extraído de `server/routes/traces.py`, onde nasceu. Ficar dentro de uma rota
fazia com que ninguém mais conseguisse reusar: foi por isso que o auto-dataset
do sandbox nasceu falando com o Langfuse hardcoded, e continuou apontando pro
host morto mesmo depois de o admin escolher LangSmith na tela.

Nenhuma mudança de comportamento na extração — as funções são as mesmas, só
deixaram de ser privadas de um módulo de rota.
"""

from __future__ import annotations

import structlog

from whatsapp_langchain.shared.app_setting import get_obs_provider_preferido
from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.db import get_pool

logger = structlog.get_logger()


def langfuse_configurado() -> bool:
    """Tem credencial de Langfuse.

    **Não** quer dizer que o Langfuse está no ar: as chaves seguem no `.env`
    mesmo com os containers desligados (foi o caso entre 27/07 e agora). Quem
    precisa saber se responde tem que perguntar pro host.
    """
    return settings.langfuse_enabled


def langsmith_configurado() -> bool:
    return bool(settings.langchain_api_key and settings.langchain_project)


def active_provider() -> str | None:
    """Resolução automática: langfuse > langsmith > None."""
    if langfuse_configurado():
        return "langfuse"
    if langsmith_configurado():
        return "langsmith"
    return None


async def provider_efetivo() -> str | None:
    """Provider a usar, considerando a preferência gravada na UI (mig 141).

    Existe porque a resolução por env é uma armadilha operacional: desligar os
    containers do Langfuse NÃO muda `settings.langfuse_enabled` (as chaves
    seguem no .env), então `/traces` continuaria apontando pro host morto.

    `auto` mantém o comportamento antigo. Escolha explícita que aponta pra
    provider sem credencial cai no automático em vez de devolver nada — o
    admin vê a lista do outro provider, não uma tela vazia sem explicação.
    """
    pool = await get_pool()
    preferido = await get_obs_provider_preferido(pool)

    if preferido == "langfuse" and langfuse_configurado():
        return "langfuse"
    if preferido == "langsmith" and langsmith_configurado():
        return "langsmith"

    if preferido != "auto":
        logger.warning(
            "obs_provider_preferido_sem_credencial",
            preferido=preferido,
            acao="caindo pra resolucao automatica",
        )
    return active_provider()
