#!/usr/bin/env python3
"""Captura as telas do painel Chatvolt a partir do PC do operador.

Por que existe: o Chatvolt usa NextAuth — **não há login por senha**, só magic
link por e-mail, código ou Google. A VPS não tem como se autenticar sozinha.
Então o login acontece uma vez aqui, numa janela real, e o script segue
capturando tudo automaticamente.

Autocontido de propósito: copie SÓ este arquivo para o seu PC, não precisa do
repositório.

--------------------------------------------------------------------------
COMO USAR
--------------------------------------------------------------------------

1) Instalar (uma vez):

       pip install playwright
       playwright install chromium

2) Rodar:

       python capture_chatvolt_local.py

   Abre uma janela do Chromium na tela de login. Entre com o seu método
   habitual (magic link, código ou Google). Assim que o painel carregar,
   volte ao terminal e aperte ENTER.

   O script captura todas as telas em `chatvolt-img/` e grava
   `storage_state.json` (a sessão), para as próximas rodadas não pedirem
   login de novo.

3) Rodadas seguintes (sem login):

       python capture_chatvolt_local.py --reusar

4) Mandar o resultado para a VPS:

       # as imagens
       scp -r chatvolt-img/* opc@<vps>:/home/dev/projetos/whatsapp-langchain/docs/benchmark/plataformas/chatvolt/img/

       # OU só a sessão, e a VPS captura sozinha (arquivo pequeno)
       scp storage_state.json opc@<vps>:/tmp/

--------------------------------------------------------------------------
OPÇÕES
--------------------------------------------------------------------------

    --reusar        usa storage_state.json existente, não pede login
    --so-sessao     só faz login e grava storage_state.json, sem capturar
    --mobile        captura também em viewport de celular (390x844)
    --out DIR       pasta de saída (padrão: chatvolt-img)

--------------------------------------------------------------------------
PRIVACIDADE
--------------------------------------------------------------------------

As telas capturadas são da SUA conta e podem conter dados de clientes
(Inbox, contatos). Revise antes de commitar. O `storage_state.json` é
credencial de sessão — trate como senha e apague quando terminar.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    sys.exit(
        "Playwright não instalado.\n\n"
        "    pip install playwright\n"
        "    playwright install chromium\n"
    )

BASE = "https://app.chatvolt.ai"

# Rotas extraídas do _buildManifest.js do app (Next.js), não chutadas.
# Recuperar assim quando mudarem:
#   curl -s https://app.chatvolt.ai/auth/signin | grep -oE '"buildId":"[^"]+"'
#   curl -s https://app.chatvolt.ai/_next/static/<buildId>/_buildManifest.js
#
# (slug, caminho, full_page, espera_ms, o_que_observar)
TELAS: list[tuple[str, str, bool, int, str]] = [
    ("agents-lista", "/agents", False, 4000, "Densidade da lista, ações por agente"),
    (
        "agent-editor",
        "/agents/create",
        False,
        4000,
        "Abas do editor, ergonomia do prompt",
    ),
    (
        "datastores",
        "/datastores",
        False,
        4000,
        "Agrupamento de fontes e status de sync",
    ),
    ("inbox", "/logs", False, 6000, "Filtros, tags, frustration, painel do contato"),
    ("crm", "/crm", False, 5000, "Board kanban, cenários e etapas"),
    (
        "dispatches",
        "/dispatches",
        False,
        4000,
        "Abas Active/Scheduled/Completed/Listas",
    ),
    ("artifacts", "/artifacts", False, 4000, "Cadastro de produto e mídia"),
    (
        "artifact-categories",
        "/artifact-categories",
        False,
        3000,
        "Hierarquia de categorias",
    ),
    ("contacts", "/contacts", False, 4000, "Campos, variáveis, card CTWA, exportação"),
    ("voltapi", "/voltapi", False, 4000, "Editor JS e assistente de IA"),
    # Descobertos no manifest — não existem na documentação pública.
    (
        "analytics",
        "/analytics",
        False,
        6000,
        "Métricas, filtros e auditoria de créditos",
    ),
    (
        "custom-dashboard",
        "/custom-dashboard",
        False,
        5000,
        "Dashboard montável pelo cliente?",
    ),
    ("forms", "/forms", False, 4000, "O módulo que aparece só nas permissões"),
    ("apps", "/apps", False, 4000, "Marketplace/catálogo de integrações?"),
    ("partner-set", "/partner-set", False, 4000, "Programa de parceiro/revenda"),
    ("onboarding", "/onboarding", False, 4000, "Passos do primeiro acesso"),
    # Configuração e billing.
    (
        "settings-billing",
        "/settings/billing",
        False,
        4000,
        "Consumo de crédito em tempo real",
    ),
    (
        "settings-api-keys",
        "/settings/api-keys",
        False,
        3000,
        "Escopo e rotação de chave",
    ),
    (
        "settings-llm-keys",
        "/settings/llm-keys",
        False,
        3000,
        "BYOK: quais provedores aceita",
    ),
    (
        "settings-organization",
        "/settings/organization",
        False,
        4000,
        "Team e permissões por agente",
    ),
]

VIEWPORT = {"width": 1440, "height": 900}
VIEWPORT_MOBILE = {"width": 390, "height": 844}


async def _abrir(pw, headless: bool, storage: Path | None, mobile: bool):
    """Sobe o browser. `channel='chromium'` evita o headless_shell, que
    segfaulta em alguns hosts ARM."""
    browser = await pw.chromium.launch(headless=headless, channel="chromium")
    kwargs: dict = {
        "viewport": VIEWPORT_MOBILE if mobile else VIEWPORT,
        "device_scale_factor": 2,
        "locale": "pt-BR",
    }
    if storage and storage.exists():
        kwargs["storage_state"] = str(storage)
    ctx = await browser.new_context(**kwargs)
    return browser, ctx


async def _login(ctx, storage: Path) -> bool:
    page = await ctx.new_page()
    await page.goto(f"{BASE}/auth/signin", wait_until="domcontentloaded")
    print("\n" + "=" * 62)
    print("  Faça login na janela que abriu.")
    print("  (magic link por e-mail, código, ou 'Continuar com Google')")
    print("=" * 62)
    input("\n  Painel carregado? Aperte ENTER para continuar... ")

    url = page.url
    if "/auth/" in url or "signin" in url:
        print(f"\n  ⚠ Ainda parece a tela de login ({url}).")
        if input("  Continuar mesmo assim? [s/N] ").strip().lower() != "s":
            return False

    await ctx.storage_state(path=str(storage))
    print(f"  ✓ sessão salva em {storage}")
    await page.close()
    return True


async def _capturar(ctx, destino: Path, mobile: bool) -> tuple[int, list[str]]:
    destino.mkdir(parents=True, exist_ok=True)
    page = await ctx.new_page()
    sufixo = "-mobile" if mobile else ""
    ok, falhas = 0, []

    for slug, caminho, full_page, espera, observar in TELAS:
        print(f"\n→ {slug}  ({observar})")
        try:
            await page.goto(
                f"{BASE}{caminho}", wait_until="networkidle", timeout=45_000
            )
            await page.wait_for_timeout(espera)
            arq = destino / f"chatvolt-{slug}{sufixo}.png"
            await page.screenshot(path=str(arq), full_page=full_page)
            print(f"   ✓ {arq.name}  ({arq.stat().st_size // 1024} KB)")
            ok += 1
        except Exception as exc:  # noqa: BLE001 — captura é best-effort
            print(f"   ✗ {type(exc).__name__}: {str(exc)[:120]}")
            falhas.append(slug)

    await page.close()
    return ok, falhas


def _otimizar(destino: Path) -> None:
    """Reduz as capturas de @2x para 1x. Sem isso, uma tela full-page passa de
    3 MB e incha o repositório — texto continua legível em 1x."""
    try:
        from PIL import Image
    except ImportError:
        print("\n(Pillow não instalado — imagens ficam em @2x. `pip install pillow`)")
        return

    total_antes = total_depois = 0
    for arq in sorted(destino.glob("*.png")):
        total_antes += arq.stat().st_size
        img = Image.open(arq)
        if img.width > 1600:
            img = img.resize((img.width // 2, img.height // 2), Image.LANCZOS)
        img.convert("RGB").save(arq, "PNG", optimize=True)
        total_depois += arq.stat().st_size

    if total_antes:
        print(f"\nOtimizado: {total_antes // 1024}KB → {total_depois // 1024}KB")


async def executar(args) -> int:
    destino = Path(args.out)
    storage = Path("storage_state.json")

    async with async_playwright() as pw:
        if args.reusar and not storage.exists():
            print(f"ERRO: {storage} não existe. Rode sem --reusar primeiro.")
            return 1

        precisa_login = not args.reusar
        browser, ctx = await _abrir(
            pw,
            headless=not precisa_login,
            storage=storage if args.reusar else None,
            mobile=False,
        )

        if precisa_login:
            if not await _login(ctx, storage):
                await browser.close()
                return 1

        ok, falhas = (0, []) if args.so_sessao else await _capturar(ctx, destino, False)
        await ctx.close()
        await browser.close()

        if args.mobile and not args.so_sessao:
            print("\n--- viewport mobile ---")
            browser, ctx = await _abrir(pw, True, storage, mobile=True)
            ok_m, falhas_m = await _capturar(ctx, destino, True)
            ok += ok_m
            falhas += falhas_m
            await ctx.close()
            await browser.close()

    if args.so_sessao:
        print(f"\n✓ Sessão em {storage.resolve()} — mande para a VPS.")
        return 0

    _otimizar(destino)
    print(f"\n{'=' * 62}\n{ok} telas em {destino.resolve()}")
    if falhas:
        print(f"Falharam (rota pode ser outra): {', '.join(falhas)}")
    print(
        "\nRevise as imagens antes de enviar — Inbox e Contatos podem ter\n"
        "dados de cliente. Depois:\n"
        f"  scp -r {destino}/* opc@<vps>:/home/dev/projetos/whatsapp-langchain/"
        "docs/benchmark/plataformas/chatvolt/img/"
    )
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Captura telas do painel Chatvolt para o benchmark.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--reusar", action="store_true", help="usa storage_state.json existente"
    )
    ap.add_argument("--so-sessao", action="store_true", help="só grava a sessão")
    ap.add_argument("--mobile", action="store_true", help="captura também em 390x844")
    ap.add_argument("--out", default="chatvolt-img", help="pasta de saída")
    return asyncio.run(executar(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
