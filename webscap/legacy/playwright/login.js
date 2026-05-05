/**
 * login.js — abre o ZigChat headed, espera você logar à mão e salva
 * storageState em auth.json. Roda uma vez por PC. O capture.js depois
 * reusa essa sessão sem precisar de password.
 *
 * Uso:
 *   npm install
 *   npx playwright install chromium
 *   npm run login
 *   (logue manualmente, depois aperte Enter no terminal)
 */
import { chromium } from "playwright";
import readline from "node:readline";

const BASE_URL = "https://dev.zigchat.com.br";

async function waitForEnter(message) {
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  return new Promise((resolve) => rl.question(message, () => { rl.close(); resolve(); }));
}

(async () => {
  const browser = await chromium.launch({ headless: false });
  const ctx = await browser.newContext();
  const page = await ctx.newPage();
  await page.goto(BASE_URL);

  console.log("\n→ Faça login na janela do navegador.");
  console.log("→ Depois que estiver dentro do dashboard, volte aqui.");
  await waitForEnter("\nEnter pra salvar a sessão... ");

  await ctx.storageState({ path: "auth.json" });
  console.log("✓ Sessão salva em auth.json");
  await browser.close();
})();
