#!/usr/bin/env python3
"""Captura telas de plataformas concorrentes para o benchmark funcional.

Roda na VPS com o Chromium do Playwright (já em cache). Como a VPS não
compartilha sessão com o navegador do operador, telas autenticadas exigem
`--storage` apontando para um `storage_state.json` exportado do browser logado
(ver `docs/benchmark/README.md`).

Uso:
    # páginas públicas (sem login)
    uv run python scripts/capture_benchmark_screens.py --set publico

    # painel autenticado, com estado de sessão exportado
    uv run python scripts/capture_benchmark_screens.py --set painel \
        --storage /caminho/storage_state.json

    # gravar o storage_state fazendo login headful (precisa de display/VNC)
    uv run python scripts/capture_benchmark_screens.py --login
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

RAIZ = Path(__file__).resolve().parents[1]
DESTINO = RAIZ / "docs/benchmark/plataformas/chatvolt/img"

# Viewport de desktop padrão do benchmark. Mobile usa 390x844 (iPhone 14).
VIEWPORT = {"width": 1440, "height": 900}
VIEWPORT_MOBILE = {"width": 390, "height": 844}

# (slug, url, full_page, espera_extra_ms)
TELAS: dict[str, list[tuple[str, str, bool, int]]] = {
    "publico": [
        ("landing", "https://www.chatvolt.ai/", True, 2500),
        ("pricing", "https://www.chatvolt.ai/pricing", True, 2500),
        ("login", "https://app.chatvolt.ai/auth/signin", False, 3000),
    ],
    # Rotas reais, extraídas do _buildManifest.js do app — não chutadas.
    # A lista canônica (com o que observar em cada tela) vive em
    # `scripts/capture_chatvolt_local.py`, que é o script que o operador roda.
    "painel": [
        (slug, f"https://app.chatvolt.ai{caminho}", False, espera)
        for slug, caminho, espera in [
            ("agents-lista", "/agents", 4000),
            ("agent-editor", "/agents/create", 4000),
            ("datastores", "/datastores", 4000),
            ("inbox", "/logs", 6000),
            ("crm", "/crm", 5000),
            ("dispatches", "/dispatches", 4000),
            ("artifacts", "/artifacts", 4000),
            ("artifact-categories", "/artifact-categories", 3000),
            ("contacts", "/contacts", 4000),
            ("voltapi", "/voltapi", 4000),
            ("analytics", "/analytics", 6000),
            ("custom-dashboard", "/custom-dashboard", 5000),
            ("forms", "/forms", 4000),
            ("apps", "/apps", 4000),
            ("partner-set", "/partner-set", 4000),
            ("onboarding", "/onboarding", 4000),
            ("settings-billing", "/settings/billing", 4000),
            ("settings-api-keys", "/settings/api-keys", 3000),
            ("settings-llm-keys", "/settings/llm-keys", 3000),
            ("settings-organization", "/settings/organization", 4000),
        ]
    ],
}


async def _shot(
    page, slug: str, full_page: bool, espera: int, sufixo: str = ""
) -> None:
    await page.wait_for_timeout(espera)
    destino = DESTINO / f"chatvolt-{slug}{sufixo}.png"
    await page.screenshot(path=str(destino), full_page=full_page)
    tam = destino.stat().st_size // 1024
    print(f"  ✓ {destino.name}  ({tam} KB)")


def storage_de_cookie(
    valor: str, nome: str = "__Secure-next-auth.session-token"
) -> dict:
    """Monta um storage_state a partir do cookie de sessão colado pelo operador.

    O Chatvolt usa NextAuth — não existe login por senha, só magic link, código
    ou Google. Então a única forma de a VPS ver o painel é reaproveitar o cookie
    de uma sessão já autenticada no navegador do operador.
    """
    if "=" in valor and valor.split("=", 1)[0].strip().endswith("session-token"):
        nome, valor = (p.strip() for p in valor.split("=", 1))
    return {
        "cookies": [
            {
                "name": nome,
                "value": valor.strip(),
                "domain": ".chatvolt.ai",
                "path": "/",
                "httpOnly": True,
                "secure": True,
                "sameSite": "Lax",
                "expires": -1,
            }
        ],
        "origins": [],
    }


async def capturar(conjunto: str, storage: Path | None, mobile: bool) -> int:
    telas = TELAS[conjunto]
    DESTINO.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        # `channel="chromium"` força o build completo. O `headless_shell` que o
        # Playwright usa por padrão dá SIGSEGV neste host ARM/OEL8 — o chrome
        # completo roda normal. Não trocar sem testar em aarch64.
        browser = await pw.chromium.launch(
            headless=True,
            channel="chromium",
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        ctx_kwargs: dict = {
            "viewport": VIEWPORT_MOBILE if mobile else VIEWPORT,
            "device_scale_factor": 2,
            "locale": "pt-BR",
        }
        if storage:
            if not storage.exists():
                print(f"ERRO: storage_state não encontrado: {storage}", file=sys.stderr)
                return 1
            ctx_kwargs["storage_state"] = str(storage)

        ctx = await browser.new_context(**ctx_kwargs)
        page = await ctx.new_page()
        falhas = 0
        sufixo = "-mobile" if mobile else ""

        for slug, url, full_page, espera in telas:
            print(f"→ {slug}: {url}")
            try:
                await page.goto(url, wait_until="networkidle", timeout=45_000)
                await _shot(page, slug, full_page, espera, sufixo)
            except Exception as exc:  # noqa: BLE001 — captura é best-effort
                print(f"  ✗ falhou: {type(exc).__name__}: {exc}")
                falhas += 1

        await ctx.close()
        await browser.close()

    print(f"\n{len(telas) - falhas}/{len(telas)} capturadas em {DESTINO}")
    return 1 if falhas == len(telas) else 0


async def gravar_login(destino: Path) -> int:
    """Abre navegador headful para login manual e grava o storage_state."""
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        ctx = await browser.new_context(viewport=VIEWPORT, locale="pt-BR")
        page = await ctx.new_page()
        await page.goto("https://app.chatvolt.ai/auth/signin")
        print("Faça login na janela aberta e volte aqui.")
        input("Pressione ENTER quando o painel estiver carregado... ")
        await ctx.storage_state(path=str(destino))
        print(f"storage_state salvo em {destino}")
        await browser.close()
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--set", dest="conjunto", choices=sorted(TELAS), default="publico")
    ap.add_argument("--storage", type=Path, help="storage_state.json da sessão logada")
    ap.add_argument("--mobile", action="store_true", help="viewport 390x844")
    ap.add_argument(
        "--login", action="store_true", help="gravar storage_state (headful)"
    )
    ap.add_argument("--out", type=Path, default=Path("storage_state.json"))
    args = ap.parse_args()

    if args.login:
        return asyncio.run(gravar_login(args.out))
    return asyncio.run(capturar(args.conjunto, args.storage, args.mobile))


if __name__ == "__main__":
    raise SystemExit(main())
