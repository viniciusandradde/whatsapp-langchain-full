"""Módulo de Uso — relatório mensal por cliente (mig 165).

Ferramenta de plataforma, não de tenant: quem opera é a VSA, olhando os
clientes dela. Por isso o guarda é **superadmin** em toda rota, e não
`require_permission` — a permissão é resolvida contra a empresa ATIVA do
header, que aqui não tem relação com a empresa-alvo do path. Mesmo racional
dos endpoints de `empresa_admin.py` e de `test_runner.py`.

Endpoints:
    GET  /api/relatorios/uso/empresas          → clientes + elegibilidade
    GET  /api/relatorios/uso/{id}              → payload do relatório (JSON)
    GET  /api/relatorios/uso/{id}/pdf          → o documento
    POST /api/relatorios/uso/{id}/enviar       → gera e dispara agora
    GET  /api/relatorios/uso/{id}/config       → agendamento mensal
    PUT  /api/relatorios/uso/{id}/config       → salva o agendamento
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from whatsapp_langchain.server.dependencies import (
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.empresa import is_superadmin
from whatsapp_langchain.shared.relatorio_uso import (
    Competencia,
    enviar_relatorio,
    gerar_pdf,
    listar_clientes,
    montar_dados,
)
from whatsapp_langchain.shared.rls_context import empresa_scope

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/relatorios/uso",
    tags=["relatorio-uso"],
    dependencies=[Depends(verify_service_token)],
)


async def _exigir_superadmin(user_id: str) -> None:
    pool = await get_pool()
    if not await is_superadmin(pool, user_id):
        raise HTTPException(status_code=403, detail="Apenas superadmins.")


def _competencia(rotulo: str | None) -> Competencia:
    """Rótulo da query, ou o último mês fechado quando ausente."""
    if not rotulo:
        return Competencia.mes_anterior()
    try:
        return Competencia.de_rotulo(rotulo)
    except (ValueError, IndexError) as exc:
        raise HTTPException(
            status_code=400,
            detail="Competência inválida. Use o formato AAAA-MM, por exemplo 2026-07.",
        ) from exc


class ConfigUso(BaseModel):
    ativo: bool = False
    telefone: str | None = Field(default=None, max_length=32)
    dia: int = Field(default=1, ge=1, le=28)
    horario: str = Field(default="09:00", pattern=r"^\d{2}:\d{2}$")
    tz: str = Field(default="America/Campo_Grande", max_length=64)
    # Só leitura — o PUT aceita e ignora, como o resumo diário faz.
    ultima_competencia: str | None = None
    ultimo_status: str | None = None
    ultimo_erro: str | None = None
    ultima_tentativa_em: str | None = None


class EnviarInput(BaseModel):
    competencia: str | None = None
    # Sobrescreve o telefone cadastrado — usado no primeiro disparo, para o
    # número da própria VSA em vez do cliente.
    telefone: str | None = Field(default=None, max_length=32)


@router.get("/empresas")
async def listar_empresas(
    user_id: str = Depends(get_user_id_from_request),
) -> dict[str, list[dict[str, Any]]]:
    await _exigir_superadmin(user_id)
    pool = await get_pool()
    return {"clientes": await listar_clientes(pool, user_id)}


@router.get("/{empresa_id}")
async def ler_relatorio(
    empresa_id: int,
    competencia: str | None = Query(default=None, description="AAAA-MM"),
    user_id: str = Depends(get_user_id_from_request),
) -> dict[str, Any]:
    await _exigir_superadmin(user_id)
    pool = await get_pool()
    comp = _competencia(competencia)
    return await montar_dados(pool, empresa_id, comp)


@router.get("/{empresa_id}/pdf")
async def baixar_pdf(
    empresa_id: int,
    competencia: str | None = Query(default=None, description="AAAA-MM"),
    user_id: str = Depends(get_user_id_from_request),
) -> Response:
    await _exigir_superadmin(user_id)
    pool = await get_pool()
    comp = _competencia(competencia)
    pdf, nome = await gerar_pdf(pool, empresa_id, comp)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nome}"'},
    )


@router.post("/{empresa_id}/enviar")
async def enviar(
    empresa_id: int,
    body: EnviarInput,
    user_id: str = Depends(get_user_id_from_request),
) -> dict[str, Any]:
    """Dispara o relatório agora, sem tocar no claim do agendamento.

    Devolve **200 com `ok: false`** quando o provedor recusa, em vez de 5xx: a
    falha é do WhatsApp, não da nossa API, e a tela precisa do motivo em texto.
    Mesma escolha do `POST /resumo-diario/testar`.
    """
    await _exigir_superadmin(user_id)
    pool = await get_pool()
    comp = _competencia(body.competencia)
    try:
        conexao_id = await enviar_relatorio(
            pool, empresa_id, comp, telefone=body.telefone
        )
    except Exception as exc:
        logger.warning(
            "relatorio_uso_envio_manual_falhou",
            empresa_id=empresa_id,
            competencia=comp.rotulo,
            error=str(exc),
        )
        return {"ok": False, "erro": str(exc), "competencia": comp.rotulo}
    logger.info(
        "relatorio_uso_envio_manual",
        empresa_id=empresa_id,
        competencia=comp.rotulo,
        conexao_id=conexao_id,
        por=user_id,
    )
    return {"ok": True, "competencia": comp.rotulo, "conexao_id": conexao_id}


@router.get("/{empresa_id}/config")
async def ler_config(
    empresa_id: int,
    user_id: str = Depends(get_user_id_from_request),
) -> ConfigUso:
    await _exigir_superadmin(user_id)
    pool = await get_pool()
    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                SELECT relatorio_uso_ativo, relatorio_uso_telefone,
                       relatorio_uso_dia, relatorio_uso_horario, relatorio_uso_tz,
                       relatorio_uso_last_sent, relatorio_uso_last_status,
                       relatorio_uso_last_error, relatorio_uso_last_attempt_at
                  FROM empresa WHERE id = %s
                """,
                (empresa_id,),
            )
            row = await cur.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Empresa não encontrada.")
    return ConfigUso(
        ativo=row[0],
        telefone=row[1],
        dia=row[2],
        horario=row[3].strftime("%H:%M"),
        tz=row[4],
        ultima_competencia=row[5].isoformat() if row[5] else None,
        ultimo_status=row[6],
        ultimo_erro=row[7],
        ultima_tentativa_em=row[8].isoformat() if row[8] else None,
    )


