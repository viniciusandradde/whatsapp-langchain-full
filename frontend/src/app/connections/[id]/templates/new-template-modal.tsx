"use client";

import { useMemo, useState } from "react";
import { Loader2, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import type {
  WabaTemplateCategoria,
  WabaTemplateComponent,
} from "@/lib/api";

import { createTemplateAction } from "./actions";

interface Props {
  conexaoId: number;
  onClose: (refresh: boolean) => void;
}

const inputCls =
  "flex h-9 w-full rounded-md border border-border/40 bg-background px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring";

export function NewTemplateModal({ conexaoId, onClose }: Props) {
  const [nome, setNome] = useState("");
  const [categoria, setCategoria] = useState<WabaTemplateCategoria>("UTILITY");
  const [idioma, setIdioma] = useState("pt_BR");
  const [headerText, setHeaderText] = useState("");
  const [bodyText, setBodyText] = useState(
    "Olá {{1}}! Seu pedido {{2}} foi confirmado."
  );
  const [footerText, setFooterText] = useState("");
  const [examples, setExamples] = useState("João, 12345");
  const [submitToMeta, setSubmitToMeta] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const variableCount = useMemo(() => {
    const matches = bodyText.match(/\{\{\d+\}\}/g) || [];
    return new Set(matches).size;
  }, [bodyText]);

  const exampleArr = examples
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);

  function buildComponents(): WabaTemplateComponent[] {
    const comps: WabaTemplateComponent[] = [];
    if (headerText.trim()) {
      comps.push({ type: "HEADER", format: "TEXT", text: headerText.trim() });
    }
    comps.push({
      type: "BODY",
      text: bodyText.trim(),
      ...(exampleArr.length > 0
        ? { example: { body_text: [exampleArr] } }
        : {}),
    });
    if (footerText.trim()) {
      comps.push({ type: "FOOTER", text: footerText.trim() });
    }
    return comps;
  }

  async function handleSubmit(submit: boolean) {
    if (!nome.match(/^[a-z][a-z0-9_]*$/)) {
      setError("Nome inválido: use snake_case (ex: confirmacao_pedido).");
      return;
    }
    if (!bodyText.trim()) {
      setError("Texto do BODY é obrigatório.");
      return;
    }
    if (variableCount > 0 && exampleArr.length < variableCount) {
      setError(
        `Forneça ${variableCount} exemplo(s), separados por vírgula (1 por variável).`
      );
      return;
    }
    setError(null);
    setBusy(true);
    const r = await createTemplateAction(conexaoId, {
      nome: nome.trim(),
      categoria,
      idioma,
      componentes_json: buildComponents(),
      submit,
    });
    setBusy(false);
    if (r.ok) onClose(true);
    else setError(r.error);
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onClick={() => onClose(false)}
    >
      <div
        className="w-full max-w-2xl rounded-lg border border-border/40 bg-background shadow-2xl"
        onClick={(e: React.MouseEvent<HTMLDivElement>) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-border/40 p-4">
          <h2 className="text-lg font-semibold">Novo template HSM</h2>
          <Button
            size="sm"
            variant="ghost"
            className="h-7 w-7 p-0"
            onClick={() => onClose(false)}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>

        <div className="max-h-[70vh] space-y-4 overflow-y-auto p-4">
          <div className="grid grid-cols-3 gap-3">
            <div>
              <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Nome *
              </label>
              <input
                className={inputCls}
                value={nome}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                  setNome(e.target.value.toLowerCase())
                }
                placeholder="confirmacao_pedido"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Categoria
              </label>
              <select
                value={categoria}
                onChange={(e: React.ChangeEvent<HTMLSelectElement>) =>
                  setCategoria(e.target.value as WabaTemplateCategoria)
                }
                className="h-9 w-full rounded-md border border-border/40 bg-background px-2 text-sm"
              >
                <option value="UTILITY">Utility</option>
                <option value="AUTHENTICATION">Authentication</option>
                <option value="MARKETING">Marketing</option>
              </select>
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Idioma
              </label>
              <select
                value={idioma}
                onChange={(e: React.ChangeEvent<HTMLSelectElement>) =>
                  setIdioma(e.target.value)
                }
                className="h-9 w-full rounded-md border border-border/40 bg-background px-2 text-sm"
              >
                <option value="pt_BR">Português (Brasil)</option>
                <option value="en_US">English (US)</option>
                <option value="es">Español</option>
              </select>
            </div>
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-muted-foreground">
              HEADER (opcional, texto)
            </label>
            <input
              className={inputCls}
              value={headerText}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                setHeaderText(e.target.value)
              }
              maxLength={60}
              placeholder="Ex: Confirmação"
            />
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-muted-foreground">
              BODY * — use {"{{1}}, {{2}}"} pra variáveis
            </label>
            <textarea
              value={bodyText}
              onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) =>
                setBodyText(e.target.value)
              }
              rows={4}
              maxLength={1024}
              className="w-full rounded-md border border-border/40 bg-background p-2 text-sm"
            />
            <p className="mt-1 text-[11px] text-muted-foreground">
              {variableCount} variável{variableCount === 1 ? "" : "is"} detectada
              {variableCount === 1 ? "" : "s"}.
            </p>
          </div>

          {variableCount > 0 && (
            <div>
              <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-muted-foreground">
                Exemplos das variáveis (separar por vírgula, na ordem)
              </label>
              <input
                className={inputCls}
                value={examples}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                  setExamples(e.target.value)
                }
                placeholder="João, 12345"
              />
              <p className="mt-1 text-[11px] text-muted-foreground">
                Meta exige exemplo pra cada variável. Use valores reais ou plausíveis.
              </p>
            </div>
          )}

          <div>
            <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-muted-foreground">
              FOOTER (opcional)
            </label>
            <input
              className={inputCls}
              value={footerText}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                setFooterText(e.target.value)
              }
              maxLength={60}
              placeholder="Ex: Equipe Suporte"
            />
          </div>

          {/* Preview */}
          <div>
            <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Preview
            </label>
            <div className="rounded-lg border border-border/40 bg-emerald-50/5 p-3 text-sm">
              {headerText && <div className="font-semibold">{headerText}</div>}
              <div className="whitespace-pre-line">
                {bodyText.replace(/\{\{(\d+)\}\}/g, (_, n) => {
                  const idx = parseInt(n, 10) - 1;
                  return exampleArr[idx]
                    ? `[${exampleArr[idx]}]`
                    : `{{${n}}}`;
                })}
              </div>
              {footerText && (
                <div className="mt-1 text-xs text-muted-foreground">
                  {footerText}
                </div>
              )}
            </div>
          </div>

          {error && (
            <div className="rounded-md border border-destructive/50 bg-destructive/10 p-2 text-xs text-destructive">
              {error}
            </div>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-border/40 p-4">
          <label className="flex items-center gap-2 text-xs">
            <input
              type="checkbox"
              checked={submitToMeta}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                setSubmitToMeta(e.target.checked)
              }
            />
            Submeter pra aprovação Meta
          </label>
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => onClose(false)}
              disabled={busy}
            >
              Cancelar
            </Button>
            <Button
              onClick={() => handleSubmit(submitToMeta)}
              disabled={busy}
            >
              {busy && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
              {submitToMeta ? "Submeter" : "Salvar rascunho"}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
