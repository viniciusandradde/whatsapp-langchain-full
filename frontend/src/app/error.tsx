"use client";

import { useEffect } from "react";
import Link from "next/link";
import { AlertCircle, Home, RotateCcw } from "lucide-react";

import { Button } from "@/components/ui/button";

/**
 * Sprint F.1 — error boundary global.
 *
 * Captura runtime errors do React. Mostra UI amigável + botão "Tentar de
 * novo" (reset prop) + link pra home. Em prod esconde stack trace
 * (apenas digest pra suporte). Em dev mostra mensagem completa.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    // Log no console pra desenvolvedor
    console.error("Global error boundary:", error);
  }, [error]);

  const isDev = process.env.NODE_ENV === "development";

  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-6 p-8 text-center">
      <div className="flex size-24 items-center justify-center rounded-full bg-destructive/10">
        <AlertCircle className="size-12 text-destructive" />
      </div>
      <div className="space-y-2">
        <h1 className="text-4xl font-bold tracking-tight">Ops!</h1>
        <p className="text-lg font-semibold">Algo deu errado</p>
        <p className="max-w-md text-sm text-muted-foreground">
          A página encontrou um erro inesperado. Tente recarregar — se
          continuar acontecendo, contate o suporte com o código abaixo.
        </p>
      </div>

      {/* Digest pra suporte (Next gera automaticamente em prod) */}
      {error.digest && (
        <div className="rounded-md border border-white/10 bg-obsidian-800 px-3 py-1.5 text-xs">
          <span className="text-muted-foreground">Código: </span>
          <code className="font-mono text-foreground">{error.digest}</code>
        </div>
      )}

      {/* Em dev, mostra stack pra debug */}
      {isDev && error.message && (
        <details className="mt-2 max-w-2xl text-left text-xs">
          <summary className="cursor-pointer text-muted-foreground">
            Detalhes do erro (apenas dev)
          </summary>
          <pre className="mt-2 overflow-auto rounded-md border border-white/10 bg-obsidian-800 p-3 text-destructive">
            {error.message}
            {error.stack && "\n\n" + error.stack}
          </pre>
        </details>
      )}

      <div className="flex flex-wrap gap-2">
        <Button onClick={reset}>
          <RotateCcw className="mr-1.5 size-4" />
          Tentar de novo
        </Button>
        <Link
          href="/dashboard/atendimento"
          className="inline-flex h-9 items-center justify-center gap-1.5 rounded-md border border-white/15 bg-transparent px-4 text-sm font-medium hover:bg-white/5"
        >
          <Home className="size-4" />
          Voltar pra Home
        </Link>
      </div>
    </div>
  );
}
