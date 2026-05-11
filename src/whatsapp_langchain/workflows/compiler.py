"""Compilador: pega `definicao_json` declarativa → CompiledStateGraph.

Schema de `definicao`:
    {
        "entry": "boas_vindas",      # node_id de partida
        "nodes": {
            "<node_id>": {
                "type": "send_messages" | "ask_text" | "ask_choice" | ...,
                ... spec específico ...
                "next": "<next_node_id>"  (não usado por ask_choice/branch)
            }
        }
    }

Sub-workflows (MVP #1): refs `wf:<slug>` em `next` ou `choices[].next` são
resolvidas via `compile_workflow_root(...)` que aceita dict de definições.
Detecta ciclos no grafo de refs (warn, não falha — ciclo runtime é navegação
válida tipo "voltar ao menu principal").
"""

from __future__ import annotations

import logging
from collections import deque
from typing import Any

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.constants import END, START
from langgraph.graph import StateGraph

from whatsapp_langchain.workflows.nodes import NODE_FACTORIES
from whatsapp_langchain.workflows.state import WorkflowState

logger = logging.getLogger(__name__)

# Prefixo de referência cross-workflow (sub-workflow)
_WF_PREFIX = "wf:"


def compile_workflow(
    definicao: dict[str, Any],
    *,
    checkpointer: BaseCheckpointSaver,
):
    """Compila um workflow ÚNICO (sem refs `wf:` resolvidas).

    Pra sub-workflows multi-arquivo, use `compile_workflow_root`.

    Args:
        definicao: dict com keys `entry` e `nodes`
        checkpointer: AsyncPostgresSaver (ou MemorySaver pra tests)

    Returns:
        CompiledStateGraph pronto pra `.ainvoke(state, config=...)`.
    """
    entry = definicao["entry"]
    nodes = definicao["nodes"]

    if entry not in nodes:
        raise ValueError(f"entry '{entry}' não está em nodes")

    builder: StateGraph = StateGraph(WorkflowState)

    # Adiciona nodes
    for node_id, spec in nodes.items():
        node_type = spec.get("type")
        if node_type not in NODE_FACTORIES:
            raise ValueError(
                f"node '{node_id}' tem type '{node_type}' desconhecido. "
                f"Suportados: {list(NODE_FACTORIES)}"
            )
        spec_with_id = {**spec, "__node_id__": node_id}
        factory = NODE_FACTORIES[node_type]
        builder.add_node(node_id, factory(spec_with_id))

    # Adiciona edges
    builder.add_edge(START, entry)
    for node_id, spec in nodes.items():
        node_type = spec.get("type")
        # Nodes que retornam Command(goto=...) — sem static edge
        if node_type in ("ask_choice", "branch", "end"):
            continue
        nxt = spec.get("next")
        if nxt is None:
            continue
        if nxt == "__end__" or nxt == END:
            builder.add_edge(node_id, END)
        else:
            if nxt not in nodes:
                raise ValueError(
                    f"node '{node_id}' aponta pra next='{nxt}' que não existe"
                )
            builder.add_edge(node_id, nxt)

    return builder.compile(checkpointer=checkpointer)


# === MVP #1: sub-workflows ===


def _extract_refs(spec: dict) -> list[str]:
    """Devolve lista de refs `wf:xxx` mencionadas em next ou choices."""
    refs: list[str] = []
    nxt = spec.get("next")
    if isinstance(nxt, str) and nxt.startswith(_WF_PREFIX):
        refs.append(nxt[len(_WF_PREFIX) :])
    for choice in spec.get("choices") or []:
        cn = choice.get("next")
        if isinstance(cn, str) and cn.startswith(_WF_PREFIX):
            refs.append(cn[len(_WF_PREFIX) :])
    return refs


def _collect_referenced_slugs(
    root_slug: str, definicoes: dict[str, dict[str, Any]]
) -> list[str]:
    """BFS coleta todos os slugs alcançáveis a partir de `root_slug`."""
    seen: set[str] = set()
    order: list[str] = []
    queue: deque[str] = deque([root_slug])
    while queue:
        slug = queue.popleft()
        if slug in seen:
            continue
        if slug not in definicoes:
            raise ValueError(
                f"sub-workflow 'wf:{slug}' referenciado mas não fornecido em definicoes"
            )
        seen.add(slug)
        order.append(slug)
        for spec in definicoes[slug]["nodes"].values():
            for ref in _extract_refs(spec):
                if ref not in seen:
                    queue.append(ref)
    return order


def _detect_ref_cycle(
    slugs: list[str], definicoes: dict[str, dict[str, Any]]
) -> list[str] | None:
    """DFS — retorna caminho do ciclo se existir (None senão).

    Ciclos NÃO são erro fatal — em runtime "voltar ao menu" é navegação
    válida. Mas warn pra detectar bugs de definição.
    """
    graph: dict[str, set[str]] = {}
    for slug in slugs:
        out_refs: set[str] = set()
        for spec in definicoes[slug]["nodes"].values():
            for ref in _extract_refs(spec):
                out_refs.add(ref)
        graph[slug] = out_refs

    WHITE, GRAY, BLACK = 0, 1, 2  # noqa: N806
    color: dict[str, int] = dict.fromkeys(slugs, WHITE)
    parent: dict[str, str | None] = dict.fromkeys(slugs, None)

    def dfs(u: str) -> list[str] | None:
        color[u] = GRAY
        for v in graph.get(u, ()):
            if color.get(v, WHITE) == WHITE:
                parent[v] = u
                cyc = dfs(v)
                if cyc:
                    return cyc
            elif color[v] == GRAY:
                # Cycle: reconstrói caminho v → ... → u → v
                path = [v, u]
                p = parent.get(u)
                while p and p != v:
                    path.append(p)
                    p = parent.get(p)
                path.append(v)
                return list(reversed(path))
        color[u] = BLACK
        return None

    for slug in slugs:
        if color[slug] == WHITE:
            cyc = dfs(slug)
            if cyc:
                return cyc
    return None


