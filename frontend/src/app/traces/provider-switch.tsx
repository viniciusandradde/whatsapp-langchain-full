"use client";

import { useState, useTransition } from "react";
import { Check, Loader2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { ObsProvider } from "@/lib/api";

import { setTracesProviderAction } from "./actions";

interface Props {
  /** O que está gravado (pode ser "auto"). */
  preferido: ObsProvider;
  /** O que vale de fato depois de checar credencial. */
  efetivo: string | null;
  /** Quais têm credencial; sem ela a opção fica desabilitada. */
  disponiveis: { langfuse: boolean; langsmith: boolean };
}

const OPCOES: { valor: ObsProvider; label: string; hint: string }[] = [
  {
    valor: "auto",
    label: "Automático",
    hint: "Usa Langfuse quando disponível, senão LangSmith",
  },
  { valor: "langfuse", label: "Langfuse", hint: "Self-host" },
  { valor: "langsmith", label: "LangSmith", hint: "Nuvem, com amostragem" },
];

/**
 * Escolhe a fonte de traces sem redeploy.
 *
 * A preferência é global (infra compartilhada: uma instância do Langfuse, um
 * projeto do LangSmith), não por empresa.
 */
export function ProviderSwitch({ preferido, efetivo, disponiveis }: Props) {
  const [atual, setAtual] = useState<ObsProvider>(preferido);
  const [erro, setErro] = useState<string | null>(null);
  const [pending, startTransition] = useTransition();

  function escolher(valor: ObsProvider) {
    if (valor === atual || pending) return;
    const anterior = atual;
    setAtual(valor);
    setErro(null);
    startTransition(async () => {
      const r = await setTracesProviderAction(valor);
      if (!r.ok) {
        setAtual(anterior); // desfaz o otimismo
        setErro(r.error);
      }
    });
  }

  function indisponivel(valor: ObsProvider): boolean {
    if (valor === "langfuse") return !disponiveis.langfuse;
    if (valor === "langsmith") return !disponiveis.langsmith;
    return false;
  }

  // Escolha explícita que não pôde ser honrada (ex.: escolheu Langfuse mas o
  // stack está fora). Sem este aviso, o badge mostraria outro provider e
  // pareceria que a troca não salvou.
  const divergente = atual !== "auto" && efetivo !== atual;

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-xs text-muted-foreground">Fonte:</span>
        {OPCOES.map((o) => {
          const off = indisponivel(o.valor);
          const ativo = atual === o.valor;
          return (
            <Button
              key={o.valor}
              type="button"
              size="sm"
              variant={ativo ? "secondary" : "outline"}
              disabled={off || pending}
              onClick={() => escolher(o.valor)}
              title={
                off ? "Sem credencial configurada no ambiente." : o.hint
              }
              className="h-8 text-xs"
            >
              {ativo && !pending ? <Check className="mr-1 h-3 w-3" /> : null}
              {ativo && pending ? (
                <Loader2 className="mr-1 h-3 w-3 animate-spin" />
              ) : null}
              {o.label}
              {off ? (
                <Badge variant="outline" className="ml-1 text-[9px]">
                  sem chave
                </Badge>
              ) : null}
            </Button>
          );
        })}
      </div>

      {divergente ? (
        <p className="text-xs text-amber-600 dark:text-amber-500">
          Escolhido <strong>{atual}</strong>, mas sem credencial no ambiente —
          exibindo <strong>{efetivo ?? "nenhum"}</strong>.
        </p>
      ) : null}

      {erro ? <p className="text-xs text-destructive">{erro}</p> : null}
    </div>
  );
}
