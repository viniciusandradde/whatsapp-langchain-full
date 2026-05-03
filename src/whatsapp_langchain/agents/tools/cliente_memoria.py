"""Tools de memória estruturada por cliente (M5.b.2).

Diferente das tools de M5.b.1 (cliente_atendimento.py):
- get_cliente_anotacoes: notas livres dos operadores, sem busca semântica.
- read_cliente_memoria: fatos estruturados, busca semântica scope a
  (empresa, cliente).

Use save_cliente_fato pra guardar coisas que valem pra conversas FUTURAS,
não pra registrar passos da conversa atual (a anotação cobre isso).
"""

from __future__ import annotations

from typing import Annotated, Any

import structlog
from langchain_core.runnables.config import var_child_runnable_config
from langchain_core.tools import InjectedToolArg, tool

from whatsapp_langchain.shared import cliente_memoria as memoria
from whatsapp_langchain.shared.atendimento import get_atendimento_by_id
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.models import ClienteMemoriaInput

logger = structlog.get_logger()


def _extract_runtime_config(runtime: Any) -> dict[str, Any]:
    if runtime is not None:
        config = getattr(runtime, "config", None)
        if isinstance(config, dict):
            cfg = config.get("configurable", {})
            if isinstance(cfg, dict):
                return cfg
    cfg = var_child_runnable_config.get(None)
    if isinstance(cfg, dict):
        configurable = cfg.get("configurable", {})
        if isinstance(configurable, dict):
            return configurable
    return {}


async def _resolve_cliente_id(runtime: Any) -> tuple[int | None, int | None]:
    """Lê empresa_id direto do contexto e cliente_id via atendimento."""
    cfg = _extract_runtime_config(runtime)
    try:
        empresa_id = int(cfg["empresa_id"]) if cfg.get("empresa_id") else None
        atendimento_id = (
            int(cfg["atendimento_id"]) if cfg.get("atendimento_id") else None
        )
    except (TypeError, ValueError):
        return None, None
    if empresa_id is None or atendimento_id is None:
        return None, None
    pool = await get_pool()
    atd = await get_atendimento_by_id(pool, atendimento_id)
    if atd is None or atd.empresa_id != empresa_id:
        return empresa_id, None
    return empresa_id, atd.cliente_id


def _agent_user_id(runtime: Any) -> str:
    cfg = _extract_runtime_config(runtime)
    return f"agente:{cfg.get('user_id') or 'desconhecido'}"


@tool
async def read_cliente_memoria(
    query: str,
    *,
    runtime: Annotated[Any, InjectedToolArg()] = None,
) -> str:
    """Busca semanticamente fatos/preferências/perfil do cliente atual.

    Use no início da conversa pra recuperar contexto: "o que sei sobre
    esse cliente relacionado a X?". Argumento `query` deve ser a
    pergunta em linguagem natural (ex: "histórico de compras",
    "alergias", "forma de pagamento preferida").

    Retorna até 5 trechos relevantes. Vazio quando nada bate.
    """
    empresa_id, cliente_id = await _resolve_cliente_id(runtime)
    if empresa_id is None or cliente_id is None:
        return "contexto incompleto — não consigo buscar memórias."
    pool = await get_pool()
    try:
        results = await memoria.search_relevant(pool, empresa_id, cliente_id, query)
    except Exception as e:
        logger.warning("cliente_memoria_search_failed", error=str(e))
        return f"Não consegui buscar memórias agora: {e}"
    logger.info(
        "cliente_memoria_search",
        empresa_id=empresa_id,
        cliente_id=cliente_id,
        query_chars=len(query),
        hits=len(results),
    )
    if not results:
        return "Nenhuma memória relevante sobre esse cliente."
    lines = [
        f"- [{m.categoria}, relevância {score:.2f}] {m.conteudo}"
        for m, score in results
    ]
    return "Memórias relevantes:\n" + "\n".join(lines)


@tool
async def save_cliente_fato(
    categoria: str,
    conteudo: str,
    *,
    runtime: Annotated[Any, InjectedToolArg()] = None,
) -> str:
    """Salva fato estruturado sobre o cliente pra usar em conversas futuras.

    Use quando o cliente revelar algo importante e durável (NÃO use pra
    fluxo da conversa atual — pra isso use create_cliente_anotacao).

    Argumentos:
    - `categoria`: 'perfil' (dados estáveis: profissão, contexto de
      vida) | 'preferencia' (gostos: "prefere comunicação por email")
      | 'fato' (eventos: "comprou produto X em janeiro").
    - `conteudo`: texto curto (3-1000 chars). Use 1ª pessoa do cliente
      ou descrição neutra ("cliente prefere X", não "ele me disse X").

    Dedup automático — se já existe fato semanticamente similar, não
    duplica.
    """
    categoria = categoria.strip().lower()
    if categoria not in ("perfil", "preferencia", "fato"):
        return (
            "Categoria inválida — use 'perfil', 'preferencia' ou 'fato'."
        )
    conteudo = conteudo.strip()
    if len(conteudo) < 3:
        return "Conteúdo muito curto (mínimo 3 chars)."
    if len(conteudo) > 1000:
        conteudo = conteudo[:1000]
    empresa_id, cliente_id = await _resolve_cliente_id(runtime)
    if empresa_id is None or cliente_id is None:
        return "contexto incompleto."
    pool = await get_pool()
    user_id = _agent_user_id(runtime)
    try:
        out, created = await memoria.save_memoria(
            pool,
            empresa_id,
            cliente_id,
            ClienteMemoriaInput(
                categoria=categoria,
                conteudo=conteudo,
                source="agent_explicit",
            ),
            user_id=user_id,
        )
    except Exception as e:
        logger.warning("cliente_memoria_save_failed", error=str(e))
        return f"Não consegui salvar a memória: {e}"
    if not created:
        return f"Memória já existia (#{out.id}) — não dupliquei."
    return f"Memória salva (#{out.id}, {categoria})."
