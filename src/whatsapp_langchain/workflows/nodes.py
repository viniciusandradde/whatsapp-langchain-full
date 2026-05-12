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

from langchain_core.runnables import RunnableConfig
from langgraph.constants import END
from langgraph.types import Command, interrupt

from whatsapp_langchain.workflows.state import WorkflowState
from whatsapp_langchain.workflows.validators import validate_input


def _pool_from_config(config: RunnableConfig | None) -> Any:
    """Lê o pool injetado via config.configurable pelo runner.

    Pool não é msgpack-serializável → não pode viver no state. Quando o
    node não recebe config (testes locais sem runner), retorna None e o
    side effect vira no-op.
    """
    if config is None:
        return None
    return (config.get("configurable") or {}).get("pool")

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
    """Interrupt() pedindo texto. Valida (via `validators.py`) e salva em
    `vars[save_as]` no resume.

    Spec:
        type: ask_text
        prompt: str (renderizado com vars.*)
        save_as: str (chave em state.vars)
        validate: dict | None  — legacy ex: {"min_len": 2}
        validate_with: str | None  — MVP: "cpf"/"cnpj"/"cep"/"data_br"/"min_len:N"
        retry_message: str | None  — mensagem custom (default: errMsg do validator)
        next: str
    """
    save_as = spec["save_as"]
    prompt_template = spec["prompt"]
    # Aceita ambos: `validate` (dict legacy) ou `validate_with` (str MVP)
    validate_rule: Any = spec.get("validate_with") or spec.get("validate")
    custom_retry = spec.get("retry_message")

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
            ok, err = validate_input(str(answer or ""), validate_rule)
            if ok:
                break
            answer = interrupt(
                {
                    "kind": "ask_text",
                    "prompt": custom_retry or err,
                    "save_as": save_as,
                }
            )

        return {
            "vars": {save_as: answer},
            "history": [spec.get("__node_id__", f"ask_text:{save_as}")],
        }

    return node


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


def make_send_media_node(spec: dict) -> Callable:
    """Envia mídia (PDF, imagem, áudio) com URL pública + caption opcional.

    Spec:
        type: send_media
        url: str (HTTPS público — provider faz pull)
        content_type: str (ex: "application/pdf", "image/jpeg")
        caption: str | None
        next: str
    """
    url = spec["url"]
    content_type = spec.get("content_type", "application/octet-stream")
    caption_template = spec.get("caption", "")

    def node(state: WorkflowState) -> dict:
        vars_dict = state.get("vars") or {}
        caption = _render(caption_template, vars_dict) if caption_template else ""
        return {
            "outbox": [
                {
                    "kind": "media",
                    "url": url,
                    "content_type": content_type,
                    "caption": caption,
                }
            ],
            "history": [spec.get("__node_id__", "send_media")],
        }

    return node


def make_send_link_node(spec: dict) -> Callable:
    """Envia link clicável (texto + URL).

    Spec:
        type: send_link
        url: str
        text: str (pode usar {{vars.*}})
        next: str
    """
    url = spec["url"]
    text_template = spec.get("text", url)

    def node(state: WorkflowState) -> dict:
        vars_dict = state.get("vars") or {}
        text = _render(text_template, vars_dict)
        return {
            "outbox": [{"kind": "text", "text": f"{text}\n{url}"}],
            "history": [spec.get("__node_id__", "send_link")],
        }

    return node


def make_set_var_node(spec: dict) -> Callable:
    """Define variável estática ou calculada.

    Spec:
        type: set_var
        save_as: str
        value: str (renderizado com vars.*)
        next: str
    """
    save_as = spec["save_as"]
    value_template = spec.get("value", "")

    def node(state: WorkflowState) -> dict:
        vars_dict = state.get("vars") or {}
        value = _render(value_template, vars_dict)
        return {
            "vars": {save_as: value},
            "history": [spec.get("__node_id__", f"set_var:{save_as}")],
        }

    return node


def make_branch_node(spec: dict) -> Callable:
    """Branch condicional baseado em vars.

    Spec:
        type: branch
        when: list de [{condition: "vars.foo == 'bar'", next: "node_id"}]
        else: str (node_id default)

    `condition` é parser restrito (regex): aceita apenas comparações simples
    sobre vars. NÃO usa interpretador Python arbitrário.
    """
    branches = spec.get("when", [])
    else_target = spec.get("else", "__end__")

    def node(state: WorkflowState) -> Command:
        vars_dict = state.get("vars") or {}
        for branch in branches:
            cond = branch.get("condition", "")
            if _check_condition(cond, vars_dict):
                return Command(
                    update={"history": [spec.get("__node_id__", "branch")]},
                    goto=_resolve_goto(branch["next"]),
                )
        return Command(
            update={"history": [spec.get("__node_id__", "branch") + ":else"]},
            goto=_resolve_goto(else_target),
        )

    return node


