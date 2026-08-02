#!/usr/bin/env python3
"""Varredura profunda do painel Chatvolt: abas, modais e painéis de config.

Complementa `capture_chatvolt_local.py`, que captura só o estado inicial de
cada rota. Aqui a ideia é abrir o que está atrás de um clique — abas do editor
de agente, drawer de filtros do Inbox, modal de permissão por membro,
configuração de integração — e capturar cada um.

Depende da sessão já salva:

    python capture_chatvolt_local.py --so-sessao   # uma vez
    python varrer_chatvolt.py

--------------------------------------------------------------------------
SEGURANÇA — leia antes de mexer nas listas
--------------------------------------------------------------------------

Isto roda contra uma conta de PRODUÇÃO com dados de cliente real. Clicar em
botão arbitrário pode excluir agente, disparar mensagem para contato ou
cancelar assinatura. Por isso o clique é conservador:

  * abas (`role=tab`) são sempre seguras — só trocam o painel visível;
  * botões só são clicados se o texto casar com ABRIR (intenção de abrir algo)
    E não casar com PERIGO;
  * PERIGO ganha de ABRIR sempre que os dois casarem;
  * diálogos nativos (confirm/alert) são dispensados automaticamente, porque
    travam o Playwright;
  * qualquer clique que mude de rota é desfeito com voltar.

Ao ampliar ABRIR, prefira errar para menos. Uma tela a menos no benchmark é
barata; um agente excluído na conta do operador, não.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import unicodedata
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    sys.exit("Playwright não instalado.\n\n    pip install playwright\n")

BASE = "https://app.chatvolt.ai"
VIEWPORT = {"width": 1440, "height": 900}
LOCALES = ("pt-BR", "en-US", "es-ES")

ROTAS = [
    "/agents",
    "/agents/create",
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
    "/partner-set",
    "/onboarding",
    "/settings/billing",
    "/settings/api-keys",
    "/settings/llm-keys",
    "/settings/organization",
]

# Abre algo sem efeito colateral: painel, modal, drawer, editor.
ABRIR = re.compile(
    r"config|settings|ajuste|prefer|editar|edit|detalh|detail|ver mais|view|"
    r"filtro|filter|permiss|permission|gerenciar|manage|membro|member|"
    r"variav|variable|export|integra|integration|conectar|connect|"
    r"nova|novo|new|criar|create|adicionar|add|tool|ferramenta|avancad|advanced|"
    r"webhook|api|chave|key|modelo|model|prompt|canal|channel|agendar|schedule",
    re.I,
)

# Efeito colateral real. Vence ABRIR em caso de empate.
PERIGO = re.compile(
    r"exclu|delet|delete|remov|remove|apagar|limpar|clear|reset|restaurar|"
    r"sair|logout|log out|desconect|disconnect|revogar|revoke|rotacion|rotate|"
    r"cancel|cancelar|encerrar|desativ|disable|desabilit|arquiv|archive|"
    r"enviar|send|disparar|publicar|publish|salvar|save|confirmar|confirm|"
    r"pagar|pay|comprar|buy|assinar|subscribe|upgrade|downgrade|"
    r"treinar|train|sincronizar|sync|importar|import|duplicar|duplicate",
    re.I,
)

MAX_ABAS = 12
MAX_BOTOES = 10


def _slug(texto: str, limite: int = 34) -> str:
    txt = unicodedata.normalize("NFKD", texto or "")
    txt = txt.encode("ascii", "ignore").decode()
    txt = re.sub(r"[^a-zA-Z0-9]+", "-", txt).strip("-").lower()
    return (txt or "sem-nome")[:limite]


def _sem_locale(caminho: str) -> str:
    for loc in LOCALES:
        if caminho.startswith(f"/{loc}/") or caminho == f"/{loc}":
            return caminho[len(loc) + 1 :] or "/"
    return caminho


def _sem_acento(texto: str) -> str:
    """ASCII puro para casar com os regex.

    Sem isto, 'Variáveis' não casa com `variav` — e, pior, um verbo destrutivo
    acentuado escaparia de PERIGO. Normalizar aperta a lista de perigo, não
    afrouxa.
    """
    return unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode()


def _seguro(rotulo: str) -> bool:
    r = _sem_acento(rotulo)
    return bool(ABRIR.search(r)) and not PERIGO.search(r)


async def _rotulo(el) -> str:
    """Texto acessível do elemento, com fallback para aria-label/title."""
    for attr in ("aria-label", "title"):
        try:
            v = await el.get_attribute(attr)
            if v and v.strip():
                return v.strip()
        except Exception:  # noqa: BLE001
            pass
    try:
        t = (await el.inner_text()) or ""
        return " ".join(t.split())[:80]
    except Exception:  # noqa: BLE001
        return ""


async def _shot(page, destino: Path, nome: str, registro: list) -> None:
    arq = destino / f"{nome}.png"
    await page.screenshot(path=str(arq))
    kb = arq.stat().st_size // 1024
    registro.append(nome)
    print(f"     · {arq.name}  ({kb} KB)", flush=True)


async def _varrer_rota(page, rota: str, destino: Path, registro: list) -> dict:
    base_slug = _slug(rota.strip("/").replace("/", "-")) or "home"
    info: dict = {"rota": rota, "abas": [], "paineis": [], "erro": None}

    try:
        await page.goto(f"{BASE}{rota}", wait_until="networkidle", timeout=45_000)
    except Exception as exc:  # noqa: BLE001
        info["erro"] = f"{type(exc).__name__}: {str(exc)[:100]}"
        print(f"   ✗ navegação falhou: {info['erro']}", flush=True)
        return info

    await page.wait_for_timeout(4500)
    final = _sem_locale(page.url.replace(BASE, "").split("?")[0])
    if final.rstrip("/") != rota.rstrip("/"):
        info["redirecionou_para"] = final
        print(f"   ⚠ redirecionou → {final}", flush=True)

    # --- abas -------------------------------------------------------------
    abas = page.locator('[role="tab"], [role="tablist"] button')
    try:
        n_abas = min(await abas.count(), MAX_ABAS)
    except Exception:  # noqa: BLE001
        n_abas = 0

    for i in range(n_abas):
        el = abas.nth(i)
        rot = await _rotulo(el)
        if not rot or PERIGO.search(_sem_acento(rot)):
            continue
        try:
            await el.click(timeout=4000)
            await page.wait_for_timeout(2600)
            nome = f"chatvolt-{base_slug}-aba-{i:02d}-{_slug(rot)}"
            await _shot(page, destino, nome, registro)
            info["abas"].append(rot)
        except Exception as exc:  # noqa: BLE001
            print(f"     ✗ aba '{rot}': {type(exc).__name__}", flush=True)

    # --- botões que abrem painel/modal -----------------------------------
    botoes = page.locator("button:visible, [role='button']:visible")
    try:
        n_bt = await botoes.count()
    except Exception:  # noqa: BLE001
        n_bt = 0

    candidatos = []
    for i in range(min(n_bt, 60)):
        rot = await _rotulo(botoes.nth(i))
        if rot and _seguro(rot):
            candidatos.append((i, rot))
        if len(candidatos) >= MAX_BOTOES:
            break

    for i, rot in candidatos:
        try:
            await botoes.nth(i).click(timeout=4000)
            await page.wait_for_timeout(2600)

            # Clique que navegou para outra rota: registra e volta.
            agora = _sem_locale(page.url.replace(BASE, "").split("?")[0])
            nome = f"chatvolt-{base_slug}-abre-{i:02d}-{_slug(rot)}"
            await _shot(page, destino, nome, registro)
            info["paineis"].append(rot)

            if agora.rstrip("/") != rota.rstrip("/"):
                await page.go_back(wait_until="networkidle", timeout=30_000)
                await page.wait_for_timeout(2500)
            else:
                await page.keyboard.press("Escape")
                await page.wait_for_timeout(900)
        except Exception as exc:  # noqa: BLE001
            print(f"     ✗ botão '{rot}': {type(exc).__name__}", flush=True)
            try:
                await page.keyboard.press("Escape")
            except Exception:  # noqa: BLE001
                pass

    return info


async def executar(args) -> int:
    destino = Path(args.out)
    destino.mkdir(parents=True, exist_ok=True)
    storage = Path("storage_state.json")
    if not storage.exists():
        print("ERRO: storage_state.json não existe.")
        print("Rode antes:  python capture_chatvolt_local.py --so-sessao")
        return 1

    rotas = [r for r in ROTAS if not args.rota or r in args.rota]
    registro: list[str] = []
    relatorio: list[dict] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, channel="chromium")
        ctx = await browser.new_context(
            viewport=VIEWPORT,
            device_scale_factor=2,
            locale="pt-BR",
            storage_state=str(storage),
        )
        # Diálogo nativo trava o Playwright — dispensa sempre.
        ctx.on("dialog", lambda d: asyncio.ensure_future(d.dismiss()))
        page = await ctx.new_page()

        for rota in rotas:
            print(f"\n→ {rota}", flush=True)
            relatorio.append(await _varrer_rota(page, rota, destino, registro))

        await ctx.close()
        await browser.close()

    (destino / "varredura.json").write_text(
        json.dumps(relatorio, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n{'=' * 62}")
    print(f"{len(registro)} telas novas em {destino.resolve()}")
    quebradas = [r["rota"] for r in relatorio if r["erro"]]
    desviadas = [
        f"{r['rota']} → {r['redirecionou_para']}"
        for r in relatorio
        if r.get("redirecionou_para")
    ]
    if quebradas:
        print(f"Falharam: {', '.join(quebradas)}")
    if desviadas:
        print(f"Redirecionaram: {', '.join(desviadas)}")
    return 0


def main() -> int:
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", default="chatvolt-img", help="pasta de saída")
    ap.add_argument(
        "--rota", action="append", help="limita a estas rotas (repetível)"
    )
    return asyncio.run(executar(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
