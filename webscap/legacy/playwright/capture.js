/**
 * capture.js — varre rotas do ZigChat, intercepta GraphQL, exporta
 * inventory.json + screenshot por rota.
 *
 * Pré-requisito: auth.json gerado por `npm run login`.
 *
 * Uso:
 *   npm run capture
 *
 * Saída:
 *   output/inventory.json — rotas, componentes, gqlOps, flows
 *   output/shot__<route>.png — screenshot full-page por rota
 */
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";

const BASE_URL = "https://dev.zigchat.com.br";
const ROUTES = [
  "/dashboard/panel",
  "/dashboard/sistema/usuario",
  "/dashboard/cliente",
  "/dashboard/atendimento",
  "/dashboard/conexao",
  "/dashboard/calendario",
  "/dashboard/hk/hook",
  "/dashboard/cp/campanha",
  "/dashboard/ia",
  "/dashboard/arquivo",
];

const OUT_DIR = "output";
fs.mkdirSync(OUT_DIR, { recursive: true });

(async () => {
  if (!fs.existsSync("auth.json")) {
    console.error("auth.json não encontrado — rode `npm run login` primeiro.");
    process.exit(1);
  }

  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({ storageState: "auth.json" });
  const page = await ctx.newPage();

  const inventory = { baseUrl: BASE_URL, routes: [], gqlOps: [], flows: [], capturedAt: new Date().toISOString() };

  // 1) Interceptação GraphQL — request + response
  page.on("request", (req) => {
    if (!req.url().includes("/api/graphql")) return;
    try {
      const body = JSON.parse(req.postData() || "{}");
      inventory.gqlOps.push({
        when: "request",
        operationName: body.operationName,
        variables: body.variables,
        querySnippet: (body.query || "").replace(/\s+/g, " ").slice(0, 400),
        page: page.url(),
      });
    } catch {}
  });

  page.on("response", async (res) => {
    if (!res.url().includes("/api/graphql")) return;
    try {
      const json = await res.json();
      inventory.gqlOps.push({
        when: "response",
        dataKeys: Object.keys(json.data || {}),
        errorCount: (json.errors || []).length,
        status: res.status(),
        page: page.url(),
      });
    } catch {}
  });

  // 2) Varredura por rota
  for (const route of ROUTES) {
    console.log("→", route);
    try {
      await page.goto(BASE_URL + route, { waitUntil: "networkidle", timeout: 30000 });
    } catch (e) {
      console.warn(`  timeout ou erro: ${e.message}`);
    }
    await page.waitForTimeout(1500);

    const comps = await page.evaluate(() => {
      const map = {};
      document.querySelectorAll('[class*="p-"]').forEach((el) => {
        el.classList.forEach((c) => {
          if (c.startsWith("p-") && !c.includes("ng-")) map[c] = (map[c] || 0) + 1;
        });
      });
      return map;
    });

    const navInfo = await page.evaluate(() => {
      const links = [...document.querySelectorAll('a[href^="/"]')]
        .map((a) => ({ href: a.getAttribute("href"), text: a.textContent.trim().slice(0, 60) }))
        .filter((l) => l.href);
      const buttons = [...document.querySelectorAll("button")]
        .map((b) => (b.title || b.textContent || "").trim().slice(0, 60))
        .filter(Boolean);
      const inputs = [...document.querySelectorAll('input, select, textarea')]
        .map((i) => ({
          tag: i.tagName.toLowerCase(),
          type: i.getAttribute("type"),
          name: i.getAttribute("name") || i.getAttribute("formcontrolname"),
          placeholder: i.getAttribute("placeholder"),
        }));
      return { links, buttons, inputs };
    });

    inventory.routes.push({ route, components: comps, ...navInfo });

    const safeName = route.replace(/\//g, "_");
    await page.screenshot({ path: path.join(OUT_DIR, `shot${safeName}.png`), fullPage: true });
  }

  // 3) Fluxo extra: paginação Contatos
  try {
    await page.goto(BASE_URL + "/dashboard/cliente", { waitUntil: "networkidle" });
    await page.getByRole("button", { name: /Ver Mais/i }).click().catch(() => {});
    await page.waitForTimeout(2000);
    inventory.flows.push("contatos:scroll-infinito-ver-mais → filtrarCliente offset+10");
  } catch {}

  // 4) Persistir
  fs.writeFileSync(path.join(OUT_DIR, "inventory.json"), JSON.stringify(inventory, null, 2));
  console.log(`\n✓ ${inventory.routes.length} rotas, ${inventory.gqlOps.length} GraphQL ops capturadas`);
  console.log(`  output/inventory.json`);

  await browser.close();
})();
