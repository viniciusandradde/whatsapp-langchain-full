import { AlertCircle, ArrowUpCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * Sprint F.2 — exibição padronizada de erro de API.
 *
 * Sanitiza mensagens do backend pra não vazar stack trace nem internos
 * (ex: "API error: 422 - [object Object]" → mensagem clara). Detecta
 * estrutura {detail: {message, error, upgrade_to}} do Sprint Q.3 e
 * mostra UI apropriada pra 402 (quota/feature).
 *
 * @example
 *   try { await criarConexao(...) }
 *   catch (e) { return <ApiError error={e} /> }
 */
export interface ApiErrorProps {
  /** Erro lançado por fetch/apiFetch. Pode ser Error ou objeto qualquer. */
  error: unknown;
  /** Título customizado (default: "Algo deu errado"). */
  title?: string;
  /** Mostra detalhes técnicos pro user copiar pro suporte. */
  showTechnicalDetails?: boolean;
  /** Callback quando user clica "Tentar de novo". */
  onRetry?: () => void;
  /** request_id pra mostrar pro suporte. */
  requestId?: string;
  /** Variante visual. */
  variant?: "inline" | "card";
  className?: string;
}

interface ParsedError {
  message: string;
  code?: string;
  upgradeTo?: string | null;
  isQuotaError: boolean;
  raw: unknown;
}

function parseError(error: unknown): ParsedError {
  // Caso 1: Error padrão com .message
  if (error instanceof Error) {
    return _tryParseMessage(error.message, error);
  }
  // Caso 2: objeto direto com .detail (Pydantic)
  if (typeof error === "object" && error !== null) {
    const obj = error as Record<string, unknown>;
    if (obj.detail) {
      const detail = obj.detail;
      if (typeof detail === "string") {
        return _tryParseMessage(detail, error);
      }
      if (typeof detail === "object" && detail !== null) {
        const d = detail as Record<string, unknown>;
        const msg = (d.message as string) || (d.error as string) || JSON.stringify(d);
        const isQuota =
          d.error === "quota_exceeded" || d.error === "feature_unavailable";
        return {
          message: msg,
          code: typeof d.error === "string" ? d.error : undefined,
          upgradeTo: typeof d.upgrade_to === "string" ? d.upgrade_to : null,
          isQuotaError: isQuota,
          raw: error,
        };
      }
    }
    if (typeof obj.message === "string") {
      return _tryParseMessage(obj.message, error);
    }
  }
  // Fallback: string genérica
  return {
    message: String(error || "Erro desconhecido"),
    isQuotaError: false,
    raw: error,
  };
}

function _tryParseMessage(message: string, raw: unknown): ParsedError {
  // Detecta padrão "API error: 402 - {detail JSON}"
  const match = message.match(/^API error: (\d+) - (.+)$/);
  if (match) {
    const status = parseInt(match[1], 10);
    try {
      const parsed = JSON.parse(match[2]);
      // Re-roteia se for objeto Pydantic detail
      if (parsed && typeof parsed === "object") {
        const inner = parseError({ detail: parsed.detail || parsed });
        if (status === 402) inner.isQuotaError = true;
        return inner;
      }
    } catch {
      // Não é JSON — usa string crua
    }
    return {
      message: match[2] || `HTTP ${status}`,
      isQuotaError: status === 402,
      raw,
    };
  }
  return { message, isQuotaError: false, raw };
}

export function ApiError({
  error,
  title,
  showTechnicalDetails = false,
  onRetry,
  requestId,
  variant = "inline",
  className,
}: ApiErrorProps) {
  const parsed = parseError(error);

  const wrapperClass =
    variant === "card"
      ? "rounded-lg border border-destructive/40 bg-destructive/5 p-4"
      : "rounded-md border border-destructive/30 bg-destructive/10 p-3";

  return (
    <div
      role="alert"
      aria-live="polite"
      className={cn(wrapperClass, className)}
    >
      <div className="flex items-start gap-2.5">
        <AlertCircle
          className={cn(
            "shrink-0 text-destructive",
            variant === "card" ? "size-5 mt-0.5" : "size-4 mt-0.5"
          )}
        />
        <div className="flex-1 space-y-1.5">
          <p
            className={cn(
              "font-medium text-destructive",
              variant === "card" ? "text-base" : "text-sm"
            )}
          >
            {title || (parsed.isQuotaError ? "Limite do plano atingido" : "Algo deu errado")}
          </p>
          <p className="text-sm text-foreground/80">{parsed.message}</p>
          {requestId && (
            <p className="font-mono text-[11px] text-muted-foreground">
              Código: {requestId}
            </p>
          )}
          {parsed.isQuotaError && parsed.upgradeTo && (
            <div className="pt-1.5">
              <a
                href="/billing"
                className="inline-flex h-8 items-center justify-center gap-1.5 rounded-md border border-white/15 px-3 text-xs font-medium hover:bg-white/5"
              >
                <ArrowUpCircle className="size-3.5" />
                Upgrade pra {parsed.upgradeTo.charAt(0).toUpperCase() + parsed.upgradeTo.slice(1)}
              </a>
            </div>
          )}
          {onRetry && (
            <div className="pt-1.5">
              <Button size="sm" variant="outline" onClick={onRetry}>
                Tentar de novo
              </Button>
            </div>
          )}
          {showTechnicalDetails && (
            <details className="pt-1.5 text-[11px]">
              <summary className="cursor-pointer text-muted-foreground">
                Detalhes técnicos
              </summary>
              <pre className="mt-1 max-h-32 overflow-auto rounded border border-white/10 bg-obsidian-800 p-2">
                {JSON.stringify(parsed.raw, null, 2)}
              </pre>
            </details>
          )}
        </div>
      </div>
    </div>
  );
}
