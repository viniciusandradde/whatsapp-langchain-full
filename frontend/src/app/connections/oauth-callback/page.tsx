"use client";

import { Suspense, useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { CheckCircle, XCircle } from "lucide-react";

export const dynamic = "force-dynamic";

/**
 * Landing pós-OAuth Meta. Lê ?status + ?state da URL e envia postMessage
 * pra janela pai (que abriu este popup). Pai fecha o popup + segue fluxo.
 *
 * Wrap em Suspense pra satisfazer `useSearchParams()` no Next.js 16 — sem
 * isso o build falha em prerender estático.
 */
function CallbackContent() {
  const params = useSearchParams();
  const status = params.get("status");
  const state = params.get("state");
  const reason = params.get("reason");

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (window.opener) {
      window.opener.postMessage(
        {
          type: "waba_oauth_callback",
          status,
          state,
          reason,
        },
        window.location.origin
      );
      setTimeout(() => window.close(), 600);
    }
  }, [status, state, reason]);

  return (
    <div className="max-w-md space-y-4 rounded-lg border border-border/40 bg-card p-6 text-center shadow-xl">
      {status === "ok" ? (
        <>
          <CheckCircle className="mx-auto h-12 w-12 text-emerald-400" />
          <h1 className="text-lg font-semibold">Autenticação concluída</h1>
          <p className="text-sm text-muted-foreground">
            Você pode fechar esta aba.
          </p>
        </>
      ) : (
        <>
          <XCircle className="mx-auto h-12 w-12 text-rose-400" />
          <h1 className="text-lg font-semibold">Não foi possível conectar</h1>
          <p className="text-sm text-muted-foreground">
            {reason || "Algo deu errado. Feche esta aba e tente novamente."}
          </p>
        </>
      )}
    </div>
  );
}

export default function OAuthCallbackPage() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4">
      <Suspense
        fallback={
          <div className="max-w-md rounded-lg border border-border/40 bg-card p-6 text-center text-sm text-muted-foreground">
            Carregando...
          </div>
        }
      >
        <CallbackContent />
      </Suspense>
    </div>
  );
}
