"""Endpoints CRUD do menu chatbot árvore (Sub-fase B).

Padrão de URLs:
    /api/v1/menus              — list/create menu
    /api/v1/menus/{id}         — get/update/delete menu
    /api/v1/menus/{id}/itens   — list/create item raiz
    /api/v1/menus/{id}/itens/{item_id}  — get/update/delete item
    /api/v1/menus/{id}/itens/reorder    — reordena items de um nível

Hierarquia: items têm self-FK `parent_id`. Cliente do painel constrói
árvore via list completa (ordenada por parent_id NULLS FIRST, ordem) ou
chama list_children explicitamente passando `parent_id` query param.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.server.dependencies_rbac import require_permission
from whatsapp_langchain.shared.audit import diff_dicts, record_audit
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.menu_chatbot import (
    ACAO_TIPOS,
    create_item,
    create_menu,
    delete_item,
    delete_menu,
    get_item,
    get_menu_by_id,
    list_children,
    list_items_do_menu,
    list_menus,
    reorder_items,
    update_item,
    update_menu,
)

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/v1/menus",
    tags=["menu-chatbot"],
    dependencies=[Depends(verify_service_token)],
)


# ---- Schemas ----


class CreateMenuInput(BaseModel):
    nome: str = Field(min_length=1, max_length=120)
    mensagem_boas_vindas: str = Field(min_length=1, max_length=4000)
    conexao_id: int | None = None
    trigger_keywords: list[str] | None = Field(default=None, max_length=20)
    mensagem_opcao_invalida: str | None = Field(default=None, max_length=2000)


class UpdateMenuInput(BaseModel):
    nome: str | None = Field(default=None, min_length=1, max_length=120)
    mensagem_boas_vindas: str | None = Field(default=None, min_length=1, max_length=4000)
    conexao_id: int | None = None
    trigger_keywords: list[str] | None = Field(default=None, max_length=20)
    mensagem_opcao_invalida: str | None = Field(default=None, max_length=2000)
    ativo: bool | None = None


class CreateItemInput(BaseModel):
    label: str = Field(min_length=1, max_length=200)
    acao_tipo: str
    acao_payload: dict[str, Any] = Field(default_factory=dict)
    parent_id: int | None = None
    ordem: int | None = Field(default=None, ge=1, le=99)

    @field_validator("acao_tipo")
    @classmethod
    def _validate_acao_tipo(cls, v: str) -> str:
        if v not in ACAO_TIPOS:
            raise ValueError(f"acao_tipo deve ser um de {sorted(ACAO_TIPOS)}")
        return v


class UpdateItemInput(BaseModel):
    label: str | None = Field(default=None, min_length=1, max_length=200)
    acao_tipo: str | None = None
    acao_payload: dict[str, Any] | None = None
    ordem: int | None = Field(default=None, ge=1, le=99)
    ativo: bool | None = None

    @field_validator("acao_tipo")
    @classmethod
    def _validate_acao_tipo(cls, v: str | None) -> str | None:
        if v is not None and v not in ACAO_TIPOS:
            raise ValueError(f"acao_tipo deve ser um de {sorted(ACAO_TIPOS)}")
        return v


class ReorderInput(BaseModel):
    parent_id: int | None = None
    ordered_ids: list[int] = Field(min_length=1, max_length=99)


# ---- Endpoints Menu ----


@router.get("")
async def list_menus_endpoint(
    only_active: bool = False,
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("menu_chatbot.read")),
) -> dict:
    pool = await get_pool()
    items = await list_menus(pool, empresa_id, only_active=only_active)
    return {"items": [m.to_dict() for m in items]}


@router.get("/{menu_id}")
async def get_menu_endpoint(
    menu_id: int,
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("menu_chatbot.read")),
) -> dict:
    pool = await get_pool()
    out = await get_menu_by_id(pool, empresa_id, menu_id)
    if out is None:
        raise HTTPException(status_code=404, detail="Menu não encontrado.")
    return out.to_dict()


@router.post("", status_code=201)
async def create_menu_endpoint(
    body: CreateMenuInput,
    request: Request,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("menu_chatbot.write")),
) -> dict:
    pool = await get_pool()
    out = await create_menu(
        pool,
        empresa_id,
        nome=body.nome,
        mensagem_boas_vindas=body.mensagem_boas_vindas,
        conexao_id=body.conexao_id,
        trigger_keywords=body.trigger_keywords,
        mensagem_opcao_invalida=body.mensagem_opcao_invalida,
        user_id=user_id,
    )
    await record_audit(
        pool,
        empresa_id=empresa_id,
        user_id=user_id,
        action="menu_chatbot.create",
        entity_type="menu_chatbot",
        entity_id=str(out.id),
        payload_diff={"after": out.to_dict()},
        request=request,
    )
    return out.to_dict()


@router.put("/{menu_id}")
async def update_menu_endpoint(
    menu_id: int,
    body: UpdateMenuInput,
    request: Request,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("menu_chatbot.write")),
) -> dict:
    pool = await get_pool()
    before = await get_menu_by_id(pool, empresa_id, menu_id)
    if before is None:
        raise HTTPException(status_code=404, detail="Menu não encontrado.")

    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    updated = await update_menu(pool, empresa_id, menu_id, **fields)
    if updated is None:
        raise HTTPException(status_code=404, detail="Menu não encontrado.")

    await record_audit(
        pool,
        empresa_id=empresa_id,
        user_id=user_id,
        action="menu_chatbot.update",
        entity_type="menu_chatbot",
        entity_id=str(menu_id),
        payload_diff=diff_dicts(before.to_dict(), updated.to_dict()),
        request=request,
    )
    return updated.to_dict()


@router.delete("/{menu_id}", status_code=204)
async def delete_menu_endpoint(
    menu_id: int,
    request: Request,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("menu_chatbot.write")),
) -> None:
    pool = await get_pool()
    before = await get_menu_by_id(pool, empresa_id, menu_id)
    if before is None:
        raise HTTPException(status_code=404, detail="Menu não encontrado.")
    ok = await delete_menu(pool, empresa_id, menu_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Menu não encontrado.")
    await record_audit(
        pool,
        empresa_id=empresa_id,
        user_id=user_id,
        action="menu_chatbot.delete",
        entity_type="menu_chatbot",
        entity_id=str(menu_id),
        payload_diff={"before": before.to_dict()},
        request=request,
    )


# ---- Endpoints Item ----


def _ensure_menu_owns_item(menu_id: int, item) -> None:
    """Garante que item pertence ao menu (defesa em profundidade contra
    URL forjada onde menu_id é da empresa A e item_id pertence a empresa B)."""
    if item.menu_id != menu_id:
        raise HTTPException(
            status_code=404, detail="Item não encontrado nesse menu."
        )


@router.get("/{menu_id}/itens")
async def list_items_endpoint(
    menu_id: int,
    parent_id: int | None = Query(
        default=None,
        description="Filtra por parent. Se omitido, retorna árvore inteira.",
    ),
    only_active: bool = True,
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("menu_chatbot.read")),
) -> dict:
    pool = await get_pool()
    menu = await get_menu_by_id(pool, empresa_id, menu_id)
    if menu is None:
        raise HTTPException(status_code=404, detail="Menu não encontrado.")
    # Sem parent_id no query → retorna tudo. Com parent_id → só esse nível.
    if parent_id is None:
        items = await list_items_do_menu(pool, menu_id, only_active=only_active)
    else:
        items = await list_children(pool, menu_id, parent_id)
    return {"items": [i.to_dict() for i in items]}


@router.post("/{menu_id}/itens", status_code=201)
async def create_item_endpoint(
    menu_id: int,
    body: CreateItemInput,
    request: Request,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("menu_chatbot.write")),
) -> dict:
    pool = await get_pool()
    menu = await get_menu_by_id(pool, empresa_id, menu_id)
    if menu is None:
        raise HTTPException(status_code=404, detail="Menu não encontrado.")
    # Valida parent_id pertence ao mesmo menu
    if body.parent_id is not None:
        parent = await get_item(pool, body.parent_id)
        if parent is None or parent.menu_id != menu_id:
            raise HTTPException(
                status_code=400,
                detail="parent_id não pertence a esse menu.",
            )
    out = await create_item(
        pool,
        menu_id,
        label=body.label,
        acao_tipo=body.acao_tipo,
        acao_payload=body.acao_payload,
        parent_id=body.parent_id,
        ordem=body.ordem,
    )
    await record_audit(
        pool,
        empresa_id=empresa_id,
        user_id=user_id,
        action="menu_chatbot.item.create",
        entity_type="menu_item",
        entity_id=str(out.id),
        payload_diff={"after": out.to_dict()},
        request=request,
    )
    return out.to_dict()


@router.get("/{menu_id}/itens/{item_id}")
async def get_item_endpoint(
    menu_id: int,
    item_id: int,
    empresa_id: int = Depends(get_empresa_context),
    _: None = Depends(require_permission("menu_chatbot.read")),
) -> dict:
    pool = await get_pool()
    menu = await get_menu_by_id(pool, empresa_id, menu_id)
    if menu is None:
        raise HTTPException(status_code=404, detail="Menu não encontrado.")
    item = await get_item(pool, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item não encontrado.")
    _ensure_menu_owns_item(menu_id, item)
    return item.to_dict()


@router.put("/{menu_id}/itens/{item_id}")
async def update_item_endpoint(
    menu_id: int,
    item_id: int,
    body: UpdateItemInput,
    request: Request,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("menu_chatbot.write")),
) -> dict:
    pool = await get_pool()
    menu = await get_menu_by_id(pool, empresa_id, menu_id)
    if menu is None:
        raise HTTPException(status_code=404, detail="Menu não encontrado.")
    before = await get_item(pool, item_id)
    if before is None:
        raise HTTPException(status_code=404, detail="Item não encontrado.")
    _ensure_menu_owns_item(menu_id, before)

    fields = {k: v for k, v in body.model_dump().items() if v is not None}
    updated = await update_item(pool, item_id, **fields)
    if updated is None:
        raise HTTPException(status_code=404, detail="Item não encontrado.")

    await record_audit(
        pool,
        empresa_id=empresa_id,
        user_id=user_id,
        action="menu_chatbot.item.update",
        entity_type="menu_item",
        entity_id=str(item_id),
        payload_diff=diff_dicts(before.to_dict(), updated.to_dict()),
        request=request,
    )
    return updated.to_dict()


@router.delete("/{menu_id}/itens/{item_id}", status_code=204)
async def delete_item_endpoint(
    menu_id: int,
    item_id: int,
    request: Request,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("menu_chatbot.write")),
) -> None:
    pool = await get_pool()
    menu = await get_menu_by_id(pool, empresa_id, menu_id)
    if menu is None:
        raise HTTPException(status_code=404, detail="Menu não encontrado.")
    before = await get_item(pool, item_id)
    if before is None:
        raise HTTPException(status_code=404, detail="Item não encontrado.")
    _ensure_menu_owns_item(menu_id, before)
    ok = await delete_item(pool, item_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Item não encontrado.")
    await record_audit(
        pool,
        empresa_id=empresa_id,
        user_id=user_id,
        action="menu_chatbot.item.delete",
        entity_type="menu_item",
        entity_id=str(item_id),
        payload_diff={"before": before.to_dict()},
        request=request,
    )


@router.post("/{menu_id}/itens/reorder")
async def reorder_endpoint(
    menu_id: int,
    body: ReorderInput,
    request: Request,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
    _: None = Depends(require_permission("menu_chatbot.write")),
) -> dict:
    """Reordena items de um nível. `ordered_ids` define a nova sequência."""
    pool = await get_pool()
    menu = await get_menu_by_id(pool, empresa_id, menu_id)
    if menu is None:
        raise HTTPException(status_code=404, detail="Menu não encontrado.")
    # Valida todos os ids pertencem ao menu + ao mesmo parent
    for item_id in body.ordered_ids:
        item = await get_item(pool, item_id)
        if item is None or item.menu_id != menu_id:
            raise HTTPException(
                status_code=400,
                detail=f"Item {item_id} não pertence a esse menu.",
            )
        if item.parent_id != body.parent_id:
            raise HTTPException(
                status_code=400,
                detail=f"Item {item_id} não está no nível parent_id={body.parent_id}.",
            )
    await reorder_items(pool, menu_id, body.parent_id, body.ordered_ids)
    await record_audit(
        pool,
        empresa_id=empresa_id,
        user_id=user_id,
        action="menu_chatbot.item.reorder",
        entity_type="menu_chatbot",
        entity_id=str(menu_id),
        payload_diff={
            "parent_id": body.parent_id,
            "ordered_ids": body.ordered_ids,
        },
        request=request,
    )
    return {"ok": True, "ordered_ids": body.ordered_ids}
