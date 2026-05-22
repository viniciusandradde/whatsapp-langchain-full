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


def require_plano_limit(recurso: str):
    """Factory de dependency que bloqueia se quota do recurso estourou.

    Args:
        recurso: nome do recurso ('conexoes', 'usuarios', 'atendimentos_mes',
            'documentos_kb'). Mesmo nome usado por `count_recurso()`.

    Raises:
        HTTPException 402: com body {detail, quota_max, quota_used,
            plano_atual, upgrade_to}.
    """
    valid = ("conexoes", "usuarios", "atendimentos_mes", "documentos_kb")
    if recurso not in valid:
        raise ValueError(f"recurso inválido: {recurso} (válidos: {valid})")

    async def _checker(
        empresa_id: int = Depends(get_empresa_context),
    ) -> None:
        pool = await get_pool()
        plano = await get_plano_info(pool, empresa_id)
        usado = await count_recurso(pool, empresa_id, recurso)

        if plano.passou_limite(recurso, usado):
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
                f"{usado}/{limite} {recurso}. "
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

    return _checker


def require_plano_feature(feature: str):
    """Factory de dependency que bloqueia se plano não tem a feature.

    Args:
        feature: chave em `plano.features` JSON ('calendar', 'mcp',
            'rbac', 'menu_moderno', 'white_label').

    Raises:
        HTTPException 402: feature não disponível no plano atual.
    """

    async def _checker(
        empresa_id: int = Depends(get_empresa_context),
    ) -> None:
        pool = await get_pool()
        plano = await get_plano_info(pool, empresa_id)

        if not plano.tem_feature(feature):
            upgrade = plano.upgrade_sugerido()
            logger.warning(
                "feature_unavailable",
                empresa_id=empresa_id,
                feature=feature,
                plano=plano.plano_slug,
            )
            detail_pt = (
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

    return _checker
