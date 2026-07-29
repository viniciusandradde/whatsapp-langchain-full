"use client";

import { useState, useTransition } from "react";
import { MessagesSquare } from "lucide-react";

import { Button } from "@/components/ui/button";

import { patchConexaoAction } from "../actions";

const inputCls =
  "h-9 w-full rounded-md border border-border/40 bg-background px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring";

interface Props {
  conexaoId: number;
  initialAgrupamento: number;
}

export function RespostaPanel({ conexaoId, initialAgrupamento }: Props) {
  const [segundos, setSegundos] = useState<string>(String(initialAgrupamento));
  const [msg, setMsg] = useState<string | null>(null);
  const [saving, startSaving] = useTransition();

  function handleSave() {
    setMsg(null);
    const n = segundos.trim() === "" ? 0 : parseInt(segundos, 10);
    if (isNaN(n) || n < 0 || n > 60) {
      setMsg("Informe um valor entre 0 e 60 segundos.");
      return;
    }
    startSaving(async () => {
      const r = await patchConexaoAction(conexaoId, {
        resposta_agrupamento_segundos: n,
      });
      setMsg(r.ok ? "✓ Salvo." : `Erro: ${r.error}`);
    });
  }

  const n = parseInt(segundos, 10);
  const desligado = !isNaN(n) && n === 0;

  return (
    <div className="rounded-lg border border-border/40 p-4 space-y-4">
      <div className="flex items-center gap-2">
        <MessagesSquare className="h-5 w-5 text-sky-400" />
        <div>
          <div className="font-medium">Resposta — agrupar mensagens seguidas</div>
          <p className="text-xs text-muted-foreground">
            Evita que o agente responda a cada mensagem quando o cliente escreve
            em pedaços (&quot;oi&quot; / &quot;bom dia&quot; / &quot;queria saber
            de X&quot;).
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div>
          <label className="text-xs uppercase tracking-wide text-muted-foreground">
            Aguardar antes de responder (segundos)
          </label>
          <input
            type="number"
            min={0}
            max={60}
            inputMode="numeric"
            value={segundos}
            onChange={(e) => setSegundos(e.target.value)}
            className={`${inputCls} mt-1`}
          />
        </div>
        <div className="flex items-end">
          <p className="text-xs text-muted-foreground">
            {desligado
              ? "Desligado — o agente responde cada mensagem separadamente."
              : "A primeira mensagem continua respondida na hora. As seguintes esperam esse tempo e viram uma resposta só."}
          </p>
        </div>
      </div>

      <p className="text-xs text-muted-foreground">
        Menus, formulários de coleta e a nota de satisfação não esperam — ali o
        agente responde na hora, porque cada mensagem é resposta a uma pergunta.
      </p>

      <div className="flex items-center gap-3">
        <Button onClick={handleSave} disabled={saving} size="sm">
          {saving ? "Salvando…" : "Salvar"}
        </Button>
        {msg && (
          <span
            className={
              msg.startsWith("Erro")
                ? "text-sm text-destructive"
                : "text-sm text-emerald-400"
            }
          >
            {msg}
          </span>
        )}
      </div>
    </div>
  );
}
