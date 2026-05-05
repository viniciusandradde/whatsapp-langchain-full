/**
 * Auth interativo: abre browser headed, espera login manual, salva
 * storageState em arquivo (default `auth.json`).
 *
 * Deve rodar 1 vez por máquina/sessão. `auth.json` é git-ignored.
 */

import readline from "node:readline";

import { chromium } from "playwright";

import { log } from "../lib/logger.js";

export interface LoginOptions {
  baseUrl: string;
  storageFile: string;
}

export async function interactiveLogin(opts: LoginOptions): Promise<void> {
  const browser = await chromium.launch({ headless: false });
  try {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    await page.goto(opts.baseUrl);

    log.info("login_browser_opened", { baseUrl: opts.baseUrl });
    console.log("\n→ Faça login na janela do navegador.");
    console.log("→ Quando estiver dentro do dashboard, volte aqui.\n");

    await waitForEnter("Enter pra salvar a sessão... ");

    await ctx.storageState({ path: opts.storageFile });
    log.info("session_saved", { storageFile: opts.storageFile });
  } finally {
    await browser.close();
  }
}

function waitForEnter(message: string): Promise<void> {
  const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
  });
  return new Promise((resolve) => {
    rl.question(message, () => {
      rl.close();
      resolve();
    });
  });
}
