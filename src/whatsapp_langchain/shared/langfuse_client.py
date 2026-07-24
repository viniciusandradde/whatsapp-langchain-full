"""Cliente Langfuse — singleton + helpers best-effort.

Encapsula:
- Singleton do `Langfuse` (lazy, criado no 1º acesso).
- `get_callback_handler()` retorna `CallbackHandler` LangChain pronto pra
  plugar em `invoke_config["callbacks"]`, ou None quando feature desligada.
- `get_system_prompt(name, fallback)` resolve prompt via Prompt Management
  (cache TTL 60s no SDK) e cai no fallback file-based quando off/inexistente.
- `post_score(trace_id, name, value, comment)` anexa score posthoc — usado
  pelo módulo NPS pra ligar nota do CSAT à trace correspondente.

Contrato: NUNCA pode levantar exceção pro chamador. Se Langfuse cai, o
worker tem que continuar respondendo cliente. Toda call externa em try/except.
"""

from __future__ import annotations

from typing import Any

import structlog

from whatsapp_langchain.shared.config import settings

logger = structlog.get_logger()

_CLIENT: Any | None = None
_CLIENT_INIT_FAILED = False


def get_client() -> Any | None:
    """Retorna singleton do client Langfuse, ou None quando desabilitado.

    Lazy: só importa `langfuse` no 1º acesso. Se construção falhar (host
    inalcançável, key inválida), seta flag pra não retentar a cada chamada.
    """
    global _CLIENT, _CLIENT_INIT_FAILED

    if not settings.langfuse_enabled:
        return None
    if _CLIENT_INIT_FAILED:
        return None
    if _CLIENT is not None:
        return _CLIENT

    try:
        from langfuse import Langfuse

        pub = settings.langfuse_public_key
        sec = settings.langfuse_secret_key
        assert pub is not None and sec is not None  # langfuse_enabled garante

        _CLIENT = Langfuse(
            public_key=pub.get_secret_value(),
            secret_key=sec.get_secret_value(),
            host=settings.langfuse_host,
            environment=settings.langfuse_environment,
        )
        logger.info(
            "langfuse_client_initialized",
            host=settings.langfuse_host,
            environment=settings.langfuse_environment,
        )
        return _CLIENT
    except Exception as exc:
        _CLIENT_INIT_FAILED = True
        logger.warning(
            "langfuse_client_init_failed",
            error=str(exc),
            host=settings.langfuse_host,
        )
        return None


def create_trace_id(seed: str) -> str | None:
    """Gera trace_id determinístico (mesmo seed → mesmo id).

    Útil pra garantir que o `langfuse_trace_id` gravado em `ia_execucao`
    bate com o trace real emitido pelo CallbackHandler.
    """
    client = get_client()
    if client is None:
        return None
    try:
        from langfuse import Langfuse

        return Langfuse.create_trace_id(seed=seed)
    except Exception as exc:
        logger.warning("langfuse_create_trace_id_failed", error=str(exc), seed=seed)
        return None


def get_callback_handler(
    trace_id: str | None,
    metadata: dict[str, Any] | None = None,
) -> Any | None:
    """Retorna CallbackHandler ligado a um trace_id pré-definido.

    Quando `trace_id` é None ou Langfuse off, retorna None — o caller
    simplesmente não appenda em `invoke_config["callbacks"]`.

    Args:
        trace_id: ID determinístico do trace (use `create_trace_id(seed)`).
        metadata: Não usado pelo CallbackHandler em si — anexar metadata via
                  RunnableConfig{"metadata": {...}} no chamador.
    """
    client = get_client()
    if client is None or trace_id is None:
        return None
    try:
        from langfuse.langchain import CallbackHandler

        # CallbackHandler usa o singleton global do Langfuse (criado por
        # get_client). Só precisa do trace_context — o cliente é descoberto
        # via singleton interno do SDK.
        return CallbackHandler(
            trace_context={"trace_id": trace_id},
        )
    except Exception as exc:
        logger.warning("langfuse_callback_handler_failed", error=str(exc))
        return None


def get_system_prompt(name: str, fallback: str) -> tuple[str, dict[str, Any] | None]:
    """Resolve SYSTEM_PROMPT via Langfuse Prompt Management.

    Retorna `(text, metadata)` onde:
      - text = conteúdo final do prompt (do Langfuse ou do fallback).
      - metadata = dict com `prompt_name` + `prompt_version` quando veio do
        Langfuse; None quando caiu no fallback. Anexar à `RunnableConfig`
        do invoke pra trace marcar versão usada.

    Args:
        name: Nome do prompt no Langfuse (convenção: usar template_id, ex.
              "atendimento_router").
        fallback: Texto do prompt embutido no código (constante Python).

    Comportamento:
        - Langfuse off → retorna (fallback, None) imediato.
        - Langfuse on + prompt existe → retorna (prompt.prompt, metadata).
        - Langfuse on + prompt não existe / erro → retorna (fallback, None).
    """
    client = get_client()
    if client is None:
        return fallback, None
    try:
        prompt = client.get_prompt(
            name,
            type="text",
            label=settings.langfuse_prompt_label,
            fallback=fallback,
            cache_ttl_seconds=60,
        )
    except Exception as exc:
        logger.warning(
            "langfuse_get_prompt_failed",
            name=name,
            error=str(exc),
        )
        return fallback, None

    # `prompt.prompt` é o texto bruto (sem .compile() — não usamos
    # mustache {{var}} aqui porque render_template do projeto já cobre
    # `{{empresa.*}}` etc. e roda DEPOIS desta chamada no loader).
    text = getattr(prompt, "prompt", None) or fallback
    version = getattr(prompt, "version", None)
    return text, {"prompt_name": name, "prompt_version": version}


