/**
 * Anexa listeners no Page pra interceptar tráfego GraphQL — captura
 * request (operationName/variables/query) + response (status/dataKeys/errors).
 *
 * Não bloqueia/modifica requests; só observa.
 */

import type { Page, Request, Response } from "playwright";

import type { CapturedOperation } from "../types.js";

export interface InterceptorOptions {
  graphqlPath: string;
  /** Trunca query salva em chars pra não inflar inventory.json. */
  querySnippetMaxChars?: number;
}

export function attachGraphqlInterceptor(
  page: Page,
  opts: InterceptorOptions,
): { operations: CapturedOperation[]; detach: () => void } {
  const operations: CapturedOperation[] = [];
  const maxChars = opts.querySnippetMaxChars ?? 400;

  // Map pra correlacionar request → response (mesma URL+timestamp não
  // garante 1:1 mas serve em prática). Em produção poderia hash query.
  const pendingByUrl = new Map<string, CapturedOperation>();

  function isGraphql(url: string): boolean {
    return url.includes(opts.graphqlPath);
  }

  function onRequest(req: Request) {
    if (!isGraphql(req.url())) return;
    try {
      const body = req.postData() ? JSON.parse(req.postData()!) : {};
      const op: CapturedOperation = {
        operationName: body.operationName ?? null,
        variables: body.variables ?? null,
        querySnippet: typeof body.query === "string"
          ? body.query.replace(/\s+/g, " ").slice(0, maxChars)
          : "",
        routeWhereSeen: page.url(),
        capturedAt: new Date().toISOString(),
      };
      operations.push(op);
      pendingByUrl.set(req.url(), op);
    } catch {
      /* JSON inválido — ignora */
    }
  }

  async function onResponse(res: Response) {
    if (!isGraphql(res.url())) return;
    const op = pendingByUrl.get(res.url());
    if (!op) return;
    pendingByUrl.delete(res.url());
    op.status = res.status();
    try {
      const json = await res.json();
      op.dataKeys = json && json.data ? Object.keys(json.data) : [];
      op.errorCount = json && json.errors ? json.errors.length : 0;
    } catch {
      /* response não é JSON — ignora */
    }
  }

  page.on("request", onRequest);
  page.on("response", onResponse);

  return {
    operations,
    detach: () => {
      page.off("request", onRequest);
      page.off("response", onResponse);
    },
  };
}