@router.put("/{empresa_id}/config")
async def salvar_config(
    empresa_id: int,
    body: ConfigUso,
    user_id: str = Depends(get_user_id_from_request),
) -> ConfigUso:
    await _exigir_superadmin(user_id)
    from whatsapp_langchain.shared.campanha import normalize_phone

    telefone = normalize_phone(body.telefone) if body.telefone else None
    if body.ativo and not telefone:
        raise HTTPException(
            status_code=400,
            detail=(
                "Informe um telefone válido, com código do país, "
                "para ativar o envio mensal. Exemplo: +5567999068963."
            ),
        )

    pool = await get_pool()
    with empresa_scope(empresa_id):
        async with pool.connection() as conn:
            cur = await conn.execute(
                """
                UPDATE empresa
                   SET relatorio_uso_ativo = %(ativo)s,
                       relatorio_uso_telefone = %(tel)s,
                       relatorio_uso_dia = %(dia)s,
                       relatorio_uso_horario = %(hora)s,
                       relatorio_uso_tz = %(tz)s
                 WHERE id = %(eid)s
                """,
                {
                    "ativo": body.ativo,
                    "tel": telefone,
                    "dia": body.dia,
                    "hora": body.horario,
                    "tz": body.tz,
                    "eid": empresa_id,
                },
            )
            if cur.rowcount == 0:
                raise HTTPException(status_code=404, detail="Empresa não encontrada.")
            await conn.commit()

    logger.info(
        "relatorio_uso_config_salva",
        empresa_id=empresa_id,
        ativo=body.ativo,
        dia=body.dia,
        por=user_id,
    )
    return await ler_config(empresa_id, user_id)
