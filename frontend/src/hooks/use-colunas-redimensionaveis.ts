"use client";

import { useCallback, useEffect, useRef } from "react";

import { useLocalStorage } from "./use-local-storage";

export interface LimitesColuna {
  padrao: number;
  min: number;
  max: number;
}

/**
 * Coluna redimensionável por alça (inbox agrupado 2026-09).
 *
 * Largura em px, com limites, persistida em `localStorage` e redefinida no
 * duplo clique da alça. Sem biblioteca: o `react-resizable-panels` trabalha
 * em porcentagem e não casa com "a lista tem no mínimo 320px" — e o arrasto
 * é meia dúzia de linhas de pointer events.
 *
 * Durante o arrasto o `body` recebe `cursor: col-resize` e `user-select:
 * none`, senão o cursor pisca ao passar sobre a conversa e o texto da lista
 * fica selecionado no fim do movimento.
 */
export function useColunaRedimensionavel(
  chave: string,
  limites: LimitesColuna
): {
  largura: number;
  redefinir: () => void;
  alcaProps: {
    onPointerDown: (e: React.PointerEvent) => void;
    onDoubleClick: () => void;
    role: "separator";
    "aria-orientation": "vertical";
    "aria-valuenow": number;
    "aria-valuemin": number;
    "aria-valuemax": number;
  };
} {
  const [largura, setLargura] = useLocalStorage<number>(chave, limites.padrao);
  const arrasto = useRef<{ x0: number; l0: number } | null>(null);

  const limitar = useCallback(
    (px: number) => Math.min(limites.max, Math.max(limites.min, Math.round(px))),
    [limites.max, limites.min]
  );

  useEffect(() => {
    // Largura salva fora dos limites atuais (limites mudaram entre versões).
    if (largura < limites.min || largura > limites.max) setLargura(limitar(largura));
  }, [largura, limites.min, limites.max, limitar, setLargura]);

  const onPointerDown = useCallback(
    (e: React.PointerEvent) => {
      if (e.button !== 0) return;
      e.preventDefault();
      arrasto.current = { x0: e.clientX, l0: largura };
      const body = document.body;
      const cursorAntes = body.style.cursor;
      const selectAntes = body.style.userSelect;
      body.style.cursor = "col-resize";
      body.style.userSelect = "none";

      const mover = (ev: PointerEvent) => {
        if (!arrasto.current) return;
        setLargura(limitar(arrasto.current.l0 + ev.clientX - arrasto.current.x0));
      };
      const soltar = () => {
        arrasto.current = null;
        body.style.cursor = cursorAntes;
        body.style.userSelect = selectAntes;
        window.removeEventListener("pointermove", mover);
        window.removeEventListener("pointerup", soltar);
        window.removeEventListener("pointercancel", soltar);
      };
      window.addEventListener("pointermove", mover);
      window.addEventListener("pointerup", soltar);
      window.addEventListener("pointercancel", soltar);
    },
    [largura, limitar, setLargura]
  );

  const redefinir = useCallback(() => setLargura(limites.padrao), [limites.padrao, setLargura]);

  return {
    largura,
    redefinir,
    alcaProps: {
      onPointerDown,
      onDoubleClick: redefinir,
      role: "separator",
      "aria-orientation": "vertical",
      "aria-valuenow": largura,
      "aria-valuemin": limites.min,
      "aria-valuemax": limites.max,
    },
  };
}
