"use client";

import { useState, useTransition } from "react";
import { Loader2, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { Aba } from "@/lib/api";

import { createAbaAction, updateAbaAction } from "./actions";

const CORES = [
  "#64748b", // slate
  "#dc2626", // red
  "#ea580c", // orange
  "#ca8a04", // yellow
  "#16a34a", // green
  "#0891b2", // cyan
  "#2563eb", // blue
  "#9333ea", // purple
  "#db2777", // pink
];

interface Props {
  aba: Aba | null; // null = criar nova
  onClose: (refreshed: boolean) => void;
}

export function AbaModal({ aba, onClose }: Props) {
  const isEdit = aba !== null;
  const [descricao, setDescricao] = useState(aba?.descricao ?? "");
  const [cor, setCor] = useState<string | null>(aba?.cor ?? "#64748b");
  const [error, setError] = useState<string | null>(null);
  const [, startTransition] = useTransition();
  const [submitting, setSubmitting] = useState(false);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const desc = descricao.trim();
    if (!desc) {
      setError("Informe um nome.");
      return;
    }
    setError(null);
    setSubmitting(true);
    startTransition(async () => {
      const result = isEdit
        ? await updateAbaAction(aba!.id, { descricao: desc, cor })
        : await createAbaAction({ descricao: desc, cor });
      setSubmitting(false);
      if (result.ok) {
        onClose(true);
      } else {
        setError(result.error);
      }
    });
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={() => onClose(false)}
    >
      <div
        className="w-full max-w-md rounded-lg border bg-background shadow-lg"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b p-4">
          <h2 className="text-lg font-semibold">
            {isEdit ? "Editar aba" : "Nova aba"}
          </h2>
          <Button
            size="sm"
            variant="ghost"
            className="h-7 w-7 p-0"
            onClick={() => onClose(false)}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 p-4">
          <div>
            <label className="mb-1 block text-sm font-medium">
              Nome <span className="text-destructive">*</span>
            </label>
            <input
              type="text"
              autoFocus
              maxLength={80}
              value={descricao}
              onChange={(e) => setDescricao(e.target.value)}
              placeholder="Ex: VIPs, Pendentes hoje, Urgentes"
              className="w-full rounded-md border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-primary"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium">Cor</label>
            <div className="flex flex-wrap gap-2">
              {CORES.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setCor(c)}
                  className="h-7 w-7 rounded-full border-2 transition-all"
                  style={{
                    backgroundColor: c,
                    borderColor: cor === c ? "#fff" : "transparent",
                    boxShadow: cor === c ? `0 0 0 2px ${c}` : undefined,
                  }}
                  aria-label={`Cor ${c}`}
                />
              ))}
            </div>
          </div>

          {error && (
            <p className="text-sm text-destructive">{error}</p>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => onClose(false)}
              disabled={submitting}
            >
              Cancelar
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              {isEdit ? "Salvar" : "Criar aba"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
