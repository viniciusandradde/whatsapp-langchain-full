#!/usr/bin/env python3
"""Captura dirigida do modal de permissão por membro (/settings/organization).

Por que é um script à parte: esta tela exige DOIS passos encadeados — abrir a
sub-aba "Membros da Equipe" e só então clicar a engrenagem na linha do membro.
O `--extras` do script base e a varredura genérica erram pelo mesmo motivo:
ambos enumeram botões no estado em que a página abre ("Perfil da Organização"),
onde não existe membro nenhum listado.

Gera, quando encontra:
    chatvolt-permissoes-membros.png   a aba com a lista de membros
    chatvolt-permissoes-modal.png     o modal de permissão por agente

Depende da sessão salva:
    python capture_chatvolt_local.py --so-sessao
"""

from __future__ import annotations

import asyncio
import re
import sys
import unicodedata
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    sys.exit("Playwright não instalado.\n\n    pip install playwright\n")

BASE = "https://app.chatvolt.ai"
DESTINO = Path("chatvolt-img")

ABA_MEMBROS = [
    '[role="tab"]:has-text("Membros da Equipe")',
    'button:has-text("Membros da Equipe")',
    '[role="tab"]:has-text("Membros")',
    'button:has-text("Membros")',
    '[role="tab"]:has-text("Team Members")',
]

# A engrenagem não tem rótulo textual; vai por ícone, aria-label e posição na
# linha da tabela. Ordem = da âncora mais específica para a mais genérica.
ENGRENAGEM = [
    'button:has(svg.lucide-settings)',
    'button:has(svg.lucide-settings-2)',
    'button:has(svg.lucide-cog)',
    '[aria-label*="permiss" i]',
    '[aria-label*="permission" i]',
    '[aria-label*="config" i]',
    'tbody tr button:has(svg)',
    'table tr button',
    '[class*="member"] button:has(svg)',
]


# Clicar por ícone/posição é cego ao que o botão faz. Na linha do membro o
# único botão é "Transferir Propriedade" — ação IRREVERSÍVEL. Numa conta com
# equipe real esse clique abre a transferência de dono. Rótulo é checado antes.
PERIGO = re.compile(
    r"transferir|transfer|exclu|delet|remov|apagar|revogar|revoke|"
    r"sair|logout|desativ|encerrar|cancel",
    re.I,
)


def _sem_acento(texto: str) -> str:
    return unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()


async def _rotulo(el) -> str:
    for attr in ("aria-label", "title"):
        try:
            v = await el.get_attribute(attr)
            if v and v.strip():
                return v.strip()
        except Exception:  # noqa: BLE001
            pass
    try:
        return " ".join(((await el.inner_text()) or "").split())[:80]
    except Exception:  # noqa: BLE001
        return ""


async def _clicar(page, seletores: list[str], timeout: int = 5000) -> str | None:
    for sel in seletores:
        try:
            alvo = page.locator(sel).first
            await alvo.wait_for(state="visible", timeout=timeout)
            rot = await _rotulo(alvo)
            if PERIGO.search(_sem_acento(rot)):
                print(f"   ⊘ pulado (ação destrutiva): '{rot}'", flush=True)
                continue
            await alvo.click()
            return sel
        except Exception:  # noqa: BLE001 — heurístico: tenta o próximo
            continue
    return None


async def executar() -> int:
    storage = Path("storage_state.json")
    if not storage.exists():
        print("ERRO: storage_state.json não existe.")
        print("Rode antes:  python capture_chatvolt_local.py --so-sessao")
        return 1

    DESTINO.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, channel="chromium")
        ctx = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            device_scale_factor=2,
            locale="pt-BR",
            storage_state=str(storage),
        )
        ctx.on("dialog", lambda d: asyncio.ensure_future(d.dismiss()))
        page = await ctx.new_page()

        print("→ /settings/organization", flush=True)
        await page.goto(
            f"{BASE}/settings/organization", wait_until="networkidle", timeout=45_000
        )
        await page.wait_for_timeout(4500)

        aba = await _clicar(page, ABA_MEMBROS)
        if not aba:
            print("   ✗ sub-aba 'Membros da Equipe' não encontrada.", flush=True)
            await browser.close()
            return 1
        print(f"   ✓ aba aberta (via {aba})", flush=True)
        await page.wait_for_timeout(3000)

        arq = DESTINO / "chatvolt-permissoes-membros.png"
        await page.screenshot(path=str(arq))
        print(f"   ✓ {arq.name}  ({arq.stat().st_size // 1024} KB)", flush=True)

        # Conta linhas antes de clicar: sem membro na tabela, não há engrenagem
        # e o diagnóstico correto é "conta de um usuário só", não "seletor ruim".
        try:
            linhas = await page.locator("tbody tr").count()
        except Exception:  # noqa: BLE001
            linhas = -1
        print(f"   · linhas na tabela de membros: {linhas}", flush=True)

        eng = await _clicar(page, ENGRENAGEM)
        if not eng:
            print(
                "   ✗ engrenagem não encontrada — provável conta sem outros membros.",
                flush=True,
            )
            await browser.close()
            return 2
        await page.wait_for_timeout(3000)
        arq = DESTINO / "chatvolt-permissoes-modal.png"
        await page.screenshot(path=str(arq))
        print(f"   ✓ {arq.name}  ({arq.stat().st_size // 1024} KB) via {eng}", flush=True)

        await ctx.close()
        await browser.close()
    return 0


if __name__ == "__main__":
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(asyncio.run(executar()))
