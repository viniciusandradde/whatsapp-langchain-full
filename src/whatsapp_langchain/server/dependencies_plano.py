"""Sprint Q.3 — dependencies FastAPI pra enforce quotas + features de plano.

Aplica em endpoints POST que criam recursos contáveis. Bloqueia com
HTTP 402 (Payment Required) + body explicativo com upgrade sugerido.

Uso:
    @router.post("/conexoes")
    async def criar_conexao(
        body: ConexaoInput,
        empresa_id: int = Depends(get_empresa_context),
        _quota: None = Depends(require_plano_limit("conexoes")),
        _: None = Depends(require_permission("conexao.write")),
    ):
        ...

Pra features (calendar, mcp, white_label):
    @router.put("/empresas/{empresa_id}/calendar/config")
    async def setar_calendar(
        ...
        _feature: None = Depends(require_plano_feature("calendar")),
    ):
        ...
"""

from __future__ import annotations

import structlog
from fastapi import Depends, HTTPException

from whatsapp_langchain.server.dependencies import get_empresa_context
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.plano_limits import (
    count_recurso,
    get_plano_info,
)

logger = structlog.get_logger()

# HTTP 402 Payment Required — usado tanto pra limit quanto pra feature.
# Mensagens user-facing em pt-BR pra UI mostrar direto.
_STATUS_QUOTA_EXCEEDED = 402

# Recursos contáveis aceitos por `require_plano_limit`/`assert_plano_limit`
# — mesmo nome usado por `count_recurso()` e `PlanoInfo.limite_de()`.
RECURSOS_CONTAVEIS: tuple[str, ...] = (
    "conexoes",
    "usuarios",
    "atendimentos_mes",
    "documentos_kb",
    "agentes",
)


# Como o recurso aparece na mensagem do 402 (a UI mostra `message` direto).
_ROTULO_RECURSO = {
    "conexoes": "conexões",
    "usuarios": "usuários",
    "atendimentos_mes": "atendimentos no mês",
    "documentos_kb": "documentos na base de conhecimento",
    "agentes": "agentes de IA",
}


async def assert_plano_limit(empresa_id: int, recurso: str) -> None:
    """Levanta 402 se criar mais um `recurso` estoura o limite do plano.

    Versão para endpoints onde a empresa-alvo vem do PATH (ex.: o legado
    `POST /api/empresas/{id}/membros`), pelo mesmo motivo do
    `assert_plano_feature`: o `Depends` resolveria a empresa ATIVA do usuário,
    não a editada. `require_plano_limit` delega aqui.

    Raises:
        HTTPException 402: body {error: "quota_exceeded", recurso, quota_used,
            quota_max, plano_atual, upgrade_to, message}.
        HTTPException 404: empresa não existe (mesma razão do
            `assert_plano_feature`).
    """
    if recurso not in RECURSOS_CONTAVEIS:
        raise ValueError(f"recurso inválido: {recurso} (válidos: {RECURSOS_CONTAVEIS})")
    pool = await get_pool()
    try:
        plano = await get_plano_info(pool, empresa_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.") from e
    usado = await count_recurso(pool, empresa_id, recurso)

    if not plano.passou_limite(recurso, usado):
        return

    limite = plano.limite_de(recurso)
    upgrade = plano.upgrade_sugerido()
    logger.warning(
        "quota_exceeded",
        empresa_id=empresa_id,
        recurso=recurso,
        usado=usado,
        limite=limite,
        plano=plano.plano_slug,
    )
    detail_pt = (
        f"Limite do plano {plano.plano_nome} atingido: "
        f"{usado}/{limite} {_ROTULO_RECURSO.get(recurso, recurso)}. "
        + (
            f"Faça upgrade pro plano {upgrade.title()} pra continuar."
            if upgrade
            else "Entre em contato pra aumentar o limite."
        )
    )
    raise HTTPException(
        status_code=_STATUS_QUOTA_EXCEEDED,
        detail={
            "error": "quota_exceeded",
            "recurso": recurso,
            "quota_used": usado,
            "quota_max": limite,
            "plano_atual": plano.plano_slug,
            "upgrade_to": upgrade,
            "message": detail_pt,
        },
    )


def require_plano_limit(recurso: str):
    """Factory de dependency que bloqueia se quota do recurso estourou.

    Args:
        recurso: um de `RECURSOS_CONTAVEIS` ('conexoes', 'usuarios',
            'atendimentos_mes', 'documentos_kb', 'agentes').

    Raises:
        HTTPException 402: ver `assert_plano_limit`.
    """
    if recurso not in RECURSOS_CONTAVEIS:
        raise ValueError(f"recurso inválido: {recurso} (válidos: {RECURSOS_CONTAVEIS})")

    async def _checker(
        empresa_id: int = Depends(get_empresa_context),
    ) -> None:
        await assert_plano_limit(empresa_id, recurso)

    return _checker


async def assert_plano_feature(
    empresa_id: int, feature: str, *, mensagem: str | None = None
) -> None:
    """Levanta 402 se o plano da empresa não tem a feature.

    Mesmo contrato/payload do `require_plano_feature`, mas pra endpoints
    onde a empresa-alvo vem do PATH (ex.: `/api/empresas/{id}/...`) e não
    do header `X-Empresa-Id` que `get_empresa_context` resolve — usar o
    Depends ali gatearia pela empresa ATIVA do usuário, não pela editada
    (superadmin gerindo outra empresa ficaria preso ao próprio plano).

    Args:
        empresa_id: empresa-alvo (do path).
        feature: chave em `plano.features` JSON.
        mensagem: texto pt-BR amigável que substitui o default no
            `detail.message` (a UI mostra direto via api-error-shared).

    Raises:
        HTTPException 402: feature não disponível no plano atual.
        HTTPException 404: empresa não existe. Sem isto, superadmin (que
            passa em `is_admin_of` pra QUALQUER id) apontando pra empresa
            inexistente viraria 500 técnico — o `ValueError` do
            `get_plano_info` estourava antes do 404 que o endpoint dava.
    """
    pool = await get_pool()
    try:
        plano = await get_plano_info(pool, empresa_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.") from e

    if plano.tem_feature(feature):
        return

    upgrade = plano.upgrade_sugerido()
    logger.warning(
        "feature_unavailable",
        empresa_id=empresa_id,
        feature=feature,
        plano=plano.plano_slug,
    )
    detail_pt = mensagem or (
        f"Feature '{feature}' não está disponível no plano "
        f"{plano.plano_nome}. "
        + (
            f"Faça upgrade pro plano {upgrade.title()} pra liberar."
            if upgrade
            else "Feature exclusiva — entre em contato."
        )
    )
    raise HTTPException(
        status_code=_STATUS_QUOTA_EXCEEDED,
        detail={
            "error": "feature_unavailable",
            "feature": feature,
            "plano_atual": plano.plano_slug,
            "upgrade_to": upgrade,
            "message": detail_pt,
        },
    )


def require_plano_feature(feature: str):
    """Factory de dependency que bloqueia se plano não tem a feature.

    Args:
        feature: chave em `plano.features` JSON ('calendar', 'mcp',
            'rbac', 'menu_moderno', 'white_label', 'voz').

    Raises:
        HTTPException 402: feature não disponível no plano atual.
    """

    async def _checker(
        empresa_id: int = Depends(get_empresa_context),
    ) -> None:
        await assert_plano_feature(empresa_id, feature)

    return _checker
