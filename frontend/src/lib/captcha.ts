import { APIError } from "better-auth/api";
import type { BetterAuthPlugin } from "better-auth";
import { createAuthMiddleware } from "better-auth/api";

/**
 * reCAPTCHA no login (camada de segurança, 2026-09-19).
 *
 * Plugin do Better Auth que exige um token do reCAPTCHA no `POST
 * /sign-in/email` (e `/sign-up/email`) quando a chamada vem de um NAVEGADOR
 * — o formulário de login (`components/login-form.tsx`) executa o reCAPTCHA
 * Enterprise (chave por pontuação, invisível) e manda o token no header
 * `x-captcha-response`. O app Android continua entrando sem captcha: ele não
 * manda `Origin` (cliente nativo), e o SDK Android do reCAPTCHA fica para
 * uma leva própria. O rate limit do Better Auth (15 tentativas / 15 min por
 * IP) segue valendo para todo mundo.
 *
 * Verificação (uma das duas, pela env):
 * - `RECAPTCHA_API_KEY` + `GOOGLE_CLOUD_PROJECT_ID` → reCAPTCHA Enterprise
 *   `createAssessment` (o recomendado pelo Google; a API que o dono ativou).
 * - `RECAPTCHA_SECRET_KEY` → `siteverify` legado (a "chave secreta legada"
 *   que o console Enterprise também dá; serve de plano B).
 * O interruptor geral é `RECAPTCHA_SITE_KEY`: sem ela, nada muda no login.
 *
 * Falhas: token ausente num pedido de navegador → 400; token inválido,
 * ação errada ou pontuação abaixo de `RECAPTCHA_MIN_SCORE` (0,5) → 403; o
 * Google fora do ar ou credencial recusada → **deixa passar** com erro no
 * log — trancar o hospital inteiro por uma indisponibilidade do Google é
 * pior que ficar 5 minutos só com o rate limit. Por que não o plugin
 * `captcha` do Better Auth: ele só fala o `siteverify` legado e não sabe
 * distinguir o app do navegador.
 */

export const ACAO_LOGIN = "LOGIN";

const ENDPOINTS_PROTEGIDOS = ["/sign-in/email", "/sign-up/email"];
const TIMEOUT_MS = 8_000;

export interface ConfigCaptcha {
  siteKey: string;
  apiKey?: string;
  projectId?: string;
  secretKey?: string;
  minScore: number;
}

export function configCaptcha(env: NodeJS.ProcessEnv = process.env): ConfigCaptcha | null {
  const siteKey = (env.RECAPTCHA_SITE_KEY || "").trim();
  if (!siteKey) return null;
  const minScore = Number(env.RECAPTCHA_MIN_SCORE);
  return {
    siteKey,
    apiKey: (env.RECAPTCHA_API_KEY || "").trim() || undefined,
    projectId: (env.GOOGLE_CLOUD_PROJECT_ID || "").trim() || undefined,
    secretKey: (env.RECAPTCHA_SECRET_KEY || "").trim() || undefined,
    minScore: Number.isFinite(minScore) && minScore >= 0 && minScore <= 1 ? minScore : 0.5,
  };
}

export type Veredito =
  | { ok: true; score: number | null }
  | { ok: false; motivo: string }
  | { indisponivel: true; motivo: string };

async function comTimeout(url: string, init: RequestInit): Promise<Response> {
  const ctrl = new AbortController();
  const t = setTimeout(() => ctrl.abort(), TIMEOUT_MS);
  try {
    return await fetch(url, { ...init, signal: ctrl.signal, cache: "no-store" });
  } finally {
    clearTimeout(t);
  }
}

/** reCAPTCHA Enterprise: `projects.assessments.create` com API key. */
async function avaliarEnterprise(
  cfg: ConfigCaptcha,
  token: string,
  ip: string | undefined,
  acao: string
): Promise<Veredito> {
  const url =
    `https://recaptchaenterprise.googleapis.com/v1/projects/${encodeURIComponent(cfg.projectId!)}` +
    `/assessments?key=${encodeURIComponent(cfg.apiKey!)}`;
  const r = await comTimeout(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      event: {
        token,
        siteKey: cfg.siteKey,
        expectedAction: acao,
        ...(ip ? { userIpAddress: ip } : {}),
      },
    }),
  });
  if (!r.ok) {
    // 400/403 aqui é configuração (API key sem permissão, projeto errado),
    // não um humano suspeito: fica registrado e o login segue.
    const corpo = await r.text().catch(() => "");
    return { indisponivel: true, motivo: `HTTP ${r.status} ${corpo.slice(0, 200)}` };
  }
  const j = (await r.json()) as {
    tokenProperties?: { valid?: boolean; invalidReason?: string; action?: string };
    riskAnalysis?: { score?: number; reasons?: string[] };
  };
  const props = j.tokenProperties ?? {};
  if (!props.valid) return { ok: false, motivo: `token inválido (${props.invalidReason ?? "?"})` };
  if (props.action && props.action !== acao) {
    return { ok: false, motivo: `ação inesperada (${props.action})` };
  }
  const score = typeof j.riskAnalysis?.score === "number" ? j.riskAnalysis.score : null;
  if (score !== null && score < cfg.minScore) {
    return { ok: false, motivo: `pontuação ${score} < ${cfg.minScore}` };
  }
  return { ok: true, score };
}