# Regex muito restrita pra evitar interpretação arbitrária.
# Aceita apenas: `vars.<key> <op> '<value>'` com op em {==, !=, contains}.
_COND_RE = re.compile(r"^vars\.([a-zA-Z_][\w]*)\s*(==|!=|contains)\s*'([^']*)'$")


def _check_condition(cond: str, vars_dict: dict[str, Any]) -> bool:
    """Checa condição simples via regex pattern matching (sem interpreter)."""
    if not cond:
        return False
    m = _COND_RE.fullmatch(cond.strip())
    if not m:
        return False
    key, op, value = m.group(1), m.group(2), m.group(3)
    actual = str(vars_dict.get(key, "")).strip()
    if op == "==":
        return actual == value
    if op == "!=":
        return actual != value
    if op == "contains":
        return value in actual
    return False


def make_audit_event_node(spec: dict) -> Callable:
    """Grava evento em `workflow_evento` (mig 078).

    Spec:
        type: audit_event
        evento: str (ex: "lgpd_consented")
        next: str

    Side effect: usa pool injetado via config.configurable (set pelo runner).
    Best-effort: falha silenciosa se pool ausente (PoC sem audit DB).
    """
    evento = spec["evento"]

    async def node(
        state: WorkflowState, config: RunnableConfig | None = None
    ) -> dict:
        from whatsapp_langchain.workflows.audit import log_event

        pool = _pool_from_config(config)
        if pool is not None:
            await log_event(
                pool,
                atendimento_id=state.get("atendimento_id", 0),
                empresa_id=state.get("empresa_id", 0),
                node_id=spec.get("__node_id__", evento),
                evento=evento,
                workflow_version_id=state.get("workflow_version_id"),
            )
        return {
            "history": [spec.get("__node_id__", f"audit:{evento}")],
        }

    return node


def make_transfer_departamento_node(spec: dict) -> Callable:
    """Transfere atendimento pra um departamento (reusa shared/atendimento.py).

    Spec:
        type: transfer_departamento
        departamento_id: int
        message: str | None — texto enviado ao cliente após transferência
        next: str (geralmente "__end__")

    Side effect: UPDATE atendimento.departamento_id +
    transfer_atendimento_to_departamento (volta status='aguardando',
    limpa assigned_to_user_id).
    """
    departamento_id = spec.get("departamento_id")
    message_template = spec.get(
        "message",
        "Você foi transferido para o setor responsável."
        " Em breve um atendente irá te atender.",
    )

    async def node(
        state: WorkflowState, config: RunnableConfig | None = None
    ) -> dict:
        from whatsapp_langchain.shared.atendimento import (
            transfer_atendimento_to_departamento,
        )

        pool = _pool_from_config(config)
        atend_id = state.get("atendimento_id", 0)
        if pool is not None and atend_id and departamento_id:
            try:
                await transfer_atendimento_to_departamento(
                    pool, atend_id, int(departamento_id)
                )
            except Exception as exc:  # noqa: BLE001
                # Audit + segue (cliente recebe msg mesmo se DB falhar)
                import logging

                logging.getLogger(__name__).warning(
                    "workflow_transfer_dep_failed atend=%s dep=%s err=%s",
                    atend_id,
                    departamento_id,
                    exc,
                )
        rendered = _render(message_template, state.get("vars") or {})
        return {
            "outbox": [{"kind": "text", "text": rendered}] if rendered else [],
            "history": [spec.get("__node_id__", f"transfer_dep:{departamento_id}")],
        }

    return node


