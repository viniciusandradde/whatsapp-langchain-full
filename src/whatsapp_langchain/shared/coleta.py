"""Wizard de coleta multi-pergunta por menu_item (Sprint coleta).

Quando cliente escolhe um `menu_item` que tem `coleta_perguntas` não-vazio,
o worker dispara um wizard sequencial:

1. Pergunta 1 (com templates {{cliente.X}}, {{empresa.X}}, {{coleta.X}})
2. Cliente responde — `validate_input` (reuso de workflows/validators.py)
3. Se válido, avança pra próxima. Se inválido, repete com `retry_message`.
4. Quando última pergunta termina, grava `atendimento.coleta_resumo`
   e despacha `acao_tipo` original do item (chamar_agente/transferir/etc).

State runtime em `atendimento.coleta_estado` (JSONB):
    {
      "item_id": int,
      "idx": int,                    # próxima pergunta a perguntar (0-based)
      "respostas": {save_as: valor}, # respostas válidas já dadas
      "perguntas": [...],            # snapshot do array no momento do INSERT
      "started_at": iso
    }

Esse arquivo NÃO usa LangGraph — é state machine simples no DB. Não
conflita com workflow_chatbot.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from whatsapp_langchain.shared.variavel import render_template
from whatsapp_langchain.workflows.validators import validate_input

# Reservadas (não usar como save_as)
_RESERVED_PREFIXES = ("cliente_", "empresa_", "data_", "var_")
_RESERVED_KEYS = {"cliente", "empresa", "data", "var"}


class ColetaPergunta(BaseModel):
    """Uma pergunta do wizard de coleta.

    `validate_with` aceita os mesmos formatos do workflows.validators:
    "cpf", "cnpj", "data_br", "telefone_br", "email", "uf", "cep",
    "min_len:N", "max_len:N", "regex:..." ou None (sem validação).
    """

    label: str = Field(..., min_length=1, max_length=2000)
    save_as: str = Field(..., min_length=1, max_length=64)
    validate_with: str | None = None
    retry_message: str | None = Field(default=None, max_length=2000)
    obrigatorio: bool = True

    @field_validator("save_as")
    @classmethod
    def _save_as_slug(cls, v: str) -> str:
        v = v.strip()
        if not v.replace("_", "").isalnum() or not v[0].isalpha():
            raise ValueError(
                "save_as deve ser slug [a-z][a-z0-9_]* (começa com letra)"
            )
        if v in _RESERVED_KEYS or any(
            v.startswith(p) for p in _RESERVED_PREFIXES
        ):
            raise ValueError(
                f"save_as '{v}' é reservado "
                f"(não use prefixos cliente_/empresa_/data_/var_)"
            )
        return v.lower()

    @field_validator("validate_with")
    @classmethod
    def _validate_rule_known(cls, v: str | None) -> str | None:
        if not v:
            return v
        # Smoke test do parser — dispara erro se a rule for inválida
        ok, _err = validate_input("dummy", v)
        # `ok=False` aqui é esperado (dummy não passa por cpf etc.), o que
        # importa é não dar exceção interna. Se a rule for desconhecida,
        # validate_input retorna ok=True silenciosamente, então testamos
        # padrões conhecidos manualmente.
        known = {
            "cpf", "cnpj", "cep", "uf", "data_br", "telefone_br", "email",
        }
        prefix = v.split(":", 1)[0]
        if prefix not in known and prefix not in ("min_len", "max_len", "regex"):
            raise ValueError(
                f"validate_with '{v}' desconhecido. Use cpf/cnpj/cep/uf/"
                f"data_br/telefone_br/email/min_len:N/max_len:N/regex:..."
            )
        return v


def normalize_perguntas(raw: list[dict] | None) -> list[dict]:
    """Aceita lista de dicts crus, valida via Pydantic, retorna dicts limpos."""
    if not raw:
        return []
    out: list[dict] = []
    for p in raw:
        validated = ColetaPergunta(**p)
        out.append(validated.model_dump(exclude_none=False))
    return out


def build_coleta_render_ctx(
    base_ctx: dict[str, Any], respostas: dict[str, Any]
) -> dict[str, str]:
    """Adiciona namespace `coleta.*` ao contexto pra render_template.

    O ctx do render_template é flat: {"namespace.key": "value"}. Aqui
    "achatamos" respostas como `coleta.<save_as> = valor`.
    """
    ctx = dict(base_ctx)
    for save_as, valor in (respostas or {}).items():
        ctx[f"coleta.{save_as}"] = str(valor) if valor is not None else ""
    return ctx


def render_pergunta_label(label: str, render_ctx: dict[str, Any]) -> str:
    """Renderiza `{{cliente.nome}}`, `{{coleta.cpf}}`, etc no label."""
    return render_template(label, render_ctx) or label


def make_estado_inicial(item_id: int, perguntas: list[dict]) -> dict:
    """Cria payload inicial pra coleta_estado quando wizard começa."""
    return {
        "item_id": item_id,
        "idx": 0,
        "respostas": {},
        "perguntas": perguntas,  # snapshot pra não quebrar se admin editar
        "started_at": datetime.now(UTC).isoformat(),
    }


def is_em_andamento(estado: dict | None) -> bool:
    """Verifica se há um wizard ativo no atendimento."""
    if not estado:
        return False
    perguntas = estado.get("perguntas") or []
    idx = estado.get("idx", 0)
    return bool(perguntas) and idx < len(perguntas)


def pergunta_atual(estado: dict) -> dict | None:
    """Retorna a pergunta atual (no idx), ou None se já passou da última."""
    perguntas = estado.get("perguntas") or []
    idx = estado.get("idx", 0)
    if idx >= len(perguntas):
        return None
    return perguntas[idx]


def avancar_resposta(estado: dict, save_as: str, valor: str) -> dict:
    """Retorna NOVO estado com a resposta salva e idx incrementado.

    Não muta o input. Usado pelo worker antes de gravar no DB.
    """
    novo = dict(estado)
    respostas = dict(novo.get("respostas") or {})
    respostas[save_as] = valor
    novo["respostas"] = respostas
    novo["idx"] = int(novo.get("idx", 0)) + 1
    return novo


def make_resumo_final(
    estado: dict, item_label: str | None = None
) -> dict:
    """Constrói o payload pra atendimento.coleta_resumo quando wizard termina."""
    perguntas = estado.get("perguntas") or []
    respostas = estado.get("respostas") or {}
    # Monta dict {save_as: {label, valor}} pra UI exibir contexto
    detalhado: dict[str, dict[str, str]] = {}
    for p in perguntas:
        save_as = p.get("save_as")
        if not save_as:
            continue
        if save_as in respostas:
            detalhado[save_as] = {
                "label": p.get("label", save_as),
                "valor": respostas[save_as],
            }
    return {
        "item_id": estado.get("item_id"),
        "item_label": item_label,
        "respostas": detalhado,
        "completed_at": datetime.now(UTC).isoformat(),
    }


def validar_e_processar(
    estado: dict, texto: str
) -> tuple[bool, str | None, dict]:
    """Valida o texto contra a pergunta atual.

    Returns:
        (ok, erro, novo_estado):
        - ok=True: resposta válida, novo_estado tem idx avançado
        - ok=False: resposta inválida, `erro` é a mensagem retry, novo_estado
          é o estado original (não muda)
    """
    p = pergunta_atual(estado)
    if p is None:
        # Não deveria acontecer — wizard já terminou
        return True, None, estado
    rule = p.get("validate_with")
    obrigatorio = p.get("obrigatorio", True)
    texto = (texto or "").strip()
    if not texto:
        if obrigatorio:
            return False, "Por favor, responda essa pergunta.", estado
        # Não-obrigatório aceita vazio
        novo = avancar_resposta(estado, p["save_as"], "")
        return True, None, novo
    ok, default_err = validate_input(texto, rule)
    if not ok:
        retry = p.get("retry_message") or default_err or "Resposta inválida."
        return False, retry, estado
    novo = avancar_resposta(estado, p["save_as"], texto)
    return True, None, novo
