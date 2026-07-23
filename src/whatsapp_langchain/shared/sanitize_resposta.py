"""Sanitização da resposta do agente antes de enviar ao cliente.

Modelos (especialmente os mais fracos) às vezes VAZAM o raciocínio interno
na resposta — blocos tipo `<raciocinio_interno>...</raciocinio_interno>`
instruídos como "silenciosos" no prompt acabam impressos e enviados ao
WhatsApp do cliente (incidente real: agente do Prof. Luis Fernando,
2026-07-23). Este módulo é a defesa da PLATAFORMA, independente de prompt:
remove blocos de tag estilo XML e tags soltas do texto final.
"""

from __future__ import annotations

import re

import structlog

logger = structlog.get_logger()

# Bloco completo <tag>...</tag> (tag minúscula/underscore, 3-40 chars) —
# cobre raciocinio_interno, triagem, escalonamento, thinking, reflection etc.
_BLOCO_TAG_RE = re.compile(
    r"<([a-z_]{3,40})>.*?</\1>",
    re.DOTALL | re.IGNORECASE,
)
# Tag solta (abertura sem fechamento ou vice-versa) que tenha sobrado.
_TAG_SOLTA_RE = re.compile(r"</?[a-z_]{3,40}>", re.IGNORECASE)
# Abertura sem fechamento: da tag até o fim (modelo cortou no meio do bloco).
_BLOCO_ABERTO_RE = re.compile(r"<([a-z_]{3,40})>(?:(?!</\1>).)*$", re.DOTALL)


def sanitize_resposta_agente(texto: str) -> str:
    """Remove blocos de raciocínio/tags de controle da resposta do agente.

    Conservador: se a limpeza zerar o texto (ex.: modelo mandou SÓ o bloco),
    mantém o conteúdo sem as tags em vez de enviar vazio, e loga o evento
    pra diagnóstico de prompt/modelo.
    """
    if not texto or "<" not in texto:
        return texto

    limpo = _BLOCO_TAG_RE.sub("", texto)
    limpo = _BLOCO_ABERTO_RE.sub("", limpo)
    limpo = _TAG_SOLTA_RE.sub("", limpo)
    limpo = re.sub(r"\n{3,}", "\n\n", limpo).strip()

    if limpo != texto.strip():
        logger.warning(
            "resposta_agente_sanitizada",
            original_chars=len(texto),
            final_chars=len(limpo),
        )

    if not limpo:
        # Modelo só mandou raciocínio: preserva o conteúdo sem as tags
        # (melhor que silêncio; o warning acima aponta o prompt a corrigir).
        fallback = _TAG_SOLTA_RE.sub("", texto).strip()
        return fallback or texto

    return limpo
