"""Sprint D hardening — invariante de RBAC em endpoints mutadores.

Falha se algum endpoint POST/PUT/PATCH/DELETE em `/api/*` não tiver
`Depends(require_permission(...))` OU pertencer à allowlist de exceções
(`require_service_token`-only, webhooks, auth, public).

Por que esse test?
- RBAC é gerenciado por **convenção**, não por enforcement arquitetural.
- Refatorar uma rota e esquecer o `Depends` quebra silenciosamente o
  isolamento — endpoint passa a aceitar qualquer user válido da empresa.
- Test roda em CI, falha PR antes de merge.

Estratégia: percorre todas as rotas registradas no `app` FastAPI, extrai
metadata via `dependant.dependencies` recursivamente, procura uma dep que
seja `require_permission` (factory retorna closure — checa nome interno).

Allowlist documentada:
- Webhooks: `/webhook/*` validam HMAC ao invés de user perm
- Auth interno: rotas Better Auth são públicas (registro/login)
- Admin: `/api/admin/*` usa `verify_service_token` (token compartilhado)
- Health: `/api/health/*` precisa ser público pro Dokploy healthcheck
- Bootstrap: criar 1ª empresa precisa rodar sem RBAC
- Hooks/Webhooks customizados: validam signature própria
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.routing import APIRoute

# Rotas que LEGITIMAMENTE não precisam de `require_permission`
# (validação ocorre via outro mecanismo: HMAC, service token, ou são públicas).
# Cada item: (method, path_prefix) — match por startswith.
ALLOWLIST: list[tuple[str, str]] = [
    # Health / metrics — precisa ser público pro Dokploy/Prometheus scrape
    ("GET", "/health"),
    ("GET", "/api/health"),
    ("GET", "/metrics"),
    # Webhooks — validam signature do provider
    ("POST", "/webhook/"),
    ("GET", "/webhook/"),
    # Better Auth gerencia próprio auth
    ("POST", "/api/auth/"),
    ("GET", "/api/auth/"),
    # Bootstrap empresa — primeira empresa não tem RBAC ainda
    ("POST", "/api/empresas"),
    # Billing (sprint B) — usa is_admin_of() em vez de require_permission
    # (billing é mais granular que perm "empresa.update": tem que ser
    # admin EXPLÍCITO da empresa, superadmin não basta — auditoria fiscal)
    ("POST", "/api/billing/"),
    ("PUT", "/api/billing/"),
    ("DELETE", "/api/billing/"),
    # Webhook Asaas (validação via header asaas-access-token, não user)
    ("POST", "/webhook/asaas"),
    # OAuth callbacks públicos (state CSRF + token Meta valida no callback)
    ("GET", "/api/conexoes/waba/oauth/callback"),
    # Test runner interno só pra dev/CI
    ("POST", "/api/test-runner"),
    ("GET", "/api/test-runner"),
]

# Snapshot de tech-debt — endpoints LEGADOS sem require_permission detectados
# na implementação do test (Sprint D, 2026-05-22). Não bloqueia CI hoje, mas
# o test detecta REGRESSÕES (qualquer endpoint novo fora dessa lista falha).
#
# Plano: ir tirando da lista conforme equipe adiciona `Depends(require_permission(...))`
# nos handlers correspondentes. Quando lista zerar, esse mecanismo vira o
# enforcement duro (`offenders` puro).
#
# NÃO ADICIONE endpoints novos aqui — adicione `require_permission` no
# handler. Esta lista é só pra dívida pre-existente.
TECH_DEBT_KNOWN_OFFENDERS: set[str] = {
    "DELETE /api/agents/{agent_id}/agente-ia-config",
    "DELETE /api/base-conhecimento/{doc_id}",
    "DELETE /api/clientes/{cliente_id}/tags/{tag}",
    "DELETE /api/conexoes/{conexao_id}",
    "DELETE /api/conexoes/{conexao_id}/templates/{template_id}",
    "DELETE /api/departamentos/{dep_id}",
    "DELETE /api/departamentos/{dep_id}/users/{target_user_id}",
    "DELETE /api/empresas/{empresa_id}/membros/{member_user_id}",
    "DELETE /api/feriados/{feriado_id}",
    "DELETE /api/google-calendar/config",
    "DELETE /api/hooks/{hook_id}",
    "DELETE /api/horarios/{horario_id}",
    "DELETE /api/modelos/{modelo_id}",
    "DELETE /api/pastas/{pasta_id}",
    "DELETE /api/variaveis/{var_id}",
    "PATCH /api/conexoes/{conexao_id}",
    "POST /api/admin/hitl/{acao_id}/approve",
    "POST /api/admin/hitl/{acao_id}/reject",
    "POST /api/admin/rag/dataset/import",
    "POST /api/admin/rag/fewshot/backfill",
    "POST /api/admin/rag/langsmith/sync",
    "POST /api/admin/rag/learner/run",
    "POST /api/admin/rag/preview",
    "POST /api/admin/rag/sandbox/clean",
    "POST /api/admin/rag/suggestions/{suggestion_id}/approve",
    "POST /api/admin/rag/suggestions/{suggestion_id}/reject",
    "POST /api/admin/tests/run",
    "POST /api/admin/tests/runs/{run_id}/kill",
    "POST /api/admin/workflows/{workflow_id}/toggle-active",
    "POST /api/atendentes/me/heartbeat",
    "POST /api/atendentes/me/status",
    "POST /api/atendimentos/{atendimento_id}/aba",
    "POST /api/atendimentos/{atendimento_id}/claim",
    "POST /api/atendimentos/{atendimento_id}/close",
    "POST /api/atendimentos/{atendimento_id}/marcar-lido",
    "POST /api/atendimentos/{atendimento_id}/reset-thread",
    "POST /api/atendimentos/{atendimento_id}/responder",
    "POST /api/atendimentos/{atendimento_id}/transfer",
    "POST /api/base-conhecimento",
    "POST /api/base-conhecimento/buscar",
    "POST /api/base-conhecimento/upload",
    "POST /api/campanhas",
    "POST /api/campanhas/{camp_id}/abort",
    "POST /api/campanhas/{camp_id}/dispatch",
    "POST /api/clientes/{cliente_id}/anotacoes",
    "POST /api/clientes/{cliente_id}/tags",
    "POST /api/conexoes",
    "POST /api/conexoes/evolution/provision",
    "POST /api/conexoes/test-evolution",
    "POST /api/conexoes/waba/finalize",
    "POST /api/conexoes/waba/oauth/start",
    "POST /api/conexoes/{conexao_id}/disconnect",
    "POST /api/conexoes/{conexao_id}/templates",
    "POST /api/conexoes/{conexao_id}/templates/import",
    "POST /api/conexoes/{conexao_id}/templates/{template_id}/sync",
    "POST /api/conexoes/{conexao_id}/templates/{template_id}/test-send",
    "POST /api/conexoes/{conexao_id}/test",
    "POST /api/departamentos",
    "POST /api/departamentos/{dep_id}/users",
    "POST /api/feriados",
    "POST /api/hooks",
    "POST /api/hooks/dead-letter/{dlq_id}/archive",
    "POST /api/hooks/dead-letter/{dlq_id}/retry",
    "POST /api/horarios",
    "POST /api/modelos",
    "POST /api/pastas",
    "POST /api/pastas/{pasta_id}/documentos/{doc_id}",
    "POST /api/variaveis",
    "PUT /api/admin/workflows/{workflow_id}",
    "PUT /api/agents/{agent_id}/agente-ia-config",
    "PUT /api/agents/{agent_id}/config",
    "PUT /api/base-conhecimento/{doc_id}",
    "PUT /api/calendar/regras",
    "PUT /api/clientes/{cliente_id}",
    "PUT /api/departamentos/{dep_id}",
    "PUT /api/empresas/{empresa_id}",
    "PUT /api/empresas/{empresa_id}/csat",
    "PUT /api/empresas/{empresa_id}/membros/{member_user_id}",
    "PUT /api/empresas/{empresa_id}/membros/{member_user_id}/departamentos",
    "PUT /api/empresas/{empresa_id}/membros/{member_user_id}/perfis",
    "PUT /api/empresas/{empresa_id}/membros/{member_user_id}/status",
    "PUT /api/google-calendar/config",
    "PUT /api/hooks/{hook_id}",
    "PUT /api/modelos/{modelo_id}",
    "PUT /api/pastas/{pasta_id}",
    "PUT /api/variaveis/{var_id}",
}


def _dep_name_recursive(dep: Any, max_depth: int = 5) -> list[str]:
    """Coleta nomes de todas as deps + subdeps de um endpoint."""
    if max_depth <= 0:
        return []
    names: list[str] = []
    call = getattr(dep, "call", None)
    if call is not None:
        names.append(getattr(call, "__qualname__", "") or getattr(call, "__name__", ""))
        # `require_permission` é factory que retorna closure — nome chega
        # como "require_permission.<locals>._dep" ou similar
        closure = getattr(call, "__closure__", None)
        if closure:
            for cell in closure:
                try:
                    val = cell.cell_contents
                    if isinstance(val, str):
                        names.append(f"perm:{val}")
                except ValueError:
                    pass
    sub_deps = getattr(dep, "dependencies", None) or []
    for sub in sub_deps:
        names.extend(_dep_name_recursive(sub, max_depth - 1))
    return names


def _is_allowlisted(method: str, path: str) -> bool:
    for allowed_method, prefix in ALLOWLIST:
        if method == allowed_method and path.startswith(prefix):
            return True
    return False


def _has_permission_dep(route: APIRoute) -> bool:
    names = _dep_name_recursive(route.dependant)
    return any("require_permission" in n for n in names)


@pytest.fixture(scope="module")
def app_routes() -> list[APIRoute]:
    from whatsapp_langchain.server.main import app

    return [r for r in app.routes if isinstance(r, APIRoute)]


def test_no_new_mutator_endpoints_without_permission_dep(
    app_routes: list[APIRoute],
) -> None:
    """Detecta REGRESSÕES — endpoint mutador novo sem require_permission.

    Endpoints legados sem perm estão em TECH_DEBT_KNOWN_OFFENDERS (snapshot
    de 2026-05-22). Esse test falha se aparecer endpoint novo fora do
    snapshot ou se um offender for adicionado de novo após remoção.
    """
    found_offenders: set[str] = set()
    mutator_methods = {"POST", "PUT", "PATCH", "DELETE"}

    for route in app_routes:
        path = route.path
        for method in route.methods or set():
            if method not in mutator_methods:
                continue
            if not path.startswith("/api/"):
                continue
            if _is_allowlisted(method, path):
                continue
            if not _has_permission_dep(route):
                found_offenders.add(f"{method} {path}")

    new_offenders = found_offenders - TECH_DEBT_KNOWN_OFFENDERS
    fixed_offenders = TECH_DEBT_KNOWN_OFFENDERS - found_offenders

    msgs: list[str] = []
    if new_offenders:
        msgs.append(
            "❌ NOVOS endpoints sem require_permission (regressão):\n  "
            + "\n  ".join(sorted(new_offenders))
            + "\n\nFix: adicione Depends(require_permission('codigo.write')) "
            "no handler. NÃO ADICIONE à TECH_DEBT_KNOWN_OFFENDERS."
        )
    if fixed_offenders:
        msgs.append(
            "✅ Endpoints removidos do snapshot (fix detectado). "
            "Remova da TECH_DEBT_KNOWN_OFFENDERS:\n  "
            + "\n  ".join(sorted(fixed_offenders))
        )
    assert not msgs, "\n\n".join(msgs)


def test_tech_debt_count_only_decreases() -> None:
    """Sanity check: contagem documentada de tech-debt RBAC.

    Sprint D snapshot: 86 endpoints. À medida que perm é adicionado,
    bumps esse número PRA BAIXO. Se subir, é regressão.
    """
    assert len(TECH_DEBT_KNOWN_OFFENDERS) <= 86, (
        f"TECH_DEBT_KNOWN_OFFENDERS cresceu pra "
        f"{len(TECH_DEBT_KNOWN_OFFENDERS)} (esperado ≤ 86). "
        "Adicione perm em vez de aumentar a dívida."
    )
