"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Largura em px de um elemento, acompanhada por `ResizeObserver`.
 *
 * `undefined` até a primeira medição (servidor e 1º render): quem decide O
 * QUE montar a partir dela trata `undefined` como "ainda não sei", como o
 * `useMediaQuery`. Media query não serve aqui: a conversa em `/atendimento`
 * mora entre dois sidebars e uma lista redimensionável — a largura que
 * importa é a do próprio elemento, não a da janela.
 */
export function useLarguraElemento<T extends HTMLElement>(): [
  React.RefObject<T | null>,
  number | undefined,
] {
  const ref = useRef<T | null>(null);
  const [largura, setLargura] = useState<number | undefined>(undefined);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width;
      if (w !== undefined) setLargura(w);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  return [ref, largura];
}
