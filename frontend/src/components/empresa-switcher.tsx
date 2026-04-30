"use client";

import { useState, useTransition } from "react";
import { ChevronDown, Building2 } from "lucide-react";
import { useRouter } from "next/navigation";

import { setActiveEmpresa } from "@/lib/empresa-actions";
import type { Empresa } from "@/lib/api";
import { cn } from "@/lib/utils";

interface EmpresaSwitcherProps {
  empresas: Empresa[];
  activeEmpresaId: number | null;
}

/**
 * Dropdown de empresas — visível só quando há mais de uma empresa OU o
 * usuário é superadmin (caso hidratado a partir da listagem). Não renderiza
 * nada quando há apenas 1 empresa pra evitar ruído visual em single-tenant.
 */
export function EmpresaSwitcher({
  empresas,
  activeEmpresaId,
}: EmpresaSwitcherProps) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [isPending, startTransition] = useTransition();

  if (empresas.length <= 1) {
    return null;
  }

  const active =
    empresas.find((e) => e.id === activeEmpresaId) ?? empresas[0];

  function handleSelect(id: number) {
    setOpen(false);
    if (id === active.id) return;
    startTransition(async () => {
      await setActiveEmpresa(id);
      router.refresh();
    });
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        disabled={isPending}
        className={cn(
          "flex w-full items-center justify-between gap-2 rounded-lg",
          "border border-white/[0.08] bg-white/[0.02] px-3 py-2",
          "text-left text-sm text-foreground transition-all",
          "hover:bg-white/[0.05] hover:border-white/15",
          "focus:outline-none focus:ring-2 focus:ring-brand-primary/30",
          isPending && "opacity-60 pointer-events-none",
          open && "bg-white/[0.05] border-white/15"
        )}
      >
        <div className="flex items-center gap-2 min-w-0">
          <Building2 className="h-4 w-4 text-brand-primary shrink-0" />
          <span className="truncate font-medium">{active.nome}</span>
        </div>
        <ChevronDown
          className={cn(
            "h-3.5 w-3.5 text-muted-foreground transition-transform",
            open && "rotate-180"
          )}
        />
      </button>

      {open && (
        <div
          className="absolute left-0 right-0 top-full mt-1 z-50 overflow-hidden rounded-lg border border-white/10 bg-obsidian-800 shadow-vsa-xl"
          onMouseLeave={() => setOpen(false)}
        >
          <ul className="py-1 max-h-64 overflow-auto">
            {empresas.map((e) => {
              const isActive = e.id === active.id;
              return (
                <li key={e.id}>
                  <button
                    type="button"
                    onClick={() => handleSelect(e.id)}
                    className={cn(
                      "flex w-full items-center gap-2 px-3 py-2 text-left text-sm transition-colors",
                      isActive
                        ? "bg-brand-primary/10 text-brand-primary"
                        : "text-foreground/80 hover:bg-white/[0.05] hover:text-foreground"
                    )}
                  >
                    {isActive && (
                      <span className="h-1.5 w-1.5 rounded-full bg-brand-primary shrink-0" />
                    )}
                    <span className={cn("truncate", !isActive && "ml-[14px]")}>
                      {e.nome}
                    </span>
                    <span className="ml-auto text-[11px] text-muted-foreground">
                      {e.plano}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
