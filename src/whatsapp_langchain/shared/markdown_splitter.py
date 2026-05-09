"""Markdown splitter por headers (Sprint S.2).

Divide um arquivo .md em múltiplas seções baseado em H1/H2/H3.
Cada seção vira um documento_conhecimento separado — melhor pra RAG
porque cada chunk fica no contexto da seção correta.

Sem dep externa — regex pura.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class MarkdownSection:
    titulo: str
    conteudo: str
    level: int  # 1=H1, 2=H2, 3=H3


_HEADER_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*$", re.MULTILINE)


def split_md_by_headers(
    text: str,
    *,
    max_level: int = 2,
    fallback_titulo: str = "Documento",
) -> list[MarkdownSection]:
    """Splita markdown em seções por H1/H2 (default).

    Args:
        text: conteúdo markdown completo
        max_level: 1=só H1, 2=H1+H2 (default), 3=H1+H2+H3
        fallback_titulo: título do prefixo quando texto começa SEM header

    Retorna lista de MarkdownSection. Se o texto não tem nenhum header,
    retorna 1 seção com fallback_titulo + conteúdo inteiro.
    """
    if not text or not text.strip():
        return []

    # Coleta posições dos headers até max_level
    headers: list[tuple[int, int, str]] = []  # (start_pos, level, titulo)
    for m in _HEADER_RE.finditer(text):
        level = len(m.group(1))
        if level > max_level:
            continue
        titulo = m.group(2).strip()
        headers.append((m.start(), level, titulo))

    if not headers:
        # Sem headers — 1 seção com texto inteiro
        return [
            MarkdownSection(
                titulo=fallback_titulo,
                conteudo=text.strip(),
                level=1,
            )
        ]

    sections: list[MarkdownSection] = []

    # Conteúdo ANTES do primeiro header → vira intro com fallback_titulo
    if headers[0][0] > 0:
        intro = text[: headers[0][0]].strip()
        if intro:
            sections.append(
                MarkdownSection(
                    titulo=f"{fallback_titulo} (Introdução)",
                    conteudo=intro,
                    level=1,
                )
            )

    # Pra cada header, conteúdo = texto até o próximo header (ou fim)
    for i, (start, level, titulo) in enumerate(headers):
        # Pula linha do header em si
        line_end = text.find("\n", start)
        body_start = line_end + 1 if line_end != -1 else len(text)
        body_end = headers[i + 1][0] if i + 1 < len(headers) else len(text)
        body = text[body_start:body_end].strip()
        if not body:
            # Header sem conteúdo (só sub-headers depois) — pula
            continue
        sections.append(
            MarkdownSection(titulo=titulo[:200], conteudo=body, level=level)
        )

    return sections
