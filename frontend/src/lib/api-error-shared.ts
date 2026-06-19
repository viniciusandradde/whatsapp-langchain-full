/**
 * Contrato de erro de API compartilhado entre o cliente server-side
 * (`api.ts`, que é `server-only`) e componentes client (`api-error.tsx`).
 *
 * REGRA: mensagem exibida ao usuário NUNCA carrega detalhe técnico
 * (status HTTP, `statusText`, rota `/api/...`, corpo cru, `[object Object]`,
 * stack). O técnico vai só pros logs (`console.*`). A UI mostra a frase
 * pt-BR amigável que o backend manda em `detail`, ou um fallback curto.
 *
 * Por ser puro (sem `server-only` / `next/headers`), pode ser importado
 * dos dois lados sem quebrar o boundary server/client.
 */

/** Fallback curto e neutro por faixa de status, sem vazar nada técnico. */
export function friendlyFallback(status: number): string {
  if (status === 404) return "Item não encontrado.";
  if (status === 408 || status === 504)
    return "A operação demorou demais. Tente novamente.";
  if (status >= 500) return "Erro interno. Tente novamente em instantes.";
  if (status === 400 || status === 422)
    return "Não foi possível concluir a ação. Verifique os dados e tente novamente.";
  return "Não foi possível concluir a ação.";
}

/**
 * Extrai a mensagem amigável de um `detail` do backend (string ou objeto
 * Pydantic `{message,error,upgrade_to}`). Cai no fallback por status quando
 * não há nada exibível. Nunca devolve status/rota.
 */
export function messageFromDetail(status: number, detail: unknown): string {
  if (typeof detail === "string") {
    const s = detail.trim();
    if (s && s !== "[object Object]") return s;
  }
  if (detail && typeof detail === "object") {
    const d = detail as Record<string, unknown>;
    if (typeof d.message === "string" && d.message.trim()) return d.message.trim();
    if (
      typeof d.error === "string" &&
      d.error.trim() &&
      d.error !== "[object Object]"
    )
      return d.error.trim();
  }
  return friendlyFallback(status);
}

/**
 * Versão pra quem só tem o corpo cru da resposta (server actions com `fetch`
 * direto). Tenta achar `detail` no JSON; senão usa o fallback por status.
 */
export function friendlyError(status: number, bodyText: string): string {
  let detail: unknown;
  try {
    const parsed = JSON.parse(bodyText);
    detail =
      parsed && typeof parsed === "object" && "detail" in parsed
        ? (parsed as { detail: unknown }).detail
        : parsed;
  } catch {
    // corpo não-JSON — ignora, usa fallback
  }
  return messageFromDetail(status, detail);
}

/**
 * Erro lançado pelo funil central (`apiFetch`). `message` já é amigável;
 * `status`/`detail`/`path` ficam disponíveis pra lógica (ex: UI de quota 402)
 * e pros logs — nunca pra exibição direta.
 */
export class ApiRequestError extends Error {
  status: number;
  detail: unknown;
  path: string;
  constructor(status: number, detail: unknown, path: string) {
    super(messageFromDetail(status, detail));
    this.name = "ApiRequestError";
    this.status = status;
    this.detail = detail;
    this.path = path;
  }
}

/**
 * Rede de segurança: remove resíduo técnico de uma string de erro que possa
 * ter vindo de código legado (ex: "API error: 400 Bad Request (/api/x) — msg",
 * "API error: 402 - msg", "NNN: msg"). Usado no display como última barreira.
 */
export function stripTechnical(message: string): string {
  if (!message) return message;
  let m = message;
  // "API error: 400 Bad Request (/api/x) — msg" → "msg"
  m = m.replace(/^API error:\s*\d+\s+[^(]*\([^)]*\)\s*(?:—|-)\s*/i, "");
  // "API error: 402 - msg" / "API error 402: msg" → "msg"
  m = m.replace(/^API error:?\s*\d+\s*(?::|—|-)\s*/i, "");
  // route residual "(/api/...)"
  m = m.replace(/\s*\(\/api\/[^)]*\)/g, "");
  // "upstream 502" → genérico
  if (/^upstream\s+\d+$/i.test(m.trim())) return "Não foi possível concluir a ação.";
  const out = m.trim();
  return out || message;
}
