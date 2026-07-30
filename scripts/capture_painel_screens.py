#!/usr/bin/env python3
"""Captura as telas do NOSSO painel para a auditoria de UI/UX.

Contraparte de `capture_chatvolt_local.py`: lá o alvo era o concorrente, aqui é
o Chat Nexus. O objetivo é olhar o nosso produto com a mesma régua do
benchmark — o que a tela comunica, densidade, hierarquia, estado vazio — em
desktop e mobile.

Dois modos de autenticação:

- **cookie de sessão** (`--cookie`), reaproveitando o navegador já logado do
  operador. É o modo usado contra produção: não exige senha e não escreve nada.
- **e-mail + senha** (`ADMIN_EMAIL` / `ADMIN_PASSWORD` no ambiente), que só
  funciona onde essas credenciais valem — tipicamente o stack local. O
  `admin@validation.local` do `.env` **não** é o admin de produção.

Uso:
    # produção, com cookie copiado do navegador (DevTools → Application → Cookies)
    uv run python scripts/capture_painel_screens.py --cookie "$COOKIE_SESSAO"

    # stack local, login por formulário
    uv run python scripts/capture_painel_screens.py --base http://localhost:3000

    # só um grupo da navegação
    uv run python scripts/capture_painel_screens.py --grupo operacao

    # contra stack local
    uv run python scripts/capture_painel_screens.py --base http://localhost:3000

Cuidado com o rate limit: `install_admin_rate_limit` corta em 60 req/min por
usuário em `/api/*`, e cada tela dispara várias chamadas. O `--pausa` (default
3s) existe pra isso — abaixar demais devolve 429 e a captura vira screenshot de
erro. O script avisa quando vê 429.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
from pathlib import Path

from playwright.async_api import Page, async_playwright

RAIZ = Path(__file__).resolve().parents[1]
DESTINO = RAIZ / "docs/benchmark/nosso-painel/img"

VIEWPORT = {"width": 1440, "height": 900}
VIEWPORT_MOBILE = {"width": 390, "height": 844}

# (slug, caminho, full_page, espera_ms)
#
# `full_page=True` só onde a página é formulário ou lista longa e o corte no
# fold esconderia o que importa. Nas demais o shot de viewport é mais honesto:
# é o que o operador vê sem rolar.
ROTAS: dict[str, list[tuple[str, str, bool, int]]] = {
    "visao": [
        ("home", "/", False, 3000),
        ("dashboard-atendimento", "/dashboard/atendimento", True, 5000),
        ("onboarding", "/onboarding", True, 4000),
    ],
    "operacao": [
        ("atendimento", "/atendimento", False, 6000),
        ("chats", "/chats", False, 5000),
        ("chats-relatorios", "/chats/relatorios", True, 5000),
        ("clientes", "/clientes", False, 4000),
        ("agendamentos", "/agendamentos", False, 4000),
        ("campanhas", "/campanhas", False, 4000),
        ("disparador-contatos", "/disparador/contatos", False, 4000),
        ("disparador-grupos", "/disparador/grupos", False, 4000),
        ("disparador-api-keys", "/disparador/api-keys", False, 3000),
        ("tags", "/tags", False, 3000),
    ],
    "ia": [
        ("dashboard-ia", "/dashboard/ia", True, 5000),
        ("agents", "/agents", False, 4000),
        ("agents-new", "/agents/new", True, 4000),
        ("menus", "/menus", False, 4000),
        ("menus-new", "/menus/new", True, 4000),
        ("workflows", "/workflows", False, 4000),
        ("catalog-models", "/catalog/models", False, 4000),
        ("catalog-models-new", "/catalog/models/new", True, 3000),
        ("catalog-mcp", "/catalog/mcp", False, 3000),
        ("catalog-mcp-new", "/catalog/mcp/new", True, 3000),
        ("modelos", "/modelos", False, 3000),
        ("settings-pastas", "/settings/pastas", False, 4000),
        ("settings-variaveis", "/settings/variaveis", False, 3000),
        ("models", "/models", False, 4000),
        ("whitelist", "/whitelist", False, 3000),
    ],
    "conectividade": [
        ("connections", "/connections", False, 4000),
        ("settings-integracoes", "/settings/integracoes", True, 4000),
        ("hooks", "/hooks", False, 3000),
    ],
    "governanca": [
        ("companies", "/companies", False, 4000),
        ("usuarios", "/usuarios", False, 4000),
        ("atendentes", "/atendentes", False, 4000),
        ("atendentes-me-dashboard", "/atendentes/me/dashboard", True, 4000),
        ("billing", "/billing", True, 4000),
        ("governanca-ia-budget", "/governanca/ia-budget", True, 4000),
        ("settings-perfis", "/settings/perfis", True, 4000),
        ("settings-departamentos", "/settings/departamentos", False, 3000),
        ("settings-turnos", "/settings/turnos", False, 3000),
        ("settings-horarios", "/settings/horarios", True, 3000),
        ("settings-calendar-rules", "/settings/calendar-rules", True, 3000),
        ("settings", "/settings", True, 3000),
    ],
    "observabilidade": [
        ("traces", "/traces", False, 5000),
        ("queue", "/queue", False, 4000),
        ("dashboard-qualidade", "/dashboard/qualidade", True, 5000),
        ("dashboard-rag", "/dashboard/rag", True, 5000),
        ("dashboard-rag-sandbox", "/dashboard/rag/sandbox", True, 4000),
        ("relatorios-allure", "/relatorios/allure", False, 4000),
        ("settings-login-history", "/settings/security/login-history", False, 4000),
        ("settings-audit", "/settings/security/audit", False, 4000),
        ("settings-governanca", "/settings/security/governanca", True, 4000),
        ("settings-feature-flags", "/settings/feature-flags", True, 3000),
    ],
}

# Rotas de detalhe: o ID vem de uma lista já carregada, não é chutado.
# (slug, rota da lista, regex do href do primeiro item, sufixo, full_page, espera)
DETALHES: list[tuple[str, str, str, str, bool, int]] = [
    ("connection-detalhe", "/connections", r"^/connections/\d+$", "", True, 5000),
    ("campanha-detalhe", "/campanhas", r"^/campanhas/\d+$", "", True, 5000),
    ("cliente-detalhe", "/clientes", r"^/clientes/\d+$", "", True, 4000),
    ("workflow-detalhe", "/workflows", r"^/workflows/\d+$", "", True, 5000),
    ("agent-edit", "/agents", r"^/agents/[^/]+/edit$", "", True, 5000),
    ("menu-edit", "/menus", r"^/menus/\d+/edit$", "", True, 5000),
    ("chat-detalhe", "/chats", r"^/chats/[^/]+$", "", True, 5000),
]


def _slug(caminho: str) -> str:
    """Converte "/settings/security/audit" em "settings-security-audit"."""
    return caminho.strip("/").replace("/", "-") or "home"


async def _shot(page: Page, slug: str, full_page: bool, sufixo: str) -> None:
    destino = DESTINO / f"nexus-{slug}{sufixo}.png"
    await page.screenshot(path=str(destino), full_page=full_page)
    print(f"  ✓ {destino.name}  ({destino.stat().st_size // 1024} KB)")


def storage_de_cookie(valor: str, base: str, tema: str | None = None) -> dict:
    """Monta um storage_state a partir do cookie de sessão colado pelo operador.

    Aceita tanto o valor puro quanto o par `nome=valor` copiado do DevTools. O
    Better Auth troca o nome do cookie conforme o esquema: em HTTPS ele prefixa
    com `__Secure-`. Como o operador pode colar qualquer um dos dois, o nome é
    inferido do próprio texto e só cai no default quando não veio nome.
    """
    nome = (
        "__Secure-better-auth.session_token"
        if base.startswith("https")
        else "better-auth.session_token"
    )
    valor = valor.strip()
    if "=" in valor and "session_token" in valor.split("=", 1)[0]:
        nome, valor = (p.strip() for p in valor.split("=", 1))
    dominio = base.split("//", 1)[1].split("/", 1)[0].split(":")[0]
    cookies = [
        {
            "name": nome,
            "value": valor,
            "domain": dominio,
            "path": "/",
            "httpOnly": True,
            "secure": base.startswith("https"),
            "sameSite": "Lax",
            "expires": -1,
        }
    ]
    # O tema mora em localStorage (`theme`), que é onde o next-themes guarda a
    # escolha; ele aplica a classe no <html> antes da hidratação. Semear a
    # chave é o que permite capturar a mesma tela nos dois temas sem clicar no
    # seletor. (Antes era um cookie `vsa-theme` de três valores — ver ADR-010.)
    origins = (
        [{"origin": base, "localStorage": [{"name": "theme", "value": tema}]}]
        if tema
        else []
    )
    return {"cookies": cookies, "origins": origins}


async def confirmar_sessao(page: Page, base: str) -> bool:
    """Abre a home e verifica que o cookie realmente autentica (não caiu em /login)."""
    await page.goto(f"{base}/", wait_until="domcontentloaded", timeout=45_000)
    await page.wait_for_timeout(4000)
    if "/login" in page.url:
        print(
            "ERRO: cookie não autenticou — sessão expirada ou nome errado",
            file=sys.stderr,
        )
        return False
    return True


async def login(page: Page, base: str, email: str, senha: str) -> bool:
    """Autentica via formulário do Better Auth e confirma saída do /login."""
    await page.goto(f"{base}/login", wait_until="domcontentloaded", timeout=45_000)
    await page.wait_for_selector("#email", timeout=20_000)
    await page.fill("#email", email)
    await page.fill("#password", senha)
    await page.click("button[type=submit]")
    try:
        await page.wait_for_url(
            lambda url: "/login" not in url,
            timeout=30_000,  # type: ignore[arg-type]
        )
    except Exception:
        erro = await page.query_selector("text=/Erro ao fazer login|Invalid/i")
        print(
            f"ERRO: login não completou (mensagem na tela: {bool(erro)})",
            file=sys.stderr,
        )
        return False
    await page.wait_for_timeout(3000)
    return True


async def capturar_rota(
    page: Page,
    base: str,
    slug: str,
    caminho: str,
    full_page: bool,
    espera: int,
    sufixo: str,
    alertas: list[str],
) -> bool:
    url = f"{base}{caminho}"
    print(f"→ {slug}: {caminho}")
    try:
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=45_000)
        if resp and resp.status >= 400:
            alertas.append(f"{caminho} → HTTP {resp.status}")
        await page.wait_for_timeout(espera)
        # 429 vira tela de erro; melhor saber na hora do que descobrir na análise.
        corpo = await page.inner_text("body")
        if "429" in corpo or "Too Many Requests" in corpo:
            alertas.append(f"{caminho} → possível rate limit (429) na tela")
        await _shot(page, slug, full_page, sufixo)
        return True
    except Exception as exc:  # noqa: BLE001 — captura é best-effort
        print(f"  ✗ falhou: {type(exc).__name__}: {exc}")
        alertas.append(f"{caminho} → {type(exc).__name__}")
        return False


async def descobrir_detalhe(
    page: Page, base: str, lista: str, padrao: str
) -> str | None:
    """Abre a lista e devolve o href do primeiro item que casa com o padrão."""
    await page.goto(f"{base}{lista}", wait_until="domcontentloaded", timeout=45_000)
    await page.wait_for_timeout(4000)
    hrefs = await page.eval_on_selector_all(
        "a[href]", "els => els.map(e => e.getAttribute('href'))"
    )
    rx = re.compile(padrao)
    for href in hrefs:
        if href and rx.match(href):
            return href
    return None


async def executar(
    base: str,
    grupos: list[str],
    pausa: int,
    mobile: bool,
    detalhes: bool,
    cookie: str | None,
    tema: str | None,
    avulsas: list[str],
) -> int:
    email = os.environ.get("ADMIN_EMAIL", "")
    senha = os.environ.get("ADMIN_PASSWORD", "")
    if not cookie and not (email and senha):
        print(
            "ERRO: passe --cookie (ou COOKIE_SESSAO no ambiente), ou exporte "
            "ADMIN_EMAIL/ADMIN_PASSWORD válidos pro alvo",
            file=sys.stderr,
        )
        return 1

    DESTINO.mkdir(parents=True, exist_ok=True)
    alertas: list[str] = []
    total = falhas = 0

    async with async_playwright() as pw:
        # `channel="chromium"` força o build completo: o headless_shell padrão
        # dá SIGSEGV neste host ARM/OEL8. Não trocar sem testar em aarch64.
        browser = await pw.chromium.launch(
            headless=True,
            channel="chromium",
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        tema_sfx = f"-{tema}" if tema else ""
        for viewport, sufixo in [
            (VIEWPORT, tema_sfx),
            *([(VIEWPORT_MOBILE, f"-mobile{tema_sfx}")] if mobile else []),
        ]:
            ctx_kwargs: dict = {
                "viewport": viewport,
                "device_scale_factor": 2,
                "locale": "pt-BR",
            }
            if cookie:
                ctx_kwargs["storage_state"] = storage_de_cookie(cookie, base, tema)
            ctx = await browser.new_context(**ctx_kwargs)
            page = await ctx.new_page()
            print(f"\n=== sessão ({sufixo or 'desktop'}) ===")
            autenticado = (
                await confirmar_sessao(page, base)
                if cookie
                else await login(page, base, email, senha)
            )
            if not autenticado:
                await ctx.close()
                await browser.close()
                return 1

            # Rotas avulsas (`--rota`) substituem os grupos: servem pra
            # conferir um punhado de telas específicas (ex: as que têm
            # `dark:` no código) sem varrer o grupo inteiro de novo.
            planos: list[tuple[str, list[tuple[str, str, bool, int]]]] = (
                [("avulsas", [(_slug(r), r, True, 4000) for r in avulsas])]
                if avulsas
                else [(g, ROTAS[g]) for g in grupos]
            )
            for grupo, telas in planos:
                print(f"\n--- {grupo} {sufixo} ---")
                for slug, caminho, full_page, espera in telas:
                    total += 1
                    ok = await capturar_rota(
                        page, base, slug, caminho, full_page, espera, sufixo, alertas
                    )
                    falhas += 0 if ok else 1
                    await page.wait_for_timeout(pausa)

            if detalhes and not avulsas:
                print(f"\n--- detalhes {sufixo} ---")
                for slug, lista, padrao, _sfx, full_page, espera in DETALHES:
                    href = await descobrir_detalhe(page, base, lista, padrao)
                    if not href:
                        print(f"  ↷ {slug}: nenhum item em {lista}")
                        alertas.append(f"{slug} → lista {lista} vazia")
                        continue
                    total += 1
                    ok = await capturar_rota(
                        page, base, slug, href, full_page, espera, sufixo, alertas
                    )
                    falhas += 0 if ok else 1
                    await page.wait_for_timeout(pausa)

            await ctx.close()
        await browser.close()

    print(f"\n{total - falhas}/{total} capturadas em {DESTINO}")
    if alertas:
        print("\nAlertas:")
        for a in alertas:
            print(f"  ! {a}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default="https://chat.vsanexus.com")
    ap.add_argument("--grupo", action="append", choices=sorted(ROTAS), help="repetível")
    ap.add_argument(
        "--pausa", type=int, default=3000, help="ms entre telas (rate limit)"
    )
    ap.add_argument("--sem-mobile", action="store_true")
    ap.add_argument("--sem-detalhes", action="store_true")
    ap.add_argument(
        "--rota",
        action="append",
        default=[],
        help="caminho avulso (repetível); ignora --grupo",
    )
    ap.add_argument("--tema", choices=["light", "dark"], help="força o tema")
    ap.add_argument(
        "--cookie",
        default=os.environ.get("COOKIE_SESSAO"),
        help="cookie de sessão do Better Auth (valor puro ou nome=valor)",
    )
    args = ap.parse_args()

    grupos = args.grupo or list(ROTAS)
    return asyncio.run(
        executar(
            args.base.rstrip("/"),
            grupos,
            args.pausa,
            not args.sem_mobile,
            not args.sem_detalhes,
            args.cookie,
            args.tema,
            args.rota,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
