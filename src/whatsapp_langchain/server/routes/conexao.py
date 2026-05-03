"""CRUD de conexões WhatsApp do painel admin.

Endpoints escopados pela empresa ativa (`get_empresa_context`). Mutações
ficam abertas a qualquer membro no MVP — diferenciar por role é tarefa
futura (M1.x).
"""

import httpx
import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    verify_service_token,
)
from whatsapp_langchain.shared.conexao import (
    get_conexao_by_id,
    list_conexoes,
    set_conexao_status,
    upsert_conexao,
)
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.models import Conexao, ConexaoInput

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/conexoes",
    tags=["conexoes"],
    dependencies=[Depends(verify_service_token)],
)


class TestEvolutionInput(BaseModel):
    """Payload do POST /api/conexoes/test-evolution.

    Não persiste — só valida se as credenciais batem com uma instância
    Evolution real. Útil pra dar feedback antes de salvar a conexão.
    """

    api_url: str = Field(min_length=1, max_length=2048)
    api_key: str = Field(min_length=1, max_length=200)
    instance_name: str = Field(min_length=1, max_length=200)


class TestEvolutionResult(BaseModel):
    ok: bool
    state: str | None = None
    instance_name: str | None = None
    error: str | None = None


@router.get("")
async def list_my_conexoes(
    empresa_id: int = Depends(get_empresa_context),
) -> dict[str, list[Conexao]]:
    """Lista conexões da empresa ativa, default primeiro."""
    pool = await get_pool()
    return {"conexoes": await list_conexoes(pool, empresa_id)}


@router.get("/{conexao_id}")
async def read_conexao(
    conexao_id: int,
    empresa_id: int = Depends(get_empresa_context),
) -> Conexao:
    """Detalhe de uma conexão. 404 quando inexistente, 403 cross-tenant."""
    pool = await get_pool()
    conexao = await get_conexao_by_id(pool, conexao_id)
    if conexao is None:
        raise HTTPException(status_code=404, detail="Conexão não encontrada.")
    if conexao.empresa_id != empresa_id:
        raise HTTPException(status_code=403, detail="Conexão fora da empresa ativa.")
    return conexao


@router.post("")
async def create_conexao(
    body: ConexaoInput,
    empresa_id: int = Depends(get_empresa_context),
) -> Conexao:
    """Cria conexão na empresa ativa. UPSERT — se from_number existir, atualiza."""
    pool = await get_pool()
    out = await upsert_conexao(pool, empresa_id, body)
    logger.info(
        "conexao_created",
        empresa_id=empresa_id,
        conexao_id=out.id,
        provider=out.provider,
        from_number=out.from_number,
    )
    return out


@router.put("/{conexao_id}")
async def update_conexao(
    conexao_id: int,
    body: ConexaoInput,
    empresa_id: int = Depends(get_empresa_context),
) -> Conexao:
    """Atualiza uma conexão existente. 404 quando inexistente, 403 cross-tenant."""
    pool = await get_pool()
    existing = await get_conexao_by_id(pool, conexao_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Conexão não encontrada.")
    if existing.empresa_id != empresa_id:
        raise HTTPException(status_code=403, detail="Conexão fora da empresa ativa.")

    # Mantém o from_number do payload — UPSERT vai casar pelo UNIQUE.
    out = await upsert_conexao(pool, empresa_id, body)
    logger.info(
        "conexao_updated",
        empresa_id=empresa_id,
        conexao_id=out.id,
        from_number=out.from_number,
    )
    return out


@router.delete("/{conexao_id}", status_code=204)
async def disable_conexao(
    conexao_id: int,
    empresa_id: int = Depends(get_empresa_context),
) -> None:
    """Soft-delete: status='disabled'. Preserva histórico em message_queue."""
    pool = await get_pool()
    existing = await get_conexao_by_id(pool, conexao_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Conexão não encontrada.")
    if existing.empresa_id != empresa_id:
        raise HTTPException(status_code=403, detail="Conexão fora da empresa ativa.")
    await set_conexao_status(pool, conexao_id, "disabled")
    logger.info("conexao_disabled", empresa_id=empresa_id, conexao_id=conexao_id)


@router.post("/test-evolution")
async def test_evolution_connection(
    body: TestEvolutionInput,
    _empresa_id: int = Depends(get_empresa_context),
) -> TestEvolutionResult:
    """Valida credenciais Evolution sem persistir (M2.b).

    Faz `GET {api_url}/instance/connectionState/{instance}` com
    header `apikey`. Retorna ok=true quando state ∈ {open, connecting}
    — `open` é o estado pareado e funcional; `connecting` é OK
    transitório enquanto o QR code está sendo escaneado.
    """
    api_url = body.api_url.rstrip("/")
    target = f"{api_url}/instance/connectionState/{body.instance_name}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as http:
            response = await http.get(target, headers={"apikey": body.api_key})
    except httpx.RequestError as exc:
        logger.warning(
            "test_evolution_network_error",
            api_url=api_url,
            instance=body.instance_name,
            error=str(exc),
        )
        return TestEvolutionResult(
            ok=False,
            error=f"Não foi possível conectar à Evolution API: {exc}",
        )

    if response.status_code == 401:
        return TestEvolutionResult(ok=False, error="apikey inválida.")
    if response.status_code == 404:
        return TestEvolutionResult(
            ok=False,
            instance_name=body.instance_name,
            error=f"Instância '{body.instance_name}' não existe.",
        )
    if not response.is_success:
        return TestEvolutionResult(
            ok=False,
            error=f"Evolution retornou {response.status_code}: {response.text[:200]}",
        )

    data = response.json()
    instance = data.get("instance") or {}
    state = instance.get("state") if isinstance(instance, dict) else None
    instance_name = (
        instance.get("instanceName")
        if isinstance(instance, dict)
        else body.instance_name
    )

    return TestEvolutionResult(
        ok=state in {"open", "connecting"},
        state=state,
        instance_name=instance_name,
        error=None
        if state in {"open", "connecting"}
        else f"Instância encontrada mas state='{state}'.",
    )
