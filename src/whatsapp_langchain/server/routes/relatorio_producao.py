"""Relatório de produção — gestão da plataforma (mig 173).

Ferramenta da VSA, não de cliente: fala do servidor inteiro (disco, containers,
fila, migrations). Por isso o gate é `is_superadmin`, o mesmo do relatório de
uso por cliente — e não uma permissão nova. Permissão do catálogo é concedida
ao perfil Admin de TODO tenant, o que abriria a tela para os clientes.

Estas rotas não geram o relatório: quem gera é o script no host, que tem acesso
a docker, disco e aos logs da Evolution. Aqui só se lê o que ele publicou e se
enfileira o pedido de "gerar agora".
"""

from __future__ import annotations

from datetime import time

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from whatsapp_langchain.server.dependencies import (
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.empresa import is_superadmin
from whatsapp_langchain.shared.relatorio_producao import (
    criar_pedido,
    get_config,
    get_relatorio,
    listar_relatorios,
    pedido_pendente,
    update_config,
)

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/relatorios/producao",
    tags=["relatorio-producao"],
    dependencies=[Depends(verify_service_token)],
)


async def _exigir_superadmin(user_id: str) -> None:
    pool = await get_pool()
    if not await is_superadmin(pool, user_id):
        raise HTTPException(status_code=403, detail="Apenas superadmins.")


class ConfigInput(BaseModel):
    ativo: bool = True
    #: "HH:MM" — o mesmo formato que o input `time` do navegador manda.
    horario: str = Field(pattern=r"^\d{2}:\d{2}$")
    tz: str = Field(min_length=3, max_length=64)

    @field_validator("horario")
    @classmethod
    def _hora_valida(cls, v: str) -> str:
        h, m = (int(p) for p in v.split(":"))
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError("horário inválido")
        return v


@router.get("")
async def listar(
    limite: int = 30,
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    """Histórico + o que está pendente, que é o que a tela precisa de uma vez."""
    await _exigir_superadmin(user_id)
    pool = await get_pool()
    cfg = await get_config(pool)
    return {
        "relatorios": await listar_relatorios(pool, limite=min(limite, 100)),
        "pendente": await pedido_pendente(pool),
        "config": {
            "ativo": cfg.ativo,
            "horario": cfg.horario.strftime("%H:%M"),
            "tz": cfg.tz,
            "last_run_date": cfg.last_run_date,
        },
    }


@router.get("/{relatorio_id}")
async def detalhe(
    relatorio_id: int,
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    """Um relatório com os dados crus — é o que permite conferir a conclusão
    contra a fonte, em vez de confiar no texto."""
    await _exigir_superadmin(user_id)
    pool = await get_pool()
    rel = await get_relatorio(pool, relatorio_id)
    if rel is None:
        raise HTTPException(status_code=404, detail="Relatório não encontrado.")
    return rel


@router.post("/gerar", status_code=202)
async def gerar(user_id: str = Depends(get_user_id_from_request)) -> dict:
    """Enfileira "gerar agora".

    **202, não 200**: o relatório não fica pronto nesta requisição. Quem produz
    é o host, no próximo ciclo — costuma levar menos de um minuto, mas é
    assíncrono por construção, porque o container não pode disparar nada no
    host.
    """
    await _exigir_superadmin(user_id)
    pool = await get_pool()
    pedido = await criar_pedido(pool, user_id=user_id)
    return {"ok": True, **pedido}


@router.put("/config")
async def salvar_config(
    body: ConfigInput,
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    """Horário do envio agendado.

    O timer do systemd continua acordando o script; o que muda é a decisão de
    "é a minha hora?", que passa a sair daqui. Mesmo desenho do resumo diário
    (mig 135) — quem opera muda horário pelo painel, não por unit file.
    """
    await _exigir_superadmin(user_id)
    h, m = (int(p) for p in body.horario.split(":"))
    pool = await get_pool()
    await update_config(pool, ativo=body.ativo, horario=time(h, m), tz=body.tz)
    logger.info("relatorio_producao_config_salva", actor_user_id=user_id)
    return {"ok": True}
