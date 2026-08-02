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

# O app é i18n e reescreve /agents → /pt-BR/agents. Sem tirar esse prefixo,
# a checagem de redirect acusaria as 20 rotas como se tivessem mudado.
LOCALES = ("pt-BR", "en-US", "es-ES")


def _sem_locale(caminho: str) -> str:
    for loc in LOCALES:
        if caminho.startswith(f"/{loc}/") or caminho == f"/{loc}":
            return caminho[len(loc) + 1 :] or "/"
    return caminho


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


async def _login(ctx, storage: Path, espera_max_s: int = 1800) -> bool:
    """Abre a tela de login e espera o operador entrar.

    Detecta a conclusão pela própria URL em vez de pedir ENTER: o script roda
    com stdin fechado quando disparado por um agente/CI, e `input()` estoura.
    """
    page = await ctx.new_page()
    await page.goto(f"{BASE}/auth/signin", wait_until="domcontentloaded")
    print("\n" + "=" * 62)
    print("  Faça login na janela que abriu.")
    print("  (magic link por e-mail, código, ou 'Continuar com Google')")
    print(f"  O script detecta sozinho quando o painel carregar (até {espera_max_s // 60} min).")
    print("=" * 62, flush=True)

    def _no_painel() -> str | None:
        """URL de qualquer aba já dentro do painel.

        Varre o contexto inteiro, não só a aba inicial: magic link costuma
        abrir aba nova, e a original fica parada em /auth/verify-request —
        logado de verdade, mas invisível para quem olha só uma aba.
        """
        for p in ctx.pages:
            if p.is_closed():
                continue
            u = p.url
            if u.startswith(BASE) and "/auth/" not in u and "signin" not in u:
                return u
        return None

    for decorrido in range(0, espera_max_s, 2):
        # asyncio.sleep, e não page.wait_for_timeout: a aba inicial pode ser
        # fechada pelo operador sem que a sessão se perca (o login foi noutra
        # aba). Só desiste quando não sobra aba nenhuma.
        await asyncio.sleep(2)
        try:
            achou = _no_painel()
        except Exception:  # noqa: BLE001
            achou = None
        if not ctx.pages:
            print("\n  ✗ a janela do navegador foi fechada antes do login.", flush=True)
            return False
        if achou:
            # Confirma que é o painel mesmo, e não um passo intermediário.
            await asyncio.sleep(3)
            if _no_painel():
                print(f"\n  ✓ login detectado — {achou}", flush=True)
                break
        if decorrido and decorrido % 30 == 0:
            print(f"  … aguardando login ({decorrido}s)", flush=True)
    else:
        print("\n  ✗ tempo esgotado, ainda na tela de login.", flush=True)
        return False

    await ctx.storage_state(path=str(storage))
    print(f"  ✓ sessão salva em {storage}", flush=True)
    try:
        await page.close()
    except Exception:  # noqa: BLE001 — a aba pode já ter sido fechada
        pass
    return True


async def _capturar(
    ctx, destino: Path, mobile: bool, apenas: set[str] | None = None
) -> tuple[int, list[str]]:
    destino.mkdir(parents=True, exist_ok=True)
    page = await ctx.new_page()
    sufixo = "-mobile" if mobile else ""
    ok, falhas = 0, []

    telas = [t for t in TELAS if apenas is None or t[0] in apenas]
    for slug, caminho, full_page, espera, observar in telas:
        print(f"\n→ {slug}  ({observar})")
        try:
            await page.goto(
                f"{BASE}{caminho}", wait_until="networkidle", timeout=45_000
            )
            await page.wait_for_timeout(espera)
            arq = destino / f"chatvolt-{slug}{sufixo}.png"
            await page.screenshot(path=str(arq), full_page=full_page)
            # Redirect silencioso é o modo de falha mais provável aqui: a rota
            # some do build e o Next devolve /agents ou /auth com HTTP 200.
            # split("?"): o app acrescenta query própria (?tab=…&limit=…) sem
            # trocar de tela — comparar com a query acusaria redirect que não houve.
            destino_final = _sem_locale(page.url.replace(BASE, "").split("?")[0])
            aviso = ""
            if destino_final.rstrip("/") != caminho.rstrip("/"):
                aviso = f"  ⚠ REDIRECIONOU → {destino_final}"
                falhas.append(f"{slug} (→ {destino_final})")
            print(f"   ✓ {arq.name}  ({arq.stat().st_size // 1024} KB){aviso}")
            ok += 1
        except Exception as exc:  # noqa: BLE001 — captura é best-effort
            print(f"   ✗ {type(exc).__name__}: {str(exc)[:120]}")
            falhas.append(slug)

    await page.close()
    return ok, falhas


