/**
 * Token bucket simples — limita taxa de requests/s pra não tomar 429
 * do upstream. Usado pelo crawler antes de cada navegação.
 *
 * Cap: 1 token = 1 ação. Refil contínuo no rate configurado.
 */

import { sleep } from "../lib/retry.js";

export interface Limiter {
  acquire(): Promise<void>;
}

export function rateLimiter(rps: number, burst = 1): Limiter {
  if (rps <= 0) {
    return { acquire: async () => undefined };
  }
  let tokens = burst;
  let lastRefill = Date.now();
  const refillIntervalMs = 1000 / rps;

  async function acquire(): Promise<void> {
    while (true) {
      // Refil
      const now = Date.now();
      const elapsed = now - lastRefill;
      if (elapsed > 0) {
        const refill = elapsed / refillIntervalMs;
        tokens = Math.min(burst, tokens + refill);
        lastRefill = now;
      }
      if (tokens >= 1) {
        tokens -= 1;
        return;
      }
      // Espera o tempo necessário pra próximo token
      const wait = Math.ceil((1 - tokens) * refillIntervalMs);
      await sleep(Math.max(wait, 5));
    }
  }

  return { acquire };
}
