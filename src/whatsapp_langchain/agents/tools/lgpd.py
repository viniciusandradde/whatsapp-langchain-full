"""Tools LGPD pra agentes IA hospitalares.

2 tools obrigatórias em todos os agentes de saúde:

- `verify_patient_identity(nome, data_nasc, cpf_ultimos4)`: valida 3
  campos contra `cliente` da empresa ativa antes de tratar dado sensível.
- `log_lgpd_event(event_type, details)`: registra evento de auditoria.

Ambas extraem `empresa_id`, `atendimento_id` e `agent_slug` do
`runtime.config.configurable` (preenchido pelo worker).

Compliance: LGPD Art. 37 (auditoria de acessos) + CFM (sigilo médico).
"""

from __future__ import annotations

import json
from typing import Annotated, Any

import structlog
from langchain_core.runnables.config import var_child_runnable_config
from langchain_core.tools import InjectedToolArg, tool

from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.lgpd import (
    EVENT_TYPES,
    LGPDEventTypeError,
    log_event,
    verify_cliente_identity,
)

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


def _extract_context(runtime: Any) -> dict[str, Any]:
    """Lê empresa_id, atendimento_id, cliente_id, agent_slug do runtime."""
    cfg = _extract_runtime_config(runtime)
    out: dict[str, Any] = {
        "empresa_id": None,
        "atendimento_id": None,
        "cliente_id": None,
        "agent_slug": cfg.get("agent_id") or cfg.get("agent_slug"),
    }
    for key in ("empresa_id", "atendimento_id", "cliente_id"):
        v = cfg.get(key)
        if v is not None:
            try:
                out[key] = int(v)
            except (TypeError, ValueError):
                pass
    return out


@tool
async def verify_patient_identity(
    nome: str,
    data_nasc: str,
    cpf_ultimos4: str,
    *,
    runtime: Annotated[Any, InjectedToolArg()] = None,
) -> str:
    """Valida identidade de paciente contra a base do hospital.

    Use ANTES de tratar qualquer dado sensível (CPF completo, prontuário,
    agendamento existente). Retorna JSON com `verified: true/false`.

    Args:
        nome: Nome completo do paciente
        data_nasc: Data de nascimento (dd/mm/aaaa)
        cpf_ultimos4: Últimos 4 dígitos do CPF

    Returns:
        JSON string. Sucesso: {"verified": true, "patient_id": 123}.
        Falha: {"verified": false, "reason": "<causa>"}.
        Causas possíveis: nao_encontrado, nome_invalido, data_invalida,
        cpf_invalido, multiplos_matches, empresa_id_ausente, erro_interno.

    Sempre registra o resultado via log_lgpd_event (identity_verified ou
    identity_verification_failed) automaticamente.
    """
    ctx = _extract_context(runtime)
    empresa_id = ctx["empresa_id"]
    atendimento_id = ctx["atendimento_id"]
    agent_slug = ctx["agent_slug"]

    if not empresa_id:
        result = {"verified": False, "reason": "empresa_id_ausente"}
        return json.dumps(result, ensure_ascii=False)

    pool = await get_pool()
    try:
        result = await verify_cliente_identity(
            pool,
            empresa_id,
            nome=nome,
            data_nascimento=data_nasc,
            cpf_ultimos4=cpf_ultimos4,
        )
    except Exception as exc:
        logger.exception("verify_patient_identity_failed", error=str(exc))
        return json.dumps(
            {"verified": False, "reason": "erro_interno"}, ensure_ascii=False
        )

    # Auto-log do resultado
    try:
        event_type = (
            "identity_verified"
            if result.get("verified")
            else "identity_verification_failed"
        )
        details = {
            "nome_provided": nome[:80],
            "match_reason": result.get("reason"),
        }
        if result.get("verified"):
            details["patient_id"] = result["patient_id"]

        await log_event(
            pool,
            empresa_id=empresa_id,
            event_type=event_type,
            details=details,
            atendimento_id=atendimento_id,
            cliente_id=result.get("patient_id") if result.get("verified") else None,
            agent_slug=agent_slug,
        )
    except Exception as exc:
        logger.warning("lgpd_auto_log_failed", error=str(exc))

    return json.dumps(result, ensure_ascii=False)


@tool
async def log_lgpd_event(
    event_type: str,
    details: dict[str, Any] | str | None = None,
    *,
    runtime: Annotated[Any, InjectedToolArg()] = None,
) -> str:
    """Registra evento de auditoria LGPD.

    Chame SEMPRE que coletar/acessar/compartilhar dado sensível do
    paciente (CPF, data nasc, prontuário, agendamento).

    Args:
        event_type: Tipo do evento. Valores aceitos:
            - "cpf_collected"
            - "dob_collected"
            - "appointment_lookup"
            - "data_shared_with_human"
            - "modality_qualified"
            - "document_request_created"
            - "sensitive_data_exposed"
            - "patient_record_accessed"
            (identity_verified / identity_verification_failed são auto-logados
            pela tool verify_patient_identity, não use aqui)
        details: dict com contexto (motivo, dept, etc) — opcional

    Returns:
        JSON: {"logged": true, "event_id": int} OU
        {"logged": false, "reason": str}
    """
    ctx = _extract_context(runtime)
    empresa_id = ctx["empresa_id"]
    atendimento_id = ctx["atendimento_id"]
    cliente_id = ctx["cliente_id"]
    agent_slug = ctx["agent_slug"]

    if not empresa_id:
        return json.dumps(
            {"logged": False, "reason": "empresa_id_ausente"}, ensure_ascii=False
        )

    if event_type not in EVENT_TYPES:
        return json.dumps(
            {
                "logged": False,
                "reason": f"event_type_invalido. Use: {sorted(EVENT_TYPES)}",
            },
            ensure_ascii=False,
        )

    # Normaliza details: aceita dict OU string JSON do LLM
    payload: dict[str, Any] = {}
    if isinstance(details, dict):
        payload = details
    elif isinstance(details, str) and details.strip():
        try:
            parsed = json.loads(details)
            if isinstance(parsed, dict):
                payload = parsed
            else:
                payload = {"raw": details}
        except json.JSONDecodeError:
            payload = {"raw": details}

    pool = await get_pool()
    try:
        event_id = await log_event(
            pool,
            empresa_id=empresa_id,
            event_type=event_type,
            details=payload,
            atendimento_id=atendimento_id,
            cliente_id=cliente_id,
            agent_slug=agent_slug,
        )
    except LGPDEventTypeError as exc:
        return json.dumps(
            {"logged": False, "reason": str(exc)}, ensure_ascii=False
        )
    except Exception as exc:
        logger.exception("log_lgpd_event_failed", error=str(exc))
        return json.dumps(
            {"logged": False, "reason": "erro_interno"}, ensure_ascii=False
        )

    return json.dumps({"logged": True, "event_id": event_id}, ensure_ascii=False)
