#!/usr/bin/env python3
"""Extrai texto, HTML e respostas de API do painel Chatvolt.

Complementa a captura de imagem. Screenshot mostra densidade e ergonomia;
isto aqui mostra *conteúdo* — e, diferente de PNG, dá diff.

Para cada rota grava em `chatvolt-dom/`:

    <slug>.txt        innerText da página — limpo, poucos KB, diffável
    <slug>.html       DOM renderizado — use para atributo (disabled, PRO, aria)
    <slug>.api.json   respostas XHR em JSON que a página buscou

O .txt é o artefato de maior valor por byte: rodar duas coletas e comparar
mostra funcionalidade nova antes de qualquer anúncio.

    python capture_chatvolt_local.py --so-sessao   # uma vez
    python extrair_chatvolt.py

Opções:
    --out DIR     pasta de saída (padrão: chatvolt-dom)
    --rota R      limita a estas rotas (repetível; use PowerShell, não Git Bash)
    --sem-html    pula o .html, que é o arquivo grande e mais ruidoso
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    sys.exit("Playwright não instalado.\n\n    pip install playwright\n")

BASE = "https://app.chatvolt.ai"
LOCALES = ("pt-BR", "en-US", "es-ES")

ROTAS = [
    "/agents",
    "/datastores",
    "/logs",
    "/crm",
    "/dispatches",
    "/artifacts",
    "/artifact-categories",
    "/contacts",
    "/voltapi",
    "/analytics",
    "/custom-dashboard",
    "/forms",
    "/apps",
    "/onboarding",
    "/settings/billing",
    "/settings/api-keys",
    "/settings/llm-keys",
    "/settings/organization",
]


def _slug(rota: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", rota.strip("/").lower()) or "home"


def _sem_locale(caminho: str) -> str:
    for loc in LOCALES:
        if caminho.startswith(f"/{loc}/") or caminho == f"/{loc}":
            return caminho[len(loc) + 1 :] or "/"
    return caminho


async def executar(args) -> int:
    storage = Path("storage_state.json")
    if not storage.exists():
        print("ERRO: storage_state.json não existe.")
        print("Rode antes:  python capture_chatvolt_local.py --so-sessao")
        return 1

    destino = Path(args.out)
    destino.mkdir(parents=True, exist_ok=True)
    rotas = [r for r in ROTAS if not args.rota or r in args.rota]
    if not rotas:
        print(f"Nenhuma rota casou com {args.rota}.")
        print("Dica: no Git Bash, '/logs' vira caminho do Windows. Use PowerShell.")
        return 1

    resumo: list[dict] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, channel="chromium")
        ctx = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            locale="pt-BR",
            storage_state=str(storage),
        )
        ctx.on("dialog", lambda d: asyncio.ensure_future(d.dismiss()))
        page = await ctx.new_page()

        capturado: list[dict] = []
        # O handler é assíncrono: ler o corpo demora e pode terminar depois de
        # a rota seguinte já ter limpado a lista. Sem esperar as tarefas
        # pendentes antes de gravar, a captura some em silêncio — e arquivo
        # ausente parece "tela sem API" em vez de bug. Daí o rastreio.
        pendentes: set[asyncio.Task] = set()

        async def _ler(resp) -> None:
            try:
                corpo = await resp.json()
            except Exception:  # noqa: BLE001 — corpo ilegível/consumido
                return
            capturado.append(
                {
                    "url": resp.url.replace(BASE, ""),
                    "status": resp.status,
                    "body": corpo,
                }
            )

        def _resposta(resp):
            """Guarda só JSON de XHR do próprio app — o resto é ruído."""
            if not resp.url.startswith(BASE):
                return
            if "json" not in (resp.headers or {}).get("content-type", "").lower():
                return
            tarefa = asyncio.ensure_future(_ler(resp))
            pendentes.add(tarefa)
            tarefa.add_done_callback(pendentes.discard)

        async def _drenar() -> None:
            """Espera os corpos em voo antes de gravar."""
            for _ in range(10):
                if not pendentes:
                    return
                await asyncio.gather(*list(pendentes), return_exceptions=True)
            if pendentes:
                print(f"   ⚠ {len(pendentes)} respostas não drenaram", flush=True)

        page.on("response", _resposta)

        for rota in rotas:
            slug = _slug(rota)
            capturado.clear()
            print(f"\n→ {rota}", flush=True)
            item: dict = {"rota": rota}
            try:
                await page.goto(
                    f"{BASE}{rota}", wait_until="networkidle", timeout=45_000
                )
            except Exception as exc:  # noqa: BLE001
                print(f"   ✗ {type(exc).__name__}: {str(exc)[:100]}", flush=True)
                item["erro"] = type(exc).__name__
                resumo.append(item)
                continue

            await page.wait_for_timeout(4500)
            await _drenar()
            final = _sem_locale(page.url.replace(BASE, "").split("?")[0])
            if final.rstrip("/") != rota.rstrip("/"):
                item["redirecionou_para"] = final
                print(f"   ⚠ redirecionou → {final}", flush=True)

            texto = await page.evaluate("document.body.innerText")
            arq = destino / f"{slug}.txt"
            arq.write_text(texto, encoding="utf-8")
            print(f"   · {arq.name}  ({len(texto) // 1024 or 1} KB)", flush=True)
            item["txt_chars"] = len(texto)

            if not args.sem_html:
                html = await page.content()
                arq = destino / f"{slug}.html"
                arq.write_text(html, encoding="utf-8")
                print(f"   · {arq.name}  ({len(html) // 1024} KB)", flush=True)
                item["html_chars"] = len(html)

            if capturado:
                arq = destino / f"{slug}.api.json"
                arq.write_text(
                    json.dumps(capturado, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                print(
                    f"   · {arq.name}  ({len(capturado)} respostas)", flush=True
                )
                item["api_respostas"] = [c["url"] for c in capturado]
            else:
                # Silêncio aqui é suspeito, não informativo: toda tela do painel
                # busca dados. Grita para não virar "essa tela não usa API".
                print("   ⚠ nenhuma resposta JSON capturada — suspeito", flush=True)
                item["api_respostas"] = []

            resumo.append(item)

        await ctx.close()
        await browser.close()

    (destino / "extracao.json").write_text(
        json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n{'=' * 62}")
    print(f"{len(resumo)} rotas em {destino.resolve()}")
    print("\nPara comparar duas coletas:")
    print("  git diff --no-index coleta-anterior/ chatvolt-dom/")
    return 0


def main() -> int:
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="chatvolt-dom", help="pasta de saída")
    ap.add_argument("--rota", action="append", help="limita a estas rotas")
    ap.add_argument("--sem-html", action="store_true", help="pula o .html")
    return asyncio.run(executar(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
