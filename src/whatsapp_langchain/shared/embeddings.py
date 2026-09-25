"""Cliente de embeddings da OpenRouter que respeita a chave da empresa (ADR-007).

`OpenAIEmbeddings` fixa a chave ao ser criado, e a base de conhecimento
mantinha UM singleton para o processo inteiro — com chave por empresa isso
mandaria o embedding de todo mundo pela chave de quem chamou primeiro.
Aqui há um cliente por chave (indexado pelo hash dela, não pela chave), e a
escolha acontece na hora da chamada, pelo contexto (`chave_openrouter`).

A memória semântica do LangGraph (`shared/db.py::resolve_store_index_config`)
NÃO passa por aqui de propósito: o `AsyncPostgresStore` embeda numa task de
fundo, sem o contexto da empresa — fica na chave da plataforma (custo
desprezível, e não há como acertar a empresa de lá).
"""

from __future__ import annotations

import hashlib

from langchain_openai import OpenAIEmbeddings
from pydantic import SecretStr

from whatsapp_langchain.shared.config import settings
from whatsapp_langchain.shared.openrouter_chave import chave_openrouter

_por_chave: dict[str, OpenAIEmbeddings] = {}


def _marca(chave: SecretStr | None) -> str:
    if chave is None:
        return "-"
    return hashlib.sha256(chave.get_secret_value().encode("utf-8")).hexdigest()[:16]


def embeddings_openrouter() -> OpenAIEmbeddings:
    """Cliente de embeddings para a chave em uso neste contexto."""
    chave = chave_openrouter()
    marca = _marca(chave)
    cliente = _por_chave.get(marca)
    if cliente is None:
        cliente = OpenAIEmbeddings(
            model=settings.embedding_model,
            base_url=settings.openrouter_base_url,
            api_key=SecretStr(chave.get_secret_value()) if chave else None,
        )
        _por_chave[marca] = cliente
    return cliente


def limpar_clientes() -> None:
    """Para testes."""
    _por_chave.clear()