/** `siteverify` legado (chave secreta legada do console Enterprise). */
async function avaliarLegado(
  cfg: ConfigCaptcha,
  token: string,
  ip: string | undefined,
  acao: string
): Promise<Veredito> {
  const body = new URLSearchParams({ secret: cfg.secretKey!, response: token });
  if (ip) body.set("remoteip", ip);
  const r = await comTimeout("https://www.google.com/recaptcha/api/siteverify", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body,
  });
  if (!r.ok) return { indisponivel: true, motivo: `HTTP ${r.status}` };
  const j = (await r.json()) as {
    success?: boolean;
    score?: number;
    action?: string;
    "error-codes"?: string[];
  };
  const erros = j["error-codes"] ?? [];
  // Segredo errado/ausente é configuração nossa, não o usuário.
  if (erros.some((e) => e === "invalid-input-secret" || e === "missing-input-secret")) {
    return { indisponivel: true, motivo: erros.join(",") };
  }
  if (!j.success) return { ok: false, motivo: erros.join(",") || "success=false" };
  if (j.action && j.action !== acao) return { ok: false, motivo: `ação inesperada (${j.action})` };
  const score = typeof j.score === "number" ? j.score : null;
  if (score !== null && score < cfg.minScore) {
    return { ok: false, motivo: `pontuação ${score} < ${cfg.minScore}` };
  }
  return { ok: true, score };
}

export async function verificarCaptcha(
  cfg: ConfigCaptcha,
  token: string,
  ip: string | undefined,
  acao: string = ACAO_LOGIN
): Promise<Veredito> {
  try {
    if (cfg.apiKey && cfg.projectId) return await avaliarEnterprise(cfg, token, ip, acao);
    if (cfg.secretKey) return await avaliarLegado(cfg, token, ip, acao);
    return { indisponivel: true, motivo: "sem RECAPTCHA_API_KEY+GOOGLE_CLOUD_PROJECT_ID nem RECAPTCHA_SECRET_KEY" };
  } catch (e) {
    return { indisponivel: true, motivo: e instanceof Error ? e.message : String(e) };
  }
}

function ipDe(headers: Headers | undefined): string | undefined {
  const xff = headers?.get("x-forwarded-for");
  if (xff) return xff.split(",")[0]?.trim() || undefined;
  return headers?.get("x-real-ip") ?? undefined;
}

/** Pedido de navegador: `fetch`/form manda `Origin`; o app nativo não. */
function vemDeNavegador(headers: Headers | undefined): boolean {
  return !!headers?.get("origin");
}

export function captchaLogin(): BetterAuthPlugin {
  return {
    id: "captcha-login",
    hooks: {
      before: [
        {
          matcher: (ctx) => ENDPOINTS_PROTEGIDOS.some((p) => ctx.path?.startsWith(p)),
          handler: createAuthMiddleware(async (ctx) => {
            const cfg = configCaptcha();
            if (!cfg) return;
            const headers = ctx.headers ?? ctx.request?.headers;
            if (!vemDeNavegador(headers)) return;

            const token = headers?.get("x-captcha-response")?.trim();
            if (!token) {
              throw new APIError("BAD_REQUEST", {
                message: "Verificação de segurança ausente. Recarregue a página e tente de novo.",
                code: "CAPTCHA_AUSENTE",
              });
            }
            const veredito = await verificarCaptcha(cfg, token, ipDe(headers), ACAO_LOGIN);
            if ("indisponivel" in veredito) {
              console.error("[captcha] verificação indisponível — login liberado:", veredito.motivo);
              return;
            }
            if (!veredito.ok) {
              console.warn("[captcha] login recusado:", veredito.motivo, "ip:", ipDe(headers));
              throw new APIError("FORBIDDEN", {
                message: "Não foi possível confirmar que você não é um robô. Tente de novo.",
                code: "CAPTCHA_RECUSADO",
              });
            }
          }),
        },
      ],
    },
  };
}
