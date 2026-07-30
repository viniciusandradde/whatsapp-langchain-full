#!/usr/bin/env python3
"""Baixa o CSS do painel e extrai os design tokens.

Separado do `inventario_frontend.py` porque as folhas de estilo NÃO estão no
`_buildManifest.js` — o Next.js as referencia por `<link>` no HTML. A lista de
alvos sai dos HTMLs já salvos em `chatvolt-dom/`, então rode a extração antes.

    python extrair_chatvolt.py      # gera chatvolt-dom/*.html
    python baixar_css.py
"""

from __future__ import annotations

import glob
import importlib.util
import re
import sys
from pathlib import Path

BASE = "https://app.chatvolt.ai"
DESTINO = Path("chatvolt-front")


def _carregar_inventario():
    spec = importlib.util.spec_from_file_location("inv", "inventario_frontend.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _alvos() -> list[str]:
    achados: set[str] = set()
    for arq in glob.glob("chatvolt-dom/*.html"):
        html = Path(arq).read_text(encoding="utf-8")
        achados.update(re.findall(r'href="(/_next/[^"]+\.css)"', html))
    return sorted(achados)


def main() -> int:
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    alvos = _alvos()
    if not alvos:
        print("Nenhum CSS referenciado nos HTMLs de chatvolt-dom/.")
        print("Rode antes:  python extrair_chatvolt.py")
        return 1

    inv = _carregar_inventario()
    (DESTINO / "css").mkdir(parents=True, exist_ok=True)
    total = ""
    for caminho in alvos:
        try:
            texto = inv._baixar(BASE + caminho)
        except Exception as exc:  # noqa: BLE001
            print(f"  ✗ {caminho}: {type(exc).__name__}")
            continue
        nome = caminho.split("/")[-1]
        (DESTINO / "css" / nome).write_text(texto, encoding="utf-8")
        total += texto
        print(f"  · css/{nome}  ({len(texto) // 1024} KB)")

    if total:
        (DESTINO / "design-tokens.md").write_text(inv._tokens(total), encoding="utf-8")
        print(f"  · design-tokens.md  (de {len(total) // 1024} KB de CSS)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
