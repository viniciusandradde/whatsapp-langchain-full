"""OCR via OpenRouter Vision LLM (M5.c.3).

Usado pelo `file_extractor` quando:
- PDF retorna texto vazio/curto via pypdf (provavelmente escaneado)
- Upload é PNG/JPG/JPEG/WebP direto

Stack:
- `pdf2image` rasteriza páginas PDF em PIL.Image (precisa de
  `poppler-utils` no sistema — adicionado no Dockerfile.api)
- OpenRouter Vision (settings.openrouter_midia_model) extrai o texto
  via prompt explícito "transcreva fielmente"

Sem dependência de tesseract — Vision LLM cobre pt-BR melhor e tem
qualidade superior em PDFs com layout complexo.
"""

from __future__ import annotations

import base64
import io

import httpx
import structlog

from whatsapp_langchain.shared.config import settings

logger = structlog.get_logger()


# Cap de páginas pra evitar custo absurdo. PDFs escaneados longos
# precisam ser divididos manualmente pelo admin.
MAX_PDF_PAGES = 30

# DPI pra rasterização. 200 cobre texto pequeno; 300 dá leitura de
# subpontos mas dobra o custo (mais pixels = base64 maior = mais tokens).
PDF_RASTERIZE_DPI = 200

# Resize cap — se a imagem rasterizada exceder essa largura, reduz
# proporcionalmente. Vision LLMs aceitam até ~2k px de largura sem
# perda visível.
MAX_IMAGE_WIDTH_PX = 2000

# Prompt do Vision LLM. Importante:
# - Pedir transcrição FIEL (não resumo)
# - Estruturar como markdown quando possível
# - Não inventar
OCR_SYSTEM_PROMPT = (
    "Você é um OCR/transcritor técnico. Sua única tarefa é transcrever "
    "FIELMENTE o texto presente na imagem. Regras:\n"
    "- Não resuma. Não comente. Não acrescente nada que não esteja na "
    "imagem.\n"
    "- Preserve a ordem de leitura natural (cabeçalho → corpo → rodapé).\n"
    "- Use Markdown leve quando ajudar a estrutura: # pra títulos, "
    "listas com `- `, tabelas com pipes `|`.\n"
    "- Se não há texto legível, responda exatamente: [SEM TEXTO]\n"
    "- Se o texto está em outro idioma, transcreva no idioma original."
)


class OCRError(RuntimeError):
    """Falha no pipeline OCR (Vision LLM down, pdf2image quebrou, etc)."""


def _resize_if_needed(image_bytes: bytes, mime_type: str) -> tuple[bytes, str]:
    """Reduz largura se exceder MAX_IMAGE_WIDTH_PX. Mantém mime original."""
    from PIL import Image  # lazy import — só carrega quando OCR é usado

    try:
        img = Image.open(io.BytesIO(image_bytes))
    except Exception as e:
        raise OCRError(f"imagem inválida: {e}") from e

    if img.width <= MAX_IMAGE_WIDTH_PX:
        return image_bytes, mime_type

    ratio = MAX_IMAGE_WIDTH_PX / img.width
    new_size = (MAX_IMAGE_WIDTH_PX, int(img.height * ratio))
    resized = img.resize(new_size, Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    # Converte pra PNG por consistência (pdf2image retorna PIL sem mime canônico)
    if img.mode in ("RGBA", "LA"):
        resized.save(buf, format="PNG")
        return buf.getvalue(), "image/png"
    resized = resized.convert("RGB")
    resized.save(buf, format="JPEG", quality=85)
    return buf.getvalue(), "image/jpeg"


async def ocr_image_bytes(
    image_bytes: bytes,
    mime_type: str = "image/png",
    *,
    model: str | None = None,
) -> str:
    """Transcreve texto da imagem via OpenRouter Vision.

    Retorna string vazia quando o LLM detecta `[SEM TEXTO]`.
    """
    api_key = settings.openrouter_api_key
    if not api_key:
        raise OCRError("OPENROUTER_API_KEY não configurada")

    image_bytes, mime_type = _resize_if_needed(image_bytes, mime_type)
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")

    messages = [
        {"role": "system", "content": OCR_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Transcreva o texto desta imagem."},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{image_b64}"},
                },
            ],
        },
    ]

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                f"{settings.openrouter_base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key.get_secret_value()}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model or settings.openrouter_midia_model,
                    "messages": messages,
                    "temperature": 0.0,
                },
                timeout=60.0,
            )
            response.raise_for_status()
        except httpx.HTTPError as e:
            raise OCRError(f"OpenRouter OCR falhou: {e}") from e

    content = response.json()["choices"][0]["message"].get("content") or ""
    if isinstance(content, list):
        # Alguns modelos devolvem array de blocos
        content = "\n".join(
            str(item.get("text", ""))
            for item in content
            if isinstance(item, dict) and item.get("type") == "text"
        )
    text = str(content).strip()
    if text == "[SEM TEXTO]":
        return ""
    return text


async def ocr_pdf_pages(
    pdf_bytes: bytes,
    *,
    max_pages: int = MAX_PDF_PAGES,
    dpi: int = PDF_RASTERIZE_DPI,
    model: str | None = None,
) -> str:
    """Aplica OCR em cada página do PDF, junta com `\\n\\n` entre páginas.

    Hard-limita em `max_pages` pra controlar custo. PDFs maiores geram
    `OCRError` — admin deve dividir.
    """
    from pdf2image import convert_from_bytes  # lazy import (poppler dep)

    try:
        pages = convert_from_bytes(pdf_bytes, dpi=dpi, fmt="png")
    except Exception as e:
        raise OCRError(f"pdf2image falhou: {e}") from e

    if len(pages) > max_pages:
        raise OCRError(
            f"PDF tem {len(pages)} páginas — máximo é {max_pages}. "
            "Divida o arquivo antes de subir."
        )

    transcripts: list[str] = []
    for i, page_img in enumerate(pages):
        buf = io.BytesIO()
        page_img.save(buf, format="PNG")
        try:
            text = await ocr_image_bytes(
                buf.getvalue(), mime_type="image/png", model=model
            )
        except OCRError as e:
            logger.warning("ocr_page_failed", page=i, error=str(e))
            continue
        if text:
            transcripts.append(text)
    logger.info(
        "ocr_pdf_done",
        pages=len(pages),
        transcribed_pages=len(transcripts),
        total_chars=sum(len(t) for t in transcripts),
    )
    return "\n\n".join(transcripts)
