#!/usr/bin/env python3
"""Mapeia a estrutura de frontend do painel Chatvolt.

Escopo deliberado: **estrutura, não código-fonte**. Baixa o CSS (folha de
estilo é o sistema de design, e é o que interessa comparar) e cataloga os
bundles JS por rota, tamanho e biblioteca detectada — sem espelhar o
JavaScript compilado, que é código proprietário e não ajuda um benchmark
funcional.

Não requer login: os assets do Next.js são servidos publicamente. O
`storage_state.json` não é usado aqui.

Gera em `chatvolt-front/`:

    build.json          buildId, contagem de rotas e chunks
    rotas-chunks.json   quais chunks cada rota carrega
    chunks.csv          nome, tamanho, tipo de cada chunk
    css/*.css           folhas de estilo baixadas
    design-tokens.md    cores, fontes e medidas extraídas do CSS
    bibliotecas.md      dependências detectadas por assinatura

    python inventario_frontend.py
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.request import Request, urlopen

BASE = "https://app.chatvolt.ai"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) benchmark-inventory"

# Assinaturas de biblioteca em bundle minificado. Cada entrada é (rótulo,
# regex): strings que sobrevivem à minificação — nomes de erro, chaves de
# config, mensagens de aviso.
ASSINATURAS = [
    ("React", r"react\.production\.min|__REACT_DEVTOOLS|useLayoutEffect"),
    ("Next.js", r"__NEXT_DATA__|next/dist|__nextDataPromise"),
    ("Tailwind", r"--tw-|tw-ring-offset|tailwind"),
    ("MUI / Joy UI", r"@mui|MuiBox|JoyButton|joy-ui"),
    ("Emotion", r"@emotion|__emotion|css-in-js"),
    ("SWR", r"swr|useSWR|revalidateOnFocus"),
    ("React Hook Form", r"react-hook-form|useFormContext|handleSubmit"),
    ("Zod", r"ZodError|invalid_type|zod"),
    ("NextAuth", r"next-auth|CredentialsSignin|__Secure-next-auth"),
    ("Stripe", r"stripe\.com|Stripe\(|pk_live|pk_test"),
    ("Sentry", r"sentry|captureException|@sentry"),
    ("PostHog / analytics", r"posthog|mixpanel|amplitude|gtag"),
    ("Crisp", r"crisp|\$crisp"),
    ("Recharts / D3", r"recharts|d3-scale|d3-shape"),
    ("dnd-kit / react-beautiful-dnd", r"dnd-kit|react-beautiful-dnd"),
    ("Monaco / CodeMirror", r"monaco-editor|codemirror|@codemirror"),
    ("i18next", r"i18next|react-i18next"),
    ("Prisma (tipos no cliente)", r"PrismaClient|prisma"),
]


def _baixar(url: str, binario: bool = False):
    req = Request(url, headers={"User-Agent": UA})
    with urlopen(req, timeout=45) as r:  # noqa: S310 — host fixo, https
        dados = r.read()
    return dados if binario else dados.decode("utf-8", "replace")


def _build_id() -> str:
    html = _baixar(f"{BASE}/auth/signin")
    m = re.search(r'"buildId":"([^"]+)"', html)
    if not m:
        sys.exit("Não achei o buildId em /auth/signin — o app pode ter mudado.")
    return m.group(1)


def _manifest(build: str) -> dict[str, list[str]]:
    """Rotas → chunks, a partir do _buildManifest.js.

    O manifesto é JS com escopo de função e parâmetros de uma letra; em vez de
    interpretar, extrai os pares rota/arquivo por regex sobre o trecho final.
    """
    js = _baixar(f"{BASE}/_next/static/{build}/_buildManifest.js")
    rotas: dict[str, list[str]] = {}
    for m in re.finditer(r'"(/[^"]*)":\[([^\]]*)\]', js):
        rota, corpo = m.group(1), m.group(2)
        arquivos = re.findall(r'"([^"]+\.(?:js|css))"', corpo)
        if arquivos:
            rotas[rota] = arquivos
    return rotas


def _tokens(css: str) -> str:
    cores = Counter(re.findall(r"#[0-9a-fA-F]{3,8}\b", css))
    rgb = Counter(re.findall(r"rgba?\([^)]+\)", css))
    fontes = Counter(re.findall(r"font-family:\s*([^;}]+)", css))
    raios = Counter(re.findall(r"border-radius:\s*([^;}]+)", css))
    vars_ = Counter(re.findall(r"(--[a-zA-Z0-9-]+)\s*:", css))

    def bloco(titulo, contador, n=25):
        linhas = [f"### {titulo}  ({len(contador)} distintos)", ""]
        for v, c in contador.most_common(n):
            linhas.append(f"- `{str(v).strip()[:70]}` — {c}×")
        return "\n".join(linhas) + "\n"

    return "\n".join(
        [
            "# Design tokens extraídos do CSS\n",
            "Frequência indica o que é sistema e o que é exceção.\n",
            bloco("Cores hex", cores),
            bloco("Cores rgb/rgba", rgb, 15),
            bloco("Famílias de fonte", fontes, 10),
            bloco("Raios de borda", raios, 12),
            bloco("Custom properties", vars_, 40),
        ]
    )


async def executar(args) -> int:
    destino = Path(args.out)
    (destino / "css").mkdir(parents=True, exist_ok=True)

    build = _build_id()
    print(f"buildId: {build}", flush=True)

    rotas = _manifest(build)
    todos = sorted({a for lista in rotas.values() for a in lista})
    css_files = [a for a in todos if a.endswith(".css")]
    js_files = [a for a in todos if a.endswith(".js")]
    print(f"{len(rotas)} rotas · {len(js_files)} chunks JS · {len(css_files)} CSS", flush=True)

    (destino / "rotas-chunks.json").write_text(
        json.dumps(rotas, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # --- CSS: baixa e extrai tokens -----------------------------------------
    css_total = ""
    for arq in css_files:
        url = f"{BASE}/_next/static/{arq}" if not arq.startswith("static/") else f"{BASE}/_next/{arq}"
        try:
            texto = _baixar(url)
        except Exception as exc:  # noqa: BLE001
            print(f"  ✗ css {arq}: {type(exc).__name__}", flush=True)
            continue
        nome = arq.replace("/", "_")
        (destino / "css" / nome).write_text(texto, encoding="utf-8")
        css_total += texto
        print(f"  · css/{nome}  ({len(texto) // 1024} KB)", flush=True)

    if css_total:
        (destino / "design-tokens.md").write_text(_tokens(css_total), encoding="utf-8")
        print(f"  · design-tokens.md  (de {len(css_total) // 1024} KB de CSS)", flush=True)

    # --- JS: catálogo, com amostragem para detectar biblioteca --------------
    linhas = []
    achados: dict[str, set[str]] = {}
    alvo = js_files if args.todos_js else js_files[: args.amostra]
    print(f"\nAnalisando {len(alvo)} de {len(js_files)} chunks JS…", flush=True)

    for arq in alvo:
        url = f"{BASE}/_next/static/{arq}" if not arq.startswith("static/") else f"{BASE}/_next/{arq}"
        try:
            dados = _baixar(url, binario=True)
        except Exception as exc:  # noqa: BLE001
            print(f"  ✗ {arq}: {type(exc).__name__}", flush=True)
            continue
        texto = dados.decode("utf-8", "replace")
        for rotulo, padrao in ASSINATURAS:
            if re.search(padrao, texto, re.I):
                achados.setdefault(rotulo, set()).add(arq)
        linhas.append({"arquivo": arq, "bytes": len(dados)})

    if linhas:
        with (destino / "chunks.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["arquivo", "bytes"])
            w.writeheader()
            w.writerows(sorted(linhas, key=lambda r: -r["bytes"]))
        print(f"  · chunks.csv  ({len(linhas)} chunks)", flush=True)

    md = ["# Bibliotecas detectadas no bundle\n"]
    md.append(
        f"Por assinatura em {len(alvo)} de {len(js_files)} chunks. "
        "Ausência aqui não prova ausência no produto — só que a amostra não "
        "cobriu o chunk que a contém.\n"
    )
    for rotulo, arquivos in sorted(achados.items(), key=lambda kv: -len(kv[1])):
        md.append(f"- **{rotulo}** — em {len(arquivos)} chunk(s)")
    if not achados:
        md.append("_Nenhuma assinatura casou._")
    (destino / "bibliotecas.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print(f"  · bibliotecas.md  ({len(achados)} detectadas)", flush=True)

    (destino / "build.json").write_text(
        json.dumps(
            {
                "buildId": build,
                "rotas": len(rotas),
                "chunks_js": len(js_files),
                "chunks_css": len(css_files),
                "js_analisados": len(alvo),
                "bibliotecas": sorted(achados),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"\n{'=' * 62}\nInventário em {destino.resolve()}")
    return 0


def main() -> int:
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="chatvolt-front", help="pasta de saída")
    ap.add_argument(
        "--amostra", type=int, default=40, help="quantos chunks JS inspecionar"
    )
    ap.add_argument(
        "--todos-js", action="store_true", help="inspeciona todos os chunks"
    )
    return asyncio.run(executar(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
