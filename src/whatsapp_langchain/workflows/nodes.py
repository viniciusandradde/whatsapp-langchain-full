"""Node factories — funções que retornam callables LangGraph-compatíveis.

Regra crítica (Sprint v2 #2): nodes que pedem input chamam `interrupt()`
na PRIMEIRA linha. Side effects ficam após o interrupt (resume reexecuta
o node inteiro do início — qualquer DB write/send_message antes do
interrupt DUPLICA na retomada).

Tipos do PoC (4):
- `send_messages` — append mensagens estáticas no outbox
- `ask_text` — interrupt() pedindo texto livre, valida, salva em vars
- `ask_choice` — interrupt() pedindo 1-N, Command(goto=...)
- `end` — termina workflow

Versão completa (15 tipos) está no roadmap MVP — `docs/PROPOSTA_WORKFLOWS_LANGGRAPH.md`.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from langgraph.constants import END
from langgraph.types import Command, interrupt

from whatsapp_langchain.workflows.state import WorkflowState

# Map "__end__"/"end" no spec → langgraph END sentinel
# (usado por ask_choice → Command(goto=...))
_END_ALIASES = {"__end__", "end", END}


def _resolve_goto(target: str) -> str:
    """Normaliza target de Command.goto: '__end__' / 'end' → END sentinel."""
    return END if target in _END_ALIASES else target


def _render(template: str, vars_dict: dict[str, Any]) -> str:
    """Substituição mínima de `{{vars.foo}}` por `vars_dict["foo"]`.

    Versão MVP usa `shared/variavel.py::render_template` com namespaces
    completos (empresa.*, data.*, cliente.*). PoC se contenta com vars.
    """
    if not template:
        return ""

    def replace(match: re.Match) -> str:
        path = match.group(1).strip()
        if path.startswith("vars."):
            key = path[5:]
            return str(vars_dict.get(key, match.group(0)))
        return match.group(0)

    return re.sub(r"\{\{([^}]+)\}\}", replace, template)


def make_send_messages_node(spec: dict) -> Callable:
    """Append `spec["messages"]` ao outbox. Side effect (POST-interrupt safe).

    Spec:
        type: send_messages
        messages: [str, ...]
        next: str (node id)
    """
    messages = spec.get("messages", [])

    def node(state: WorkflowState) -> dict:
        vars_dict = state.get("vars") or {}
        rendered = [_render(m, vars_dict) for m in messages]
        return {
            "outbox": [{"kind": "text", "text": m} for m in rendered],
            "history": [spec.get("__node_id__", "send_messages")],
        }

    return node


def make_ask_text_node(spec: dict) -> Callable:
    """Interrupt() pedindo texto. Salva em `vars[save_as]` no resume.

    Spec:
        type: ask_text
        prompt: str (renderizado com vars.*)
        save_as: str (chave em state.vars)
        validate: dict | None  — ex: {"min_len": 2}
        retry_message: str | None
        next: str
    """
    save_as = spec["save_as"]
    prompt_template = spec["prompt"]
    validate_cfg = spec.get("validate") or {}
    retry_msg = spec.get("retry_message", "Resposta inválida. Tente de novo.")

    def node(state: WorkflowState) -> dict:
        # ⚠ interrupt() PRIMEIRO — Sprint v2 #2
        vars_dict = state.get("vars") or {}
        prompt = _render(prompt_template, vars_dict)

        answer = interrupt(
            {
                "kind": "ask_text",
                "prompt": prompt,
                "save_as": save_as,
            }
        )

        # Validação pós-resume (re-prompt se inválido via loop em interrupt)
        while True:
            ok, _err = _validate_answer(answer, validate_cfg)
            if ok:
                break
            answer = interrupt(
                {
                    "kind": "ask_text",
                    "prompt": retry_msg,
                    "save_as": save_as,
                }
            )

        return {
            "vars": {save_as: answer},
            "history": [spec.get("__node_id__", f"ask_text:{save_as}")],
        }

    return node


def _validate_answer(answer: Any, cfg: dict) -> tuple[bool, str]:
    """Validators básicos do PoC (MVP adiciona validators_br)."""
    if not cfg:
        return True, ""
    text = str(answer or "").strip()
    min_len = cfg.get("min_len")
    if min_len is not None and len(text) < int(min_len):
        return False, f"Mínimo {min_len} caracteres."
    return True, ""


def make_ask_choice_node(spec: dict) -> Callable:
    """Interrupt() pedindo escolha 1-N. Command(goto=choice.next) no resume.

    Spec:
        type: ask_choice
        prompt: str
        choices: [{label, value, next}, ...]
        retry_message: str | None
    """
    prompt_template = spec["prompt"]
    choices = spec["choices"]
    retry_msg = spec.get("retry_message", "Opção inválida.")

    def node(state: WorkflowState) -> Command:
        # ⚠ interrupt() PRIMEIRO
        vars_dict = state.get("vars") or {}
        prompt = _render(prompt_template, vars_dict)
        rendered_prompt = _format_choice_prompt(prompt, choices)

        while True:
            answer = interrupt(
                {
                    "kind": "ask_choice",
                    "prompt": rendered_prompt,
                    "choices": [
                        {"label": c["label"], "value": c["value"]} for c in choices
                    ],
                }
            )
            chosen = _match_choice(answer, choices)
            if chosen is not None:
                return Command(
                    update={
                        "history": [
                            spec.get("__node_id__", "ask_choice")
                            + f":{chosen['value']}"
                        ],
                    },
                    goto=_resolve_goto(chosen["next"]),
                )
            rendered_prompt = retry_msg

    return node


def _format_choice_prompt(base: str, choices: list[dict]) -> str:
    """Adiciona lista numerada `[1] Label` ao final do prompt."""
    options = "\n".join(f"[{c['value']}] {c['label']}" for c in choices)
    return f"{base}\n\n{options}"


def _match_choice(answer: Any, choices: list[dict]) -> dict | None:
    """Match exato `value` (string) — case-insensitive."""
    if answer is None:
        return None
    norm = str(answer).strip().lower()
    for c in choices:
        if str(c["value"]).lower() == norm:
            return c
    return None


NODE_FACTORIES: dict[str, Callable[[dict], Callable]] = {
    "send_messages": make_send_messages_node,
    "ask_text": make_ask_text_node,
    "ask_choice": make_ask_choice_node,
    # Nota: não há node type "end" — `next: "__end__"` no spec basta
    # (o compiler mapeia pra langgraph.constants.END).
}
