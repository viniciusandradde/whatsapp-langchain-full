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
    # Disparador in-browser (extensão) — autenticado por API key da empresa
    # (require_scope("dispatch")), não RBAC de user. Mesmo padrão de webhook.
    ("POST", "/api/disparador/ext/"),
    # Resumo diário (mig 135) — valida is_admin_of da empresa-ALVO do path
    # (padrão do router empresa_admin: role-guard explícito por endpoint;
    # require_permission checaria a empresa ATIVA do header, que pode ser
    # outra — mesmo racional do CSAT).
    ("PUT", "/api/empresas/{empresa_id}/resumo-diario"),
    # Envio manual do resumo (mig 162) — mesmo router, mesmo `is_admin_of` da
    # empresa-ALVO. Prefixo cobre `/resumo-diario/testar`.
    ("POST", "/api/empresas/{empresa_id}/resumo-diario"),
    # Módulo de Uso (mig 165) — relatório mensal que a VSA envia aos clientes.
    # É ferramenta de PLATAFORMA: o guarda é `is_superadmin`, checado em toda
    # rota do arquivo. `require_permission` seria errado aqui pelo mesmo motivo
    # do `/resumo-diario` acima — ele resolve a permissão contra a empresa
    # ATIVA do header, e aqui a empresa-alvo é a do path, de outro tenant. Não
    # existe permissão de superadmin no catálogo, e criar uma seria pior:
    # `shared/perfil.py` concede o catálogo inteiro ao superadmin, então
    # qualquer Admin de tenant também a teria.
    ("POST", "/api/relatorios/uso/"),
    ("PUT", "/api/relatorios/uso/"),
    # Dispensar o onboarding (mig 160) — valida `get_empresa_membership` da
    # empresa-ALVO do path, ou superadmin. NÃO é endpoint aberto.
    #
    # `require_permission` seria errado aqui por dois motivos: checaria a
    # empresa ATIVA do header, que pode ser outra (mesmo racional do
    # `/resumo-diario` acima), e exigiria uma permissão específica — o que
    # desfaz a decisão deliberada de qualquer MEMBRO poder dispensar. Exigir
    # admin faria o botão "Pular" falhar calado justo pro operador, que é quem
    # mais topa com o wizard. A escrita mexe só em qual tela a raiz "/" abre.
    #
    # O isolamento é coberto por
    # `test_onboarding_endpoints.py::TestE2EIsolamento::test_estranho_nao_dispensa`
    # (membro de outra empresa recebe 403) — a allowlist tira o endpoint desta
    # invariante, não da cobertura.
    ("PUT", "/api/empresas/{empresa_id}/onboarding-dispensado"),
    # Captura da extensão Chrome — autenticada por API key da empresa
    # (require_scope("capture")), não RBAC de user. Mesmo padrão do ext/.
    ("POST", "/api/captura/"),
    # Config global Asaas — superadmin only via _require_superadmin (é
    # plataforma, não empresa: require_permission não se aplica, mesmo
    # racional do bloco /api/billing acima). Cobre PUT config + POST testar.
    ("PUT", "/api/admin/integracoes/asaas"),
    ("POST", "/api/admin/integracoes/asaas"),
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
    "DELETE /api/conexoes/{conexao_id}",
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
    "POST /api/atendimentos/{atendimento_id}/claim",
    "POST /api/atendimentos/{atendimento_id}/close",
    "POST /api/atendimentos/{atendimento_id}/reset-thread",
    "POST /api/atendimentos/{atendimento_id}/responder",
    "POST /api/atendimentos/{atendimento_id}/transfer",
    "POST /api/base-conhecimento",
    "POST /api/base-conhecimento/buscar",
    "POST /api/base-conhecimento/upload",
    "POST /api/campanhas",
    "POST /api/campanhas/{camp_id}/abort",
    "POST /api/campanhas/{camp_id}/dispatch",
    "POST /api/conexoes",
    "POST /api/conexoes/evolution/provision",
    "POST /api/conexoes/test-evolution",
    "POST /api/conexoes/waba/finalize",
    "POST /api/conexoes/waba/oauth/start",
    "POST /api/conexoes/{conexao_id}/disconnect",
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


#: Endpoints cujo efeito é limitado a QUEM CHAMA (ou à conversa que a pessoa
#: já enxerga), e que por isso não levam permissão do catálogo.
#:
#: A distinção importa: `require_permission` faz match EXATO do código
#: (`dependencies_rbac.py`), então exigir `atendimento.read` aqui trancaria
#: justamente o operador que só tem `atendimento.read.own` — ele veria a
#: conversa e não conseguiria marcá-la como não lida. O gate real destes é o
#: escopo de empresa (`get_empresa_context` + carga do atendimento).
#:
#: NÃO é lugar pra endpoint que escreve dado de outra pessoa.
SELF_SCOPED_SEM_PERMISSAO: set[str] = {
    # Read receipt por usuário: mexe só no badge de não-lidas de quem chama.
    "POST /api/atendimentos/{atendimento_id}/marcar-lido",
    "POST /api/atendimentos/{atendimento_id}/marcar-nao-lido",
    # Transcrição sob demanda: "quem vê a conversa pode transcrever" (mig 169).
    "POST /api/atendimentos/{atendimento_id}/mensagens/{mensagem_id}/transcrever",
    # Preferência do próprio usuário (mig 171) — falhar aqui travaria o painel.
    "POST /api/usuarios/me/tour",
}

#: Endpoints com gate `is_superadmin` chamado DENTRO do handler, não como
#: `Depends`. São recursos de PLATAFORMA (catálogo global, relatório de
#: produção), onde superadmin é mais restritivo que qualquer permissão de
#: empresa — a decisão está documentada no topo de cada módulo.
#:
#: Ficam aqui porque este teste só enxerga a árvore de dependências; o gate
#: existe, o inspetor é que não alcança. Se algum dia virar `Depends`, some
#: daqui naturalmente.
GATE_SUPERADMIN_NO_HANDLER: set[str] = {
    "POST /api/openrouter/sync",
    "POST /api/openrouter/modelos/{author}/{slug}/promover",
    "POST /api/relatorios/producao/gerar",
    "PUT /api/relatorios/producao/config",
}


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

    # Gate deliberado por outro mecanismo ≠ gate esquecido. As duas listas
    # abaixo são justificadas caso a caso na declaração de cada uma.
    gated_de_outro_jeito = SELF_SCOPED_SEM_PERMISSAO | GATE_SUPERADMIN_NO_HANDLER
    new_offenders = found_offenders - TECH_DEBT_KNOWN_OFFENDERS - gated_de_outro_jeito
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