async def _extras(ctx, destino: Path) -> tuple[int, list[str]]:
    """Telas que exigem interação, não só navegação.

    Best-effort de propósito: os seletores são heurísticos (o app não expõe
    data-testid), então cada extra tenta várias âncoras e desiste avisando em
    vez de fingir sucesso.
    """
    page = await ctx.new_page()
    ok, falhas = 0, []

    async def _tentar(seletores: list[str], timeout: int = 5000):
        for sel in seletores:
            try:
                alvo = page.locator(sel).first
                await alvo.wait_for(state="visible", timeout=timeout)
                await alvo.click()
                return sel
            except Exception:  # noqa: BLE001 — seletor heurístico, tenta o próximo
                continue
        return None

    # 1) Modal de permissões por membro (/settings/organization).
    print("\n→ permissoes-modal  (permissão por agente individual)")
    try:
        await page.goto(
            f"{BASE}/settings/organization", wait_until="networkidle", timeout=45_000
        )
        await page.wait_for_timeout(4000)
        achou = await _tentar(
            [
                'button:has(svg.lucide-settings)',
                'button:has(svg.lucide-cog)',
                '[aria-label*="permission" i]',
                '[aria-label*="permiss" i]',
                'table tbody tr button:last-of-type',
                'tr button:has(svg)',
            ]
        )
        if not achou:
            raise RuntimeError("nenhum ícone de engrenagem encontrado na linha do membro")
        await page.wait_for_timeout(2500)
        arq = destino / "chatvolt-permissoes-modal.png"
        await page.screenshot(path=str(arq))
        print(f"   ✓ {arq.name}  (via {achou})")
        ok += 1
    except Exception as exc:  # noqa: BLE001
        print(f"   ✗ {type(exc).__name__}: {str(exc)[:140]}")
        falhas.append("permissoes-modal")

    # 2) Aba Tools + editor de HTTP Tool (/agents/create).
    print("\n→ http-tool  (aba Tools e editor de HTTP Tool)")
    try:
        await page.goto(
            f"{BASE}/agents/create", wait_until="networkidle", timeout=45_000
        )
        await page.wait_for_timeout(4000)
        aba = await _tentar(
            [
                'button[role="tab"]:has-text("Tools")',
                '[role="tab"]:has-text("Ferramentas")',
                'button:has-text("Tools")',
                'a:has-text("Tools")',
            ]
        )
        if not aba:
            raise RuntimeError("aba Tools não encontrada")
        await page.wait_for_timeout(2500)
        # O editor costuma abrir por um "Add tool" e depois a opção HTTP.
        await _tentar(
            [
                'button:has-text("HTTP Tool")',
                'button:has-text("Add Tool")',
                'button:has-text("Adicionar")',
                'button:has-text("HTTP")',
            ],
            timeout=4000,
        )
        await page.wait_for_timeout(1500)
        await _tentar(['button:has-text("HTTP")', 'li:has-text("HTTP")'], timeout=3000)
        await page.wait_for_timeout(2500)
        arq = destino / "chatvolt-http-tool.png"
        await page.screenshot(path=str(arq))
        print(f"   ✓ {arq.name}  (aba via {aba})")
        ok += 1
    except Exception as exc:  # noqa: BLE001
        print(f"   ✗ {type(exc).__name__}: {str(exc)[:140]}")
        falhas.append("http-tool")

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

    LARGURA_MAX = 1440
    total_antes = total_depois = 0
    for arq in sorted(destino.glob("*.png")):
        total_antes += arq.stat().st_size
        img = Image.open(arq)
        if img.width > LARGURA_MAX:
            altura = round(img.height * LARGURA_MAX / img.width)
            img = img.resize((LARGURA_MAX, altura), Image.LANCZOS)
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

        if args.extras and not args.so_sessao:
            print("\n--- extras (interação) ---")
            ok_e, falhas_e = await _extras(ctx, destino)
            ok += ok_e
            falhas += falhas_e

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
    # O console do Windows abre em cp1252, onde ✓/✗ não existem — sem isto o
    # primeiro print de sucesso derruba a captura com UnicodeEncodeError.
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    ap = argparse.ArgumentParser(
        description="Captura telas do painel Chatvolt para o benchmark.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument(
        "--reusar", action="store_true", help="usa storage_state.json existente"
    )
    ap.add_argument("--so-sessao", action="store_true", help="só grava a sessão")
    ap.add_argument("--mobile", action="store_true", help="captura também em 390x844")
    ap.add_argument(
        "--extras",
        action="store_true",
        help="telas que exigem clique: modal de permissões e HTTP Tool",
    )
    ap.add_argument("--out", default="chatvolt-img", help="pasta de saída")
    return asyncio.run(executar(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
