/**
 * Retry exponencial com jitter — pra qualquer operação que pode falhar
 * por flake de rede ou 5xx do upstream.
 *
 * Não retenta em 4xx (exceto 408/425/429): erro do nosso lado, retry
 * só amplifica.
 */

import { log } from "./logger.js";

export interface RetryOptions {
  maxAttempts: number;
  baseMs: number;
  /** Cap pra delay total (default 30s). */
  maxDelayMs?: number;
  /** Default: retenta em status 408/425/429/5xx ou erro de rede. */
  shouldRetry?: (err: unknown) => boolean;
}

export class RetryError extends Error {
  constructor(
    msg: string,
    public readonly attempts: number,
    public readonly lastError: unknown,
  ) {
    super(msg);
    this.name = "RetryError";
  }
}

const DEFAULT_RETRY_STATUS = new Set([408, 425, 429, 500, 502, 503, 504]);

export function defaultShouldRetry(err: unknown): boolean {
  if (err instanceof Error) {
    const msg = err.message.toLowerCase();
    if (
      msg.includes("timeout") ||
      msg.includes("econnreset") ||
      msg.includes("enotfound") ||
      msg.includes("net::") ||
      msg.includes("network")
    )
      return true;
    // Tipo HttpError com .status
    const status = (err as { status?: number }).status;
    if (typeof status === "number") return DEFAULT_RETRY_STATUS.has(status);
  }
  return false;
}

export async function withRetry<T>(
  fn: () => Promise<T>,
  opts: RetryOptions,
  label = "op",
): Promise<T> {
  const maxDelay = opts.maxDelayMs ?? 30_000;
  const shouldRetry = opts.shouldRetry ?? defaultShouldRetry;
  let lastErr: unknown;

  for (let attempt = 1; attempt <= opts.maxAttempts; attempt++) {
    try {
      return await fn();
    } catch (e) {
      lastErr = e;
      const last = attempt === opts.maxAttempts;
      const retry = !last && shouldRetry(e);
      if (!retry) {
        log.debug("retry_giving_up", {
          label,
          attempt,
          last,
          error: String(e),
        });
        throw e;
      }
      // Exponencial com jitter ±20%
      const base = opts.baseMs * 2 ** (attempt - 1);
      const jitter = base * (0.8 + Math.random() * 0.4);
      const delay = Math.min(jitter, maxDelay);
      log.warn("retry_scheduled", {
        label,
        attempt,
        next_in_ms: Math.round(delay),
        error: String(e).slice(0, 120),
      });
      await sleep(delay);
    }
  }

  throw new RetryError(
    `[${label}] esgotou ${opts.maxAttempts} tentativas`,
    opts.maxAttempts,
    lastErr,
  );
}

export function sleep(ms: number): Promise<void> {
  return new Promise((res) => setTimeout(res, ms));
}
