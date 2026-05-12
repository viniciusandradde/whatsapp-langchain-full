"""Workflows estilo state-machine com LangGraph (Sprint Workflow-LangGraph PoC).

Sistema de fluxos conversacionais declarativos com state machine,
`interrupt()` + checkpointing nativos do LangGraph.

Status: PoC em branch `proposta/menu-langgraph-workflows`. Não em prod.
Veja `docs/PROPOSTA_WORKFLOWS_LANGGRAPH.md` pra design completo.

Exports principais:
- `WorkflowState` — TypedDict do state que LangGraph persiste
- `compile_workflow` — pega JSON declarativo → CompiledStateGraph
- `WorkflowRunner.process` — runtime que integra com worker
"""

from whatsapp_langchain.workflows.compiler import compile_workflow
from whatsapp_langchain.workflows.runner import WorkflowRunner
from whatsapp_langchain.workflows.state import WorkflowState

__all__ = ["WorkflowState", "compile_workflow", "WorkflowRunner"]
