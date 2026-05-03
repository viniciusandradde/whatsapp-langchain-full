"""Chunker simples para a base de conhecimento — M5.c.1.

Estratégia: divide texto em chunks ~`max_chars` priorizando quebras
"naturais" (parágrafo > sentença > caractere). Aplica `overlap` entre
chunks pra preservar contexto que cruza fronteiras.

Não tenta tokenizar — caracteres são proxy razoável pra português e
funcionam sem dependência adicional. Se virar gargalo de qualidade,
trocar por tiktoken depois.
"""

from __future__ import annotations

import re

# Regex captura quebras de parágrafo (linha em branco) ou de sentença
# (.,!,? seguido de espaço). Não é perfeito mas é robusto pra texto
# corrido em pt-BR, FAQ e listas.
_PARAGRAPH_RE = re.compile(r"\n\s*\n+")
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ])")


DEFAULT_MAX_CHARS = 800
DEFAULT_OVERLAP = 100


def split_text(
    text: str,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap: int = DEFAULT_OVERLAP,
) -> list[str]:
    """Divide `text` em chunks de até `max_chars` com `overlap` entre eles.

    Algoritmo:
    1. Se texto ≤ max_chars, retorna como chunk único.
    2. Tenta quebrar em parágrafos. Agrupa parágrafos consecutivos enquanto
       cabem em max_chars; chunk fecha quando o próximo parágrafo
       estouraria o limite.
    3. Parágrafos individuais maiores que max_chars são quebrados em
       sentenças usando o mesmo critério.
    4. Sentenças individuais maiores que max_chars são cortadas na boa.
    5. Aplica overlap = últimos `overlap` chars do chunk anterior são
       prependidos ao próximo (preserva contexto).

    Strings vazias retornam lista vazia.
    """
    text = text.strip()
    if not text:
        return []

    if len(text) <= max_chars:
        return [text]

    paragraphs = [p.strip() for p in _PARAGRAPH_RE.split(text) if p.strip()]
    raw_chunks: list[str] = []
    buffer = ""
    for para in paragraphs:
        if len(para) > max_chars:
            # Parágrafo grande — flush buffer e quebra em sentenças.
            if buffer:
                raw_chunks.append(buffer)
                buffer = ""
            raw_chunks.extend(_split_long(para, max_chars=max_chars))
            continue

        candidate = f"{buffer}\n\n{para}".strip() if buffer else para
        if len(candidate) <= max_chars:
            buffer = candidate
        else:
            raw_chunks.append(buffer)
            buffer = para

    if buffer:
        raw_chunks.append(buffer)

    if overlap <= 0 or len(raw_chunks) <= 1:
        return raw_chunks
    return _apply_overlap(raw_chunks, overlap=overlap)


def _split_long(text: str, *, max_chars: int) -> list[str]:
    """Parágrafo > max_chars: tenta sentença, depois corte fixo."""
    sentences = _SENTENCE_RE.split(text)
    out: list[str] = []
    buffer = ""
    for sent in sentences:
        sent = sent.strip()
        if not sent:
            continue
        if len(sent) > max_chars:
            if buffer:
                out.append(buffer)
                buffer = ""
            # Sentença gigante (URL longa, base64, etc) — corta na régua.
            for i in range(0, len(sent), max_chars):
                out.append(sent[i : i + max_chars])
            continue

        candidate = f"{buffer} {sent}".strip() if buffer else sent
        if len(candidate) <= max_chars:
            buffer = candidate
        else:
            out.append(buffer)
            buffer = sent
    if buffer:
        out.append(buffer)
    return out


def _apply_overlap(chunks: list[str], *, overlap: int) -> list[str]:
    """Prepend dos últimos `overlap` chars do chunk anterior em cada um."""
    if overlap <= 0:
        return chunks
    out: list[str] = [chunks[0]]
    for prev, curr in zip(chunks, chunks[1:]):
        prefix = prev[-overlap:].lstrip()
        # Evita duplicar literalmente — se prefix já é início de curr.
        merged = f"{prefix} {curr}" if not curr.startswith(prefix) else curr
        out.append(merged)
    return out
