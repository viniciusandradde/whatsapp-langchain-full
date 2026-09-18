"use client";

import { useCallback, useMemo, useSyncExternalStore } from "react";

/**
 * Estado espelhado no `localStorage` — preferência POR NAVEGADOR (modo de
 * agrupamento, grupos abertos, largura de coluna), nunca dado.
 *
 * `useSyncExternalStore` com o storage como fonte (o mesmo desenho do som da
 * fila em `fila-live.tsx`): o snapshot do servidor é o `inicial`, então o
 * HTML hidrata igual e o React troca pro valor salvo logo depois — sem
 * `setState` dentro de efeito (o React Compiler reprova) e sem mismatch.
 * Leitura e escrita ficam em `try/catch` porque o storage pode estar
 * bloqueado (janela privada, quota) — aí a tela funciona, só não lembra.
 *
 * `inicial` precisa ser ESTÁVEL (constante de módulo, não literal no
 * render): ele entra no `useMemo` que desserializa o snapshot.
 */

const ouvintes = new Map<string, Set<() => void>>();

function assinar(chave: string) {
  return (cb: () => void) => {
    let set = ouvintes.get(chave);
    if (!set) {
      set = new Set();
      ouvintes.set(chave, set);
    }
    set.add(cb);
    // Outra aba do painel mudou a preferência: acompanha.
    const externo = (e: StorageEvent) => {
      if (e.key === chave || e.key === null) {
        memoria.delete(chave);
        cb();
      }
    };
    window.addEventListener("storage", externo);
    return () => {
      set?.delete(cb);
      window.removeEventListener("storage", externo);
    };
  };
}

function notificar(chave: string) {
  ouvintes.get(chave)?.forEach((cb) => cb());
}

// Espelho em memória: quando o storage está bloqueado, a preferência ainda
// vale enquanto a aba viver — senão o clique não fazia nada.
const memoria = new Map<string, string>();

function lerBruto(chave: string): string | null {
  const local = memoria.get(chave);
  if (local !== undefined) return local;
  try {
    return window.localStorage.getItem(chave);
  } catch {
    return null;
  }
}

function desserializar<T>(bruto: string | null, inicial: T): T {
  if (bruto === null) return inicial;
  try {
    return JSON.parse(bruto) as T;
  } catch {
    return inicial;
  }
}

export function useLocalStorage<T>(
  chave: string,
  inicial: T
): [T, (valor: T | ((anterior: T) => T)) => void] {
  const subscribe = useMemo(() => assinar(chave), [chave]);
  const bruto = useSyncExternalStore(
    subscribe,
    () => lerBruto(chave),
    () => null
  );
  const valor = useMemo(() => desserializar(bruto, inicial), [bruto, inicial]);

  const setValor = useCallback(
    (proximo: T | ((anterior: T) => T)) => {
      const anterior = desserializar(lerBruto(chave), inicial);
      const novo =
        typeof proximo === "function"
          ? (proximo as (anterior: T) => T)(anterior)
          : proximo;
      const serializado = JSON.stringify(novo);
      memoria.set(chave, serializado);
      try {
        window.localStorage.setItem(chave, serializado);
      } catch {
        // sem storage: fica só no espelho em memória
      }
      notificar(chave);
    },
    [chave, inicial]
  );

  return [valor, setValor];
}
