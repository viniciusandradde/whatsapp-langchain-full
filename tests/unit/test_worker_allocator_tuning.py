"""Regressão: tuning do alocador no Dockerfile.worker.

Incidente 2026-07-26: o worker subia em ~100MB e estacionava em ~435MB depois
de ~40h, encostando nos 85% do limite de 512M e vazando pro swap.

O diagnóstico descartou vazamento de referência (o loop ocioso projeta 11MB
em 40h; compilar o grafo custa 0.10MB; o RSS estaciona em vez de crescer sem
parar; `gc.collect()` não devolve nada, `malloc_trim()` devolve). A causa é o
mmap threshold DINÂMICO do glibc: o worker aloca blocos únicos de vários MB
ao pré-processar mídia (base64 pro OpenRouter multimodal), o glibc sobe o
limiar sozinho a cada bloco liberado, e a partir daí serve essas alocações
pela heap — que não volta pro SO.

Medido com 22 mídias de 6MB: +15.4MB retidos com o default contra +1.5MB com
o limiar fixo.

Este teste tranca a config. Sem ele, alguém "limpa" o ENV do Dockerfile e o
RSS volta a inchar meses depois, sem ninguém ligar uma coisa à outra.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCKERFILE = REPO_ROOT / "Dockerfile.worker"


@pytest.fixture(scope="module")
def dockerfile_texto() -> str:
    if not DOCKERFILE.is_file():
        pytest.skip(f"Dockerfile.worker não encontrado em {DOCKERFILE}")
    return DOCKERFILE.read_text(encoding="utf-8")


def test_mmap_threshold_fixo(dockerfile_texto: str) -> None:
    """O limiar precisa estar FIXO — é o que impede o ratchet de RSS."""
    match = re.search(r"MALLOC_MMAP_THRESHOLD_=(\d+)", dockerfile_texto)
    assert match, (
        "MALLOC_MMAP_THRESHOLD_ sumiu do Dockerfile.worker. Sem ele o glibc "
        "volta a subir o limiar sozinho e o RSS do worker incha até a marca "
        "d'água (~435MB medidos no incidente 2026-07-26)."
    )

    valor = int(match.group(1))
    # Acima de ~1MB o limiar deixa de cobrir o payload típico de mídia
    # (áudio/imagem em base64), que é justamente o que causava o ratchet.
    assert 65536 <= valor <= 1048576, (
        f"MALLOC_MMAP_THRESHOLD_={valor} fora da faixa útil. Muito baixo "
        "castiga com syscall; muito alto não cobre o base64 de mídia."
    )


def test_arena_max_limitado(dockerfile_texto: str) -> None:
    """Arenas por thread multiplicam o RSS retido em container."""
    match = re.search(r"MALLOC_ARENA_MAX=(\d+)", dockerfile_texto)
    assert match, "MALLOC_ARENA_MAX sumiu do Dockerfile.worker"

    valor = int(match.group(1))
    assert 1 <= valor <= 4, (
        f"MALLOC_ARENA_MAX={valor} alto demais para container com limite de "
        "memória — cada arena retém memória livre própria."
    )


def test_motivo_documentado_no_dockerfile(dockerfile_texto: str) -> None:
    """Config de alocador sem o porquê vira lixo que ninguém ousa remover.

    O comentário é o que liga o ENV ao incidente; sem ele o próximo dev não
    tem como saber se ainda é necessário.
    """
    assert "MALLOC_MMAP_THRESHOLD_" in dockerfile_texto
    contexto = dockerfile_texto.split("MALLOC_MMAP_THRESHOLD_")[0]
    assert "mídia" in contexto or "midia" in contexto, (
        "Falta o comentário explicando que o gatilho é o pré-processamento "
        "de mídia (base64), não vazamento de referência."
    )
