"use client";

/**
 * PlanoContext — o plano EFETIVO da empresa ativa para toda a árvore de
 * Client Components (ADR-005 leva D): é o que põe o cadeado no menu e nos
 * interruptores e o que o `/billing` mostra como "plano atual".
 *
 * Vem mesclado com as exceções por empresa (`feature_flag` `plano.<chave>`),
 * então a tela trava exatamente o que a rota trava. Carregado no servidor
 * pelo `layout.tsx` (sem flash); trocar de empresa refaz o layout.
 *
 * Uso: `const { plano, liberada } = usePlano();` ou o `usePlanoGate(chave)`
 * de `cadeado-plano.tsx`, que já embala toast e rótulo.
 */

import { createContext, useContext, useMemo, type ReactNode } from "react";

import type { PlanoEmpresa } from "@/lib/api";
import { featureLiberada } from "@/lib/plano";

interface PlanoContextValue {
  /** `null` fora de rota autenticada ou quando a API falhou. */
  plano: PlanoEmpresa | null;
  /** True quando a chave está no plano (ou o plano não pôde ser lido). */
  liberada: (chave: string) => boolean;
  /** Teto do recurso contado; `null` = ilimitado; `undefined` = desconhecido. */
  limite: (recurso: string) => number | null | undefined;
}

const PlanoContext = createContext<PlanoContextValue | null>(null);

export function PlanoProvider({
  plano,
  children,
}: {
  plano: PlanoEmpresa | null;
  children: ReactNode;
}) {
  const value = useMemo<PlanoContextValue>(
    () => ({
      plano,
      // Plano ilegível = liberado, como o worker faz (`plano_libera`): o
      // cadeado é orientação; quem decide de verdade é o 402 da rota.
      liberada: (chave) => (plano ? featureLiberada(plano.features, chave) : true),
      limite: (recurso) => (plano ? plano.limites[recurso] : undefined),
    }),
    [plano]
  );
  return <PlanoContext.Provider value={value}>{children}</PlanoContext.Provider>;
}

export function usePlano(): PlanoContextValue {
  const ctx = useContext(PlanoContext);
  if (!ctx) {
    // Fora do Provider (ex.: /login): nada trava, nada some.
    return { plano: null, liberada: () => true, limite: () => undefined };
  }
  return ctx;
}
