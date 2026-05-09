"""CRUD da Base de Conhecimento (M5.c).

Endpoints escopados pela empresa ativa via cookie. O empresa_id sai do
`get_empresa_context` (mesmo padrão de modelo_mensagem/hook).
"""

from __future__ import annotations

from pathlib import Path

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from whatsapp_langchain.server.dependencies import (
    get_empresa_context,
    get_user_id_from_request,
    verify_service_token,
)
from whatsapp_langchain.shared import base_conhecimento
from whatsapp_langchain.shared.db import get_pool
from whatsapp_langchain.shared.file_extractor import (
    FileExtractionError,
    FileTooLargeError,
    UnsupportedFileTypeError,
    extract_text,
)
from whatsapp_langchain.shared.models import (
    DocumentoConhecimento,
    DocumentoConhecimentoInput,
)

logger = structlog.get_logger()

router = APIRouter(
    prefix="/api/base-conhecimento",
    tags=["base-conhecimento"],
    dependencies=[Depends(verify_service_token)],
)


@router.get("")
async def list_documentos(
    empresa_id: int = Depends(get_empresa_context),
    pasta_id: int | None = None,
    raiz: bool = False,
    incluir_subpastas: bool = False,
) -> dict[str, list[DocumentoConhecimento]]:
    """Lista docs da empresa (E2.C).

    Filtros opcionais:
    - `raiz=true` ⇒ só docs sem pasta (pasta_id IS NULL).
    - `pasta_id=N` ⇒ só docs daquela pasta. Combinado com
      `incluir_subpastas=true` aplica recursive CTE pra incluir descendentes.
    - Sem filtros ⇒ todos os docs da empresa (compat).
    """
    pool = await get_pool()

    pasta_ids: set[int] | None = None
    pasta_id_set = False
    target_pasta_id: int | None = None

    if pasta_id is not None:
        if incluir_subpastas:
            from whatsapp_langchain.shared.pasta import get_descendant_ids

            pasta_ids = await get_descendant_ids(pool, empresa_id, [pasta_id])
            if not pasta_ids:
                # Não existe ou não há subpastas — devolve nada
                return {"documentos": []}
        else:
            pasta_id_set = True
            target_pasta_id = pasta_id
    elif raiz:
        pasta_id_set = True

    docs = await base_conhecimento.list_documentos(
        pool,
        empresa_id,
        pasta_id=target_pasta_id,
        pasta_id_set=pasta_id_set,
        pasta_ids=pasta_ids,
    )
    return {"documentos": docs}


@router.get("/{doc_id}")
async def get_documento(
    doc_id: int,
    empresa_id: int = Depends(get_empresa_context),
) -> DocumentoConhecimento:
    pool = await get_pool()
    doc = await base_conhecimento.get_documento(pool, empresa_id, doc_id)
    if doc is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    return doc


