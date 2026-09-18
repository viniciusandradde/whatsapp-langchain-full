"use client";

/**
 * QueryProvider — TanStack Query no painel (Onda 1 do blueprint one-for-all).
 *
 * Por que existe: até aqui a fila viva se atualizava com `router.refresh()`,
 * que re-executa os QUATRO fetches da página inteira a cada evento SSE. Em
 * 16/09/2026 isso gerou 1073 req/min de um único operador e travou o painel no
 * rate limit ("Muitas ações em pouco tempo"). Com Query, o evento invalida uma
 * CHAVE e só a lista afetada revalida.
 *
 * Os defaults abaixo são conservadores de propósito — o objetivo é reduzir
 * requisições, não multiplicá-las:
 *
 * - `refetchOnWindowFocus: false` — é o default do Query, mas ligá-lo aqui
 *   recriaria a tempestade: o operador alterna entre abas o dia inteiro.
 * - `staleTime` de 10s — dentro da janela, alternar de tela não refaz fetch.
 * - `retry` não insiste em erro do cliente (4xx), EXCETO 429, onde espera o
 *   backoff exponencial em vez de martelar (era o circuit breaker manual).
 *
 * Deploy com aba aberta: a `queryFn` é uma Server Action, e Server Action é
 * chamada por um hash que muda a cada build. Depois de um deploy, a aba
 * antiga chama um hash que o servidor novo não conhece — o Next devolve
 * "Failed to find Server Action" e, sem tratamento, a fila congelava em
 * silêncio até alguém recarregar (visto em produção em 18/09/2026, logo após
 * o deploy da #142). `router.refresh()` não sofria disso; o Query sofre. Daí
 * o `onError` global: aba em segundo plano recarrega sozinha (ninguém perde
 * rascunho); aba visível ganha um aviso com botão.
 */

import { useState, type ReactNode } from "react";
import { unstable_isUnrecognizedActionError } from "next/navigation";
import {
  MutationCache,
  QueryCache,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import { toast } from "sonner";

/** 429 = rate limit: vale esperar. Outros 4xx não melhoram com retry. */
function deveTentarDeNovo(falhas: number, erro: unknown): boolean {
  if (unstable_isUnrecognizedActionError(erro)) return false;
  const msg = erro instanceof Error ? erro.message : String(erro ?? "");
  const rateLimit = msg.includes("Muitas ações");
  if (rateLimit) return falhas < 3;
  // Sem status estruturado no erro do apiFetch: mensagens de permissão/sessão
  // não se resolvem repetindo.
  if (msg.includes("permissão") || msg.includes("Sessão expirada")) return false;
  return falhas < 2;
}

let avisouNovaVersao = false;

function tratarErroDeDeploy(erro: unknown): void {
  if (!unstable_isUnrecognizedActionError(erro) || avisouNovaVersao) return;
  avisouNovaVersao = true;
  if (typeof document !== "undefined" && document.visibilityState !== "visible") {
    window.location.reload();
    return;
  }
  toast.warning("Nova versão do painel", {
    description:
      "As atualizações automáticas pararam nesta aba. Recarregue para continuar.",
    duration: Infinity,
    action: { label: "Recarregar", onClick: () => window.location.reload() },
  });
}

export function QueryProvider({ children }: { children: ReactNode }) {
  // useState garante UM client por montagem do app (não por render) e evita
  // compartilhar cache entre requisições no SSR.
  const [client] = useState(
    () =>
      new QueryClient({
        queryCache: new QueryCache({ onError: tratarErroDeDeploy }),
        mutationCache: new MutationCache({ onError: tratarErroDeDeploy }),
        defaultOptions: {
          queries: {
            staleTime: 10_000,
            refetchOnWindowFocus: false,
            retry: deveTentarDeNovo,
            retryDelay: (tentativa) =>
              Math.min(1000 * 2 ** tentativa, 30_000),
          },
        },
      })
  );

  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
