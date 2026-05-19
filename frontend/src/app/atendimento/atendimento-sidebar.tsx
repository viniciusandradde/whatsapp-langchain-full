"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useState, useTransition } from "react";
import {
  Folder,
  FolderOpen,
  Inbox,
  Loader2,
  MoreHorizontal,
  Pencil,
  Plus,
  Trash2,
  User,
  Users,
  X,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { usePermission } from "@/hooks/use-permission";
import { cn } from "@/lib/utils";
import type { Aba, ContadoresAtendimento } from "@/lib/api";

import { AbaModal } from "./aba-modal";
import {
  deleteAbaAction,
  loadAbasAction,
  loadContadoresAction,
} from "./actions";
import { useAtendimentoShell } from "./atendimento-shell";

type SystemTab = {
  tipo: "aguardando" | "meus" | "outros";
  label: string;
  icon: React.ComponentType<{ className?: string }>;
};

const SYSTEM_TABS: SystemTab[] = [
  { tipo: "aguardando", label: "Aguardando", icon: Inbox },
  { tipo: "meus", label: "Meus", icon: User },
  { tipo: "outros", label: "Outros", icon: Users },
];

interface Props {
  initialContadores: ContadoresAtendimento | null;
  initialAbas: Aba[];
}

/**
 * Sidebar de atendimento — agrupa fila por:
 *  - Sistema: Aguardando / Meus / Outros (status-derived)
 *  - Minhas Abas: pastas customizáveis pelo próprio usuário (mig 085)
 *
 * Lê estado da URL: ?tipo=<system> ou ?aba_id=<id>. Quando `aba_id` está
 * presente, sobrescreve o tipo (mostra só atendimentos pinneados naquela aba
 * do user logado).
 */
export function AtendimentoSidebar({
  initialContadores,
  initialAbas,
}: Props) {
  const router = useRouter();
  const sp = useSearchParams();
  const tipoAtual = sp.get("tipo") ?? "aguardando";
  const abaAtual = sp.get("aba_id");
  const canManageAbas = usePermission("atendimento.aba.manage");

  const [abas, setAbas] = useState<Aba[]>(initialAbas);
  const [contadores, setContadores] =
    useState<ContadoresAtendimento | null>(initialContadores);
  const [modalAba, setModalAba] = useState<Aba | "new" | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [, startTransition] = useTransition();

  const refresh = useCallback(async () => {
    const [a, c] = await Promise.all([
      loadAbasAction(),
      loadContadoresAction(),
    ]);
    if (a.ok) setAbas(a.abas);
    if (c.ok) setContadores(c.contadores);
  }, []);

  // Refresh contadores a cada 30s (fallback se SSE não fizer event).
  useEffect(() => {
    const id = setInterval(refresh, 30_000);
    return () => clearInterval(id);
  }, [refresh]);

  const handleDelete = (aba: Aba) => {
    if (
      !confirm(
        `Excluir a aba "${aba.descricao}"? Os atendimentos vinculados perdem o pin (não são apagados).`
      )
    ) {
      return;
    }
    setDeletingId(aba.id);
    startTransition(async () => {
      const r = await deleteAbaAction(aba.id);
      setDeletingId(null);
      if (r.ok) {
        await refresh();
        // Se estava filtrando por essa aba, volta pra Aguardando
        if (abaAtual === String(aba.id)) {
          router.replace("/atendimento?tipo=aguardando");
        }
      } else {
        alert(`Erro: ${r.error}`);
      }
    });
  };

  const sysCount = (t: SystemTab["tipo"]): number =>
    contadores?.sistema[t] ?? 0;
  const abaCount = (id: number): number =>
    contadores?.abas[String(id)] ?? 0;

  const { state, mobileOpen, closeMobile, isMobile } = useAtendimentoShell();
  const collapsed = !isMobile && state === "collapsed";

  // Em mobile, sidebar inline não aparece — usa overlay
  const showInline = !isMobile;

  const handleNav = () => {
    // Em mobile, fecha overlay ao clicar num item
    if (isMobile) closeMobile();
  };

  const sidebarBody = (
    <>
      <section>
        {!collapsed && (
          <h2 className="mb-2 px-2 text-xs font-semibold uppercase text-muted-foreground">
            Sistema
          </h2>
        )}
        <ul className="space-y-1">
          {SYSTEM_TABS.map((tab) => {
            const Icon = tab.icon;
            const active = !abaAtual && tipoAtual === tab.tipo;
            const count = sysCount(tab.tipo);
            return (
              <li key={tab.tipo}>
                <Link
                  href={`/atendimento?tipo=${tab.tipo}`}
                  onClick={handleNav}
                  title={collapsed ? `${tab.label}${count > 0 ? ` (${count})` : ""}` : undefined}
                  className={cn(
                    "flex items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors",
                    collapsed ? "justify-center" : "justify-between",
                    active
                      ? "bg-brand-primary/10 font-medium text-foreground"
                      : "text-muted-foreground hover:bg-muted/50 hover:text-foreground"
                  )}
                >
                  <span className={cn("flex items-center gap-2", collapsed && "relative")}>
                    <Icon className="h-4 w-4" />
                    {!collapsed && tab.label}
                    {collapsed && count > 0 && (
                      <span className="absolute -right-1.5 -top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-brand-primary px-1 text-[10px] font-semibold text-white">
                        {count > 99 ? "99+" : count}
                      </span>
                    )}
                  </span>
                  {!collapsed && count > 0 && (
                    <Badge variant="secondary" className="h-5 px-1.5 text-xs">
                      {count}
                    </Badge>
                  )}
                </Link>
              </li>
            );
          })}
        </ul>
      </section>

      <section>
        <div
          className={cn(
            "mb-2 flex items-center px-2",
            collapsed ? "justify-center" : "justify-between"
          )}
        >
          {!collapsed && (
            <h2 className="text-xs font-semibold uppercase text-muted-foreground">
              Minhas Abas
            </h2>
          )}
          {canManageAbas && (
            <Button
              size="sm"
              variant="ghost"
              className="h-6 w-6 p-0"
              onClick={() => setModalAba("new")}
              title="Nova aba"
            >
              <Plus className="h-4 w-4" />
            </Button>
          )}
        </div>
        <ul className="space-y-1">
          {abas.length === 0 && !collapsed && (
            <li className="px-2 py-1.5 text-xs text-muted-foreground">
              Nenhuma aba criada ainda.
            </li>
          )}
          {abas.map((aba) => {
            const active = abaAtual === String(aba.id);
            const count = abaCount(aba.id);
            const IconCmp = active ? FolderOpen : Folder;
            return (
              <li key={aba.id} className="group flex items-center gap-1">
                <Link
                  href={`/atendimento?aba_id=${aba.id}`}
                  onClick={handleNav}
                  title={
                    collapsed
                      ? `${aba.descricao}${count > 0 ? ` (${count})` : ""}`
                      : undefined
                  }
                  className={cn(
                    "flex flex-1 items-center gap-2 rounded-md px-2 py-1.5 text-sm transition-colors",
                    collapsed ? "justify-center" : "justify-between",
                    active
                      ? "bg-brand-primary/10 font-medium text-foreground"
                      : "text-muted-foreground hover:bg-muted/50 hover:text-foreground"
                  )}
                >
                  <span
                    className={cn(
                      "flex items-center gap-2 truncate",
                      collapsed && "relative"
                    )}
                  >
                    <IconCmp
                      className="h-4 w-4 shrink-0"
                      style={aba.cor ? { color: aba.cor } : undefined}
                    />
                    {!collapsed && <span className="truncate">{aba.descricao}</span>}
                    {collapsed && count > 0 && (
                      <span className="absolute -right-1.5 -top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-brand-primary px-1 text-[10px] font-semibold text-white">
                        {count > 99 ? "99+" : count}
                      </span>
                    )}
                  </span>
                  {!collapsed && count > 0 && (
                    <Badge variant="secondary" className="h-5 px-1.5 text-xs">
                      {count}
                    </Badge>
                  )}
                </Link>
                {canManageAbas && !collapsed && (
                  <div className="flex shrink-0 opacity-0 transition-opacity group-hover:opacity-100">
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-6 w-6 p-0"
                      onClick={() => setModalAba(aba)}
                      title="Editar"
                    >
                      <Pencil className="h-3 w-3" />
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="h-6 w-6 p-0 hover:text-destructive"
                      onClick={() => handleDelete(aba)}
                      disabled={deletingId === aba.id}
                      title="Excluir"
                    >
                      {deletingId === aba.id ? (
                        <Loader2 className="h-3 w-3 animate-spin" />
                      ) : (
                        <Trash2 className="h-3 w-3" />
                      )}
                    </Button>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
        {!collapsed && contadores && contadores.sem_aba > 0 && (
          <p className="mt-2 px-2 text-xs text-muted-foreground">
            <MoreHorizontal className="mr-1 inline h-3 w-3" />
            {contadores.sem_aba} sem aba
          </p>
        )}
      </section>

      {modalAba !== null && (
        <AbaModal
          aba={modalAba === "new" ? null : modalAba}
          onClose={(refreshed) => {
            setModalAba(null);
            if (refreshed) refresh();
          }}
        />
      )}
    </>
  );

  // Desktop: sidebar inline na flex (w-64 ou w-14 quando collapsed).
  // Cor sólida (não bg-card que é quase transparente no tema dark) +
  // backdrop-blur leve pra dar profundidade contra a área principal.
  if (showInline) {
    return (
      <aside
        className={cn(
          "flex h-full shrink-0 flex-col gap-4 overflow-y-auto border-r bg-background/95 p-3 backdrop-blur transition-[width] duration-200",
          collapsed ? "w-14" : "w-64"
        )}
      >
        {sidebarBody}
      </aside>
    );
  }

  // Mobile: off-canvas (fixed) + backdrop. Não renderiza nada quando fechado.
  // Cor 100% opaca pra não vazar conteúdo da página por trás.
  return (
    <>
      {mobileOpen && (
        <div
          className="fixed inset-0 z-40 bg-black/60 md:hidden"
          onClick={closeMobile}
          aria-hidden
        />
      )}
      <aside
        className={cn(
          "fixed left-0 top-0 z-50 flex h-full w-72 flex-col gap-4 overflow-y-auto border-r bg-background p-4 shadow-2xl transition-transform duration-200 md:hidden",
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        )}
      >
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-base font-semibold">Atendimentos</h2>
          <Button
            size="sm"
            variant="ghost"
            className="h-7 w-7 p-0"
            onClick={closeMobile}
            aria-label="Fechar"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
        {sidebarBody}
      </aside>
    </>
  );
}
