"use client";

import { useMemo, useState } from "react";
import { Loader2, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { WabaTemplate } from "@/lib/api";

import { testSendTemplateAction } from "./actions";

interface Props {
  conexaoId: number;
  template: WabaTemplate;
  onClose: () => void;
}

const inputCls =
  "flex h-9 w-full rounded-md border border-border/40 bg-background px-3 py-1 text-sm shadow-sm";

export function TestSendModal({ conexaoId, template, onClose }: Props) {
  const variableCount = useMemo(() => {
    const text = (
      template.componentes_json.find((c) => c.type === "BODY")?.text || ""
    );
    const matches = text.match(/\{\{\d+\}\}/g) || [];
    return new Set(matches).size;
  }, [template]);

  const [toNumber, setToNumber] = useState("");
  const [variables, setVariables] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function handleSend() {
    if (!toNumber.match(/^\+?\d{10,}$/)) {
      setError("Número inválido. Use formato E.164 (+5511999990000).");
      return;
    }
    setError(null);
    setResult(null);
    setBusy(true);
    const r = await testSendTemplateAction(conexaoId, template.id, {
      to_number: toNumber,
      variables,
    });
    setBusy(false);
    if (r.ok) {
      setResult(`✓ Enviado! message_id: ${r.data.message_id}`);
    } else {
      setError(r.error);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-lg border border-border/40 bg-background shadow-2xl"
        onClick={(e: React.MouseEvent<HTMLDivElement>) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border/40 p-4">
          <h2 className="text-lg font-semibold">Testar envio</h2>
          <Button
            size="sm"
            variant="ghost"
            className="h-7 w-7 p-0"
            onClick={onClose}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="space-y-3 p-4">
          <div>
            <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Template
            </label>
            <p className="text-sm font-mono">{template.nome}</p>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Número destino *
            </label>
            <input
              className={inputCls}
              value={toNumber}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                setToNumber(e.target.value)
              }
              placeholder="+5511999990000"
            />
          </div>

          {variableCount > 0 && (
            <div className="space-y-2">
              <label className="block text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Variáveis
              </label>
              {Array.from({ length: variableCount }, (_, i) => (
                <div key={i}>
                  <label className="block text-xs text-muted-foreground">
                    {`{{${i + 1}}}`}
                  </label>
                  <input
                    className={inputCls}
                    value={variables[String(i + 1)] || ""}
                    onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                      setVariables((prev) => ({
                        ...prev,
                        [String(i + 1)]: e.target.value,
                      }))
                    }
                  />
                </div>
              ))}
            </div>
          )}

          {error && (
            <div className="rounded-md border border-destructive/50 bg-destructive/10 p-2 text-xs text-destructive">
              {error}
            </div>
          )}
          {result && (
            <div className="rounded-md border border-emerald-500/50 bg-emerald-500/10 p-2 text-xs text-emerald-300">
              {result}
            </div>
          )}

          <div className="flex justify-end gap-2 pt-2">
            <Button variant="outline" onClick={onClose}>
              Fechar
            </Button>
            <Button onClick={handleSend} disabled={busy}>
              {busy && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
              Enviar
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