def make_handover_node(spec: dict) -> Callable:
    """Handover final: marca vars no metadata + manda atendimento pra fila
    humana com 'Resumo do Chamado'.

    Spec:
        type: handover
        departamento_id: int | None — se vier, transfere; senão fica em fila geral
        resumo_template: str — texto formatado com {{vars.*}} pra operador
        message_to_client: str — texto pro cliente (default: "Você está na fila")
        next: str (geralmente "__end__")

    Side effects:
    - UPDATE atendimento.metadata.vars_workflow ← state.vars (sync pro drawer)
    - Se departamento_id: transfer_atendimento_to_departamento
    - Outbox: msg pro cliente (não pro operador — operador vê via drawer)
    """
    departamento_id = spec.get("departamento_id")
    resumo_template = spec.get("resumo_template", "")
    message_to_client = spec.get(
        "message_to_client",
        "Você está na fila. Em breve um atendente irá te atender.",
    )

    async def node(
        state: WorkflowState, config: RunnableConfig | None = None
    ) -> dict:
        import json as _json

        pool = _pool_from_config(config)
        atend_id = state.get("atendimento_id", 0)
        vars_dict = state.get("vars") or {}
        # Pool não está mais em vars (vai via config), mas mantemos o filtro
        # `_` por segurança contra chaves internas adicionadas no futuro.
        clean_vars = {k: v for k, v in vars_dict.items() if not k.startswith("_")}
        resumo = _render(resumo_template, vars_dict) if resumo_template else ""

        if pool is not None and atend_id:
            try:
                # Sync vars pra metadata (drawer humano lê isso)
                payload = {**clean_vars}
                if resumo:
                    payload["_resumo_chamado"] = resumo
                async with pool.connection() as conn:
                    await conn.execute(
                        """
                        UPDATE atendimento
                           SET metadata = jsonb_set(
                                 COALESCE(metadata, '{}'::jsonb),
                                 '{vars_workflow}',
                                 COALESCE(metadata->'vars_workflow', '{}'::jsonb)
                                 || %s::jsonb
                               )
                         WHERE id = %s
                        """,
                        (_json.dumps(payload, ensure_ascii=False), atend_id),
                    )
                    await conn.commit()
            except Exception as exc:  # noqa: BLE001
                import logging

                logging.getLogger(__name__).warning(
                    "workflow_handover_metadata_sync_failed atend=%s err=%s",
                    atend_id,
                    exc,
                )

            if departamento_id:
                try:
                    from whatsapp_langchain.shared.atendimento import (
                        transfer_atendimento_to_departamento,
                    )

                    await transfer_atendimento_to_departamento(
                        pool, atend_id, int(departamento_id)
                    )
                except Exception as exc:  # noqa: BLE001
                    import logging

                    logging.getLogger(__name__).warning(
                        "workflow_handover_transfer_failed atend=%s dep=%s err=%s",
                        atend_id,
                        departamento_id,
                        exc,
                    )

        rendered_msg = _render(message_to_client, clean_vars)
        return {
            "outbox": [{"kind": "text", "text": rendered_msg}] if rendered_msg else [],
            "history": [spec.get("__node_id__", "handover")],
        }

    return node


def make_delegate_to_agent_node(spec: dict) -> Callable:
    """Delega controle pro agente IA (Sprint v2 #6).

    Spec:
        type: delegate_to_agent
        agent_slug: str — slug do agente IA (catálogo)
        message: str | None — opcional, texto antes de delegar
        next: str (geralmente "__end__")

    Side effect: UPDATE atendimento.agente_atual = agent_slug.
    Worker checa primeiro `agente_atual` — se setado, ignora workflow e
    roda agente IA. Pra voltar pro workflow, alguém faz UPDATE = NULL.
    """
    agent_slug = spec["agent_slug"]
    message_template = spec.get("message", "")

    async def node(
        state: WorkflowState, config: RunnableConfig | None = None
    ) -> dict:
        pool = _pool_from_config(config)
        atend_id = state.get("atendimento_id", 0)

        if pool is not None and atend_id:
            try:
                async with pool.connection() as conn:
                    await conn.execute(
                        "UPDATE atendimento SET agente_atual = %s WHERE id = %s",
                        (agent_slug, atend_id),
                    )
                    await conn.commit()
            except Exception as exc:  # noqa: BLE001
                import logging

                logging.getLogger(__name__).warning(
                    "workflow_delegate_failed atend=%s slug=%s err=%s",
                    atend_id,
                    agent_slug,
                    exc,
                )

        outbox: list[dict[str, Any]] = []
        if message_template:
            rendered = _render(message_template, state.get("vars") or {})
            if rendered:
                outbox.append({"kind": "text", "text": rendered})

        return {
            "outbox": outbox,
            "history": [spec.get("__node_id__", f"delegate:{agent_slug}")],
        }

    return node


NODE_FACTORIES: dict[str, Callable[[dict], Callable]] = {
    "send_messages": make_send_messages_node,
    "send_media": make_send_media_node,
    "send_link": make_send_link_node,
    "ask_text": make_ask_text_node,
    "ask_choice": make_ask_choice_node,
    "set_var": make_set_var_node,
    "branch": make_branch_node,
    "audit_event": make_audit_event_node,
    "transfer_departamento": make_transfer_departamento_node,
    "handover": make_handover_node,
    "delegate_to_agent": make_delegate_to_agent_node,
    # Nota: não há node type "end" — `next: "__end__"` no spec basta
    # (o compiler mapeia pra langgraph.constants.END).
}
