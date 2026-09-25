"use client";

import { useSyncExternalStore } from "react";

const semInscricao = () => () => {};

/**
 * `false` no servidor (SSR) e `true` depois de hidratar no navegador — sem
 * `setState` em efeito, que o React Compiler reprova (mesmo motivo do
 * `use-local-storage.ts`). Serve para renderizar no cliente algo que difere do
 * servidor, como hora em fuso local, sem disparar o aviso de hidratação #418.
 */
export function useMontado(): boolean {
  return useSyncExternalStore(
    semInscricao,
    () => true,
    () => false
  );
}
