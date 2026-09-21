"use client";

/**
 * Cadeado de plano nas telas (ADR-005 leva D, padrão D2): o recurso fora do
 * plano NÃO some — fica visível, com cadeado, e o toque explica em qual
 * plano ele está e leva ao `/billing`. É o mesmo desenho do seletor de
 * modelos (`seletor-modelo.tsx`): `aria-disabled` + toast, nunca `disabled`
 * (o leitor de tela precisa achar o controle, e o Playwright clica com
 * `force`).
 *
 * Só a transição desligado→ligado é travada, como no backend: o que já está
 * gravado de um plano antigo continua salvável — quem degrada é o worker.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { Lock } from "lucide-react";
import { toast } from "sonner";
import type { MouseEvent } from "react";

import type { PlanoEmpresa } from "@/lib/api";
import { featureLiberada, linkBilling, mensagemBloqueio, rotuloPlano } from "@/lib/plano";
import { loadPlanoEmpresaAction } from "@/lib/plano-actions";
import { cn } from "@/lib/utils";

import { usePlano } from "./plano-context";

/**
 * Plano efetivo de OUTRA empresa que não a ativa — o form de
 * `/companies/[id]` (superadmin edita qualquer uma). `null` enquanto carrega
 * ou se falhar: nada trava até saber. Sem id (empresa nova) não consulta.
 */
export function usePlanoDaEmpresa(empresaId: number | null | undefined): PlanoEmpresa | null {
  const q = useQuery({
    queryKey: ["plano-empresa", empresaId],
    queryFn: async () => {
      const r = await loadPlanoEmpresaAction(empresaId!);
      if (!r.ok) throw new Error(r.error);
      return r.plano;
    },
    enabled: !!empresaId,
    staleTime: 60_000,
  });
  return q.data ?? null;
}

export interface PlanoGate {
  /** True quando a chave NÃO está no plano. */
  bloqueado: boolean;
  plano: PlanoEmpresa | null;
  /** Toast padrão + atalho para o `/billing` da chave. */
  avisar: () => void;
  link: string;
  /**
   * `onClick` para `<input type="checkbox">` cru: cancela só quando o toque
   * LIGA o interruptor (desligar continua livre).
   */
  aoClicarNativo: (e: MouseEvent<HTMLInputElement>) => void;
  /**
   * `onCheckedChange` para o `Checkbox` do kit (Base UI): `details.cancel()`
   * reverte a marcação antes de o estado mudar.
   */
  aoMudarKit: (marcado: boolean, details: { cancel: () => void }) => void;
}

/**
 * @param chave chave de `plano.features` (`csat`, `fewshot`, …)
 * @param planoExplicito plano de OUTRA empresa (form de `/companies/[id]`);
 *   `undefined` usa a empresa ativa; `null` = ainda carregando → nada trava.
 */
export function usePlanoGate(chave: string, planoExplicito?: PlanoEmpresa | null): PlanoGate {
  const router = useRouter();
  const ctx = usePlano();
  const plano = planoExplicito === undefined ? ctx.plano : planoExplicito;
  const bloqueado = plano ? !featureLiberada(plano.features, chave) : false;
  const link = linkBilling(chave);

  const avisar = () => {
    if (!plano) return;
    toast.info(mensagemBloqueio(chave, plano.nome, plano.upgrade_sugerido), {
      action: { label: "Ver planos", onClick: () => router.push(link) },
    });
  };

  return {
    bloqueado,
    plano,
    avisar,
    link,
    aoClicarNativo: (e) => {
      // No `click` o navegador já virou o valor: `checked` é o PRÓXIMO estado.
      if (bloqueado && e.currentTarget.checked) {
        e.preventDefault();
        avisar();
      }
    },
    aoMudarKit: (marcado, details) => {
      if (bloqueado && marcado) {
        details.cancel();
        avisar();
      }
    },
  };
}

/**
 * Dica inline ao lado do controle travado: "Não está no plano Free · a
 * partir do Pro", com cadeado, levando ao `/billing`. Não renderiza nada
 * quando o recurso está liberado.
 */
export function DicaPlano({
  gate,
  className,
}: {
  gate: Pick<PlanoGate, "bloqueado" | "plano" | "link">;
  className?: string;
}) {
  if (!gate.bloqueado || !gate.plano) return null;
  const upgrade = gate.plano.upgrade_sugerido;
  return (
    <Link
      href={gate.link}
      prefetch={false}
      className={cn(
        "inline-flex items-center gap-1 text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline",
        className
      )}
    >
      <Lock className="size-3 shrink-0" aria-hidden />
      Não está no plano {gate.plano.nome}
      {upgrade ? ` · a partir do ${rotuloPlano(upgrade)}` : ""}
    </Link>
  );
}