def post_score(
    trace_id: str | None,
    name: str,
    value: float | str | bool,
    comment: str | None = None,
    data_type: str = "NUMERIC",
) -> None:
    """Anexa score a uma trace (best-effort, não levanta).

    Usado pelo módulo NPS pra ligar nota do CSAT → trace do atendimento.
    Quando `trace_id` é None ou Langfuse off, não-op.
    """
    if trace_id is None:
        return
    client = get_client()
    if client is None:
        return
    try:
        client.create_score(
            name=name,
            value=value,
            trace_id=trace_id,
            data_type=data_type,
            comment=comment,
        )
    except Exception as exc:
        logger.warning(
            "langfuse_post_score_failed",
            trace_id=trace_id,
            name=name,
            error=str(exc),
        )


def list_scores(
    name: str | None = None,
    from_timestamp: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Lista scores via REST (`GET /api/public/scores`, basic-auth pk:sk).

    Usado pra auto-dataset: pega os scores (ex.: NPS 0-10) de um período pra
    descobrir QUAIS traces foram bem avaliadas — o conteúdo do diálogo vem do
    banco local (message_queue.langfuse_trace_id). Best-effort: `[]` se off.

    Cada item: {traceId, name, value, comment, timestamp, ...}. Pagina até
    esgotar (o público de scores costuma ser pequeno; cap defensivo em 20 pgs).
    """
    if not settings.langfuse_enabled:
        return []
    pub = settings.langfuse_public_key
    sec = settings.langfuse_secret_key
    if pub is None or sec is None:
        return []
    try:
        import httpx

        host = settings.langfuse_host.rstrip("/")
        auth = (pub.get_secret_value(), sec.get_secret_value())
        out: list[dict[str, Any]] = []
        page = 1
        with httpx.Client(timeout=15.0) as client:
            while page <= 20:
                params: dict[str, str] = {
                    "limit": str(max(1, min(limit, 100))),
                    "page": str(page),
                }
                if name:
                    params["name"] = name
                if from_timestamp:
                    params["fromTimestamp"] = from_timestamp
                resp = client.get(
                    f"{host}/api/public/scores",
                    params=params,
                    auth=auth,
                )
                resp.raise_for_status()
                data = resp.json().get("data", [])
                if not isinstance(data, list) or not data:
                    break
                out.extend(data)
                if len(data) < int(params["limit"]):
                    break
                page += 1
        return out
    except Exception as exc:
        logger.warning("langfuse_list_scores_failed", error=str(exc))
        return []


def trace_url(trace_id: str) -> str:
    """Short-link pra UI do trace (redireciona pro projeto certo, sem precisar
    do project_id)."""
    host = settings.langfuse_host.rstrip("/")
    return f"{host}/trace/{trace_id}"


def list_traces(limit: int = 20, session_id: str | None = None) -> list[dict[str, Any]]:
    """Lista traces via REST público (`GET /api/public/traces`) com basic-auth
    pk:sk — estável entre versões do SDK. Best-effort: `[]` quando off/erro.

    `session_id` filtra por conversa (worker seta `session_id = thread_id`).
    """
    if not settings.langfuse_enabled:
        return []
    pub = settings.langfuse_public_key
    sec = settings.langfuse_secret_key
    if pub is None or sec is None:
        return []
    try:
        import httpx

        params: dict[str, str] = {"limit": str(max(1, min(limit, 100)))}
        if session_id:
            params["sessionId"] = session_id
        host = settings.langfuse_host.rstrip("/")
        resp = httpx.get(
            f"{host}/api/public/traces",
            params=params,
            auth=(pub.get_secret_value(), sec.get_secret_value()),
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        return data if isinstance(data, list) else []
    except Exception as exc:
        logger.warning("langfuse_list_traces_failed", error=str(exc))
        return []


def flush() -> None:
    """Força flush do batch de spans/scores. Usar em testes ou shutdown."""
    client = get_client()
    if client is None:
        return
    try:
        client.flush()
    except Exception as exc:
        logger.warning("langfuse_flush_failed", error=str(exc))