def compile_workflow_root(
    root_slug: str,
    definicoes: dict[str, dict[str, Any]],
    *,
    checkpointer: BaseCheckpointSaver,
):
    """Compila um workflow root + todos os sub-workflows referenciados.

    Args:
        root_slug: slug do workflow principal (ex: "menu_principal")
        definicoes: dict {slug: definicao_json} contendo root + todos os
            sub-workflows transitivamente referenciados via `wf:`
        checkpointer: compartilhado entre todos os compiled graphs

    Returns:
        CompiledStateGraph do root, com sub-workflows adicionados como
        nodes adicionais (LangGraph nativo).

    Atenção: na implementação MVP, o "subgraph" é apenas um node
    `entry-stub` que dispara `Command(goto=...)` pro entry do
    sub-workflow inline'd (todos os nodes de todos workflows ficam
    flat no parent graph com namespace `<slug>__<node_id>`). Subgraph
    LangGraph nativo (compile each + add_node(compiled)) tem
    limitação de state schema diferente — pra simplicidade do MVP,
    flat é mais previsível.
    """
    slugs = _collect_referenced_slugs(root_slug, definicoes)
    cycle = _detect_ref_cycle(slugs, definicoes)
    if cycle:
        logger.warning(
            "workflow_subgraph_ref_cycle root=%s path=%s "
            "(OK se for navegação 'voltar ao menu')",
            root_slug,
            " -> ".join(cycle),
        )

    builder: StateGraph = StateGraph(WorkflowState)

    # Adiciona nodes de todos os workflows com prefixo namespace
    for slug in slugs:
        defin = definicoes[slug]
        for node_id, spec in defin["nodes"].items():
            qualified = _qualify(slug, node_id)
            node_type = spec.get("type")
            if node_type not in NODE_FACTORIES:
                raise ValueError(
                    f"node '{slug}::{node_id}' tem type '{node_type}' desconhecido"
                )
            # Resolve refs `wf:` em choices/when/next pra qualified IDs
            spec_resolved = _rewrite_targets(spec, slug, definicoes)
            spec_with_id = {**spec_resolved, "__node_id__": qualified}
            factory = NODE_FACTORIES[node_type]
            builder.add_node(qualified, factory(spec_with_id))

    # START → entry do root
    root_entry = _qualify(root_slug, definicoes[root_slug]["entry"])
    builder.add_edge(START, root_entry)

    # Static edges (next que não é Command). Aqui usamos os specs ORIGINAIS
    # (não reescritos) pra preservar refs `wf:` — `_resolve_target` resolve.
    for slug in slugs:
        defin = definicoes[slug]
        for node_id, spec in defin["nodes"].items():
            qualified = _qualify(slug, node_id)
            node_type = spec.get("type")
            if node_type in ("ask_choice", "branch", "end"):
                continue
            nxt = spec.get("next")
            if nxt is None:
                continue
            if nxt == "__end__" or nxt == END:
                builder.add_edge(qualified, END)
            else:
                target = _resolve_target(slug, nxt, definicoes)
                builder.add_edge(qualified, target)

    return builder.compile(checkpointer=checkpointer)


def _qualify(slug: str, node_id: str) -> str:
    """Namespace node id por workflow (evita colisões cross-workflow)."""
    return f"{slug}__{node_id}"


def _resolve_target(
    current_slug: str, target: str, definicoes: dict[str, dict[str, Any]]
) -> str:
    """Resolve target string pra qualified node id.

    - `wf:other`         → `other__<entry of other>`
    - `wf:other:specific`→ `other__specific` (caso futuro)
    - `local_node`       → `<current_slug>__local_node`
    """
    if target.startswith(_WF_PREFIX):
        rest = target[len(_WF_PREFIX) :]
        if ":" in rest:
            slug, _, nid = rest.partition(":")
        else:
            slug = rest
            nid = definicoes[slug]["entry"]
        return _qualify(slug, nid)
    return _qualify(current_slug, target)


def _rewrite_targets(
    spec: dict,
    current_slug: str,
    definicoes: dict[str, dict[str, Any]],
) -> dict:
    """Reescreve `next`, `choices[].next`, `when[].next`, `else`
    no spec — resolvendo `wf:other` ou `local_node` para qualified IDs
    (formato `<slug>__<node_id>`) que o LangGraph reconhece.

    Mantém `__end__` intacto (compiler trata como END sentinel).
    """
    out = dict(spec)

    def resolve(tgt: str) -> str:
        if tgt in ("__end__", END):
            return "__end__"
        return _resolve_target(current_slug, tgt, definicoes)

    # `next` top-level
    nxt = out.get("next")
    if isinstance(nxt, str):
        out["next"] = resolve(nxt)

    # `choices[].next` (ask_choice)
    if "choices" in out:
        out["choices"] = [
            {**c, "next": resolve(c["next"])} if "next" in c else c
            for c in out["choices"]
        ]

    # `when[].next` e `else` (branch)
    if "when" in out:
        out["when"] = [
            {**w, "next": resolve(w["next"])} if "next" in w else w for w in out["when"]
        ]
    if "else" in out and isinstance(out["else"], str):
        out["else"] = resolve(out["else"])

    return out
