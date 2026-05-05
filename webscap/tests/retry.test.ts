import { describe, expect, it, vi } from "vitest";

import { defaultShouldRetry, withRetry } from "../src/lib/retry.js";

describe("defaultShouldRetry", () => {
  it("retenta em timeout/connreset/network", () => {
    expect(defaultShouldRetry(new Error("timeout"))).toBe(true);
    expect(defaultShouldRetry(new Error("ECONNRESET"))).toBe(true);
    expect(defaultShouldRetry(new Error("net::ERR_FAILED"))).toBe(true);
  });

  it("retenta em 408/425/429/5xx via .status", () => {
    const err = new Error("rate limited") as Error & { status: number };
    err.status = 429;
    expect(defaultShouldRetry(err)).toBe(true);
    err.status = 503;
    expect(defaultShouldRetry(err)).toBe(true);
    err.status = 404;
    expect(defaultShouldRetry(err)).toBe(false);
  });
});

describe("withRetry", () => {
  it("succede de primeira sem dormir", async () => {
    const fn = vi.fn(async () => 42);
    const r = await withRetry(fn, { maxAttempts: 3, baseMs: 10 });
    expect(r).toBe(42);
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it("retenta até succeder", async () => {
    let calls = 0;
    const fn = vi.fn(async () => {
      calls += 1;
      if (calls < 3) throw new Error("timeout");
      return "ok";
    });
    const r = await withRetry(fn, { maxAttempts: 5, baseMs: 5 });
    expect(r).toBe("ok");
    expect(fn).toHaveBeenCalledTimes(3);
  });

  it("não retenta em erro não-retryable", async () => {
    const fn = vi.fn(async () => {
      throw new Error("ValidationError: campo X");
    });
    await expect(
      withRetry(fn, { maxAttempts: 5, baseMs: 5 }),
    ).rejects.toThrow("ValidationError");
    expect(fn).toHaveBeenCalledTimes(1);
  });

  it("esgota tentativas e lança RetryError", async () => {
    const fn = vi.fn(async () => {
      throw new Error("timeout");
    });
    await expect(
      withRetry(fn, { maxAttempts: 2, baseMs: 5 }),
    ).rejects.toThrow();
    expect(fn).toHaveBeenCalledTimes(2);
  });
});