@router.post("", status_code=201)
async def create_documento(
    body: DocumentoConhecimentoInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> DocumentoConhecimento:
    pool = await get_pool()
    out = await base_conhecimento.upsert_documento(
        pool, empresa_id, body, user_id=user_id
    )
    logger.info(
        "base_conhecimento_created",
        empresa_id=empresa_id,
        doc_id=out.id,
        titulo=out.titulo,
        user_id=user_id,
    )
    return out


@router.put("/{doc_id}")
async def update_documento(
    doc_id: int,
    body: DocumentoConhecimentoInput,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> DocumentoConhecimento:
    pool = await get_pool()
    existing = await base_conhecimento.get_documento(pool, empresa_id, doc_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    out = await base_conhecimento.upsert_documento(
        pool, empresa_id, body, doc_id=doc_id, user_id=user_id
    )
    logger.info(
        "base_conhecimento_updated",
        empresa_id=empresa_id,
        doc_id=doc_id,
        titulo=out.titulo,
        user_id=user_id,
    )
    return out


@router.delete("/{doc_id}", status_code=204)
async def delete_documento(
    doc_id: int,
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> None:
    pool = await get_pool()
    deleted = await base_conhecimento.delete_documento(pool, empresa_id, doc_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Documento não encontrado.")
    logger.info(
        "base_conhecimento_deleted",
        empresa_id=empresa_id,
        doc_id=doc_id,
        user_id=user_id,
    )


class _BuscarBody(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    k: int = Field(default=3, ge=1, le=10)
    rerank: bool = True


class _BuscarResultado(BaseModel):
    """M5.c.1: resposta da busca agora carrega chunk + reason do reranker."""

    documento: DocumentoConhecimento
    chunk_idx: int
    chunk_conteudo: str
    score: float
    reason: str | None = None


@router.post("/buscar")
async def buscar_documentos(
    body: _BuscarBody,
    empresa_id: int = Depends(get_empresa_context),
) -> dict[str, list[_BuscarResultado]]:
    """Endpoint de teste — espelha o que a tool do agente vê."""
    pool = await get_pool()
    results = await base_conhecimento.search_relevant(
        pool, empresa_id, body.query, k=body.k, rerank=body.rerank
    )
    return {
        "resultados": [
            _BuscarResultado(
                documento=r.documento,
                chunk_idx=r.chunk_idx,
                chunk_conteudo=r.chunk_conteudo,
                score=r.score,
                reason=r.reason,
            )
            for r in results
        ]
    }


@router.post("/upload", status_code=201)
async def upload_documento(
    arquivo: UploadFile = File(...),
    titulo: str | None = Form(default=None),
    tags: str = Form(default=""),
    pasta_id: int | None = Form(default=None),
    split_md_headers: bool = Form(default=True),
    empresa_id: int = Depends(get_empresa_context),
    user_id: str = Depends(get_user_id_from_request),
) -> dict:
    """Cria documento(s) a partir de upload de PDF/DOCX/MD/TXT (M5.c.2 + S.2).

    Multipart fields:
    - `arquivo` (file): obrigatório.
    - `titulo` (string): opcional. Default = nome do arquivo sem extensão.
    - `tags` (string): opcional, CSV (ex: "manual,faq").
    - `pasta_id` (int): opcional.
    - `split_md_headers` (bool): default true. Se .md, splita por H1/H2.

    Sprint S.2: pra .md, gera 1 doc por seção (H1/H2). Pra outros tipos,
    1 doc único. Retorna `{docs_created, doc_ids[]}`.
    """
    if not arquivo.filename:
        raise HTTPException(
            status_code=422, detail="Arquivo precisa ter nome com extensão."
        )

    raw = await arquivo.read()
    try:
        texto = await extract_text(arquivo.filename, raw)
    except UnsupportedFileTypeError as e:
        raise HTTPException(status_code=415, detail=str(e)) from e
    except FileTooLargeError as e:
        raise HTTPException(status_code=413, detail=str(e)) from e
    except FileExtractionError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    titulo_base = (titulo or "").strip() or Path(arquivo.filename).stem
    tags_list = [t.strip() for t in tags.split(",") if t.strip()]
    is_md = arquivo.filename.lower().endswith((".md", ".markdown"))
    pool = await get_pool()
    doc_ids: list[int] = []

    if is_md and split_md_headers:
        # Splita por H1/H2 — 1 doc por seção
        from whatsapp_langchain.shared.markdown_splitter import (
            split_md_by_headers,
        )

        sections = split_md_by_headers(texto, max_level=2, fallback_titulo=titulo_base)
        for sec in sections:
            body = DocumentoConhecimentoInput(
                titulo=f"{titulo_base} — {sec.titulo}"[:200],
                conteudo=sec.conteudo,
                tags=tags_list,
                ativo=True,
                pasta_id=pasta_id,
            )
            out = await base_conhecimento.upsert_documento(
                pool, empresa_id, body, user_id=user_id
            )
            doc_ids.append(out.id)
        logger.info(
            "base_conhecimento_uploaded_md_split",
            empresa_id=empresa_id, filename=arquivo.filename,
            sections=len(sections), bytes=len(raw),
        )
    else:
        body = DocumentoConhecimentoInput(
            titulo=titulo_base[:200],
            conteudo=texto,
            tags=tags_list,
            ativo=True,
            pasta_id=pasta_id,
        )
        out = await base_conhecimento.upsert_documento(
            pool, empresa_id, body, user_id=user_id
        )
        doc_ids.append(out.id)
        logger.info(
            "base_conhecimento_uploaded",
            empresa_id=empresa_id, doc_id=out.id, titulo=out.titulo,
            filename=arquivo.filename, bytes=len(raw), chars=len(texto),
        )

    return {"docs_created": len(doc_ids), "doc_ids": doc_ids}
