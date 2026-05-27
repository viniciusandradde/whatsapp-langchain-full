"use client";

import { useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import {
  ChevronRight,
  CircleCheck,
  CircleX,
  Clock,
  PlusCircle,
  RotateCw,
  Search,
  Smartphone,
  Star,
  Trash2,
  Wifi,
  WifiOff,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

const inputCls =
  "flex h-9 w-full rounded-md border border-border/40 bg-background px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring";
import type {
  Conexao,
  ConexaoProvider,
  ConnectionState,
} from "@/lib/api";

import {
  deleteConexaoAction,
  disconnectConexaoAction,
  patchConexaoAction,
  testConexaoAction,
} from "./actions";
import { NewConnectionModal } from "./new-connection-modal";

interface Props {
  initialConexoes: Conexao[];
}

const PROVIDER_LABELS: Record<ConexaoProvider, string> = {
  twilio_sandbox: "Twilio Sandbox",
  twilio_prod: "Twilio Prod",
  waba: "WhatsApp Oficial",
  evolution: "Evolution",
};

const STATE_BADGES: Record<
  ConnectionState,
  { label: string; cls: string; icon: typeof Wifi }
> = {
  pending: {
    label: "Pendente",
    cls: "bg-amber-500/15 text-amber-400 border-amber-500/30",
    icon: Clock,
  },
  qr_pending: {
    label: "Aguardando QR",
    cls: "bg-amber-500/15 text-amber-400 border-amber-500/30",
    icon: Clock,
  },
  connecting: {
    label: "Conectando",
    cls: "bg-amber-500/15 text-amber-400 border-amber-500/30",
    icon: RotateCw,
  },
  open: {
    label: "Conectado",
    cls: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
    icon: Wifi,
  },
  ready: {
    label: "Pronto",
    cls: "bg-emerald-500/15 text-emerald-400 border-emerald-500/30",
    icon: CircleCheck,
  },
  disconnected: {
    label: "Desconectado",
    cls: "bg-zinc-500/15 text-zinc-400 border-zinc-500/30",
    icon: WifiOff,
  },
  error: {
    label: "Erro",
    cls: "bg-rose-500/15 text-rose-400 border-rose-500/30",
    icon: CircleX,
  },
};

function StateBadge({ state }: { state: ConnectionState }) {
  const cfg = STATE_BADGES[state] || STATE_BADGES.pending;
  const Icon = cfg.icon;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs",
        cfg.cls
      )}
    >
      <Icon className="h-3 w-3" />
      {cfg.label}
    </span>
  );
}

function ProviderBadge({ provider }: { provider: ConexaoProvider }) {
  return (
    <Badge variant="outline" className="font-normal text-xs">
      {PROVIDER_LABELS[provider]}
    </Badge>
  );
}

export function ConnectionsList({ initialConexoes }: Props) {
  const router = useRouter();
  const [conexoes, setConexoes] = useState<Conexao[]>(initialConexoes);
  const [filter, setFilter] = useState("");
  const [providerFilter, setProviderFilter] = useState<string>("");
  const [showNew, setShowNew] = useState(false);
  const [busy, setBusy] = useState<number | null>(null);
  const [, startTransition] = useTransition();

  const filtered = conexoes.filter((c) => {
    if (
      filter &&
      !c.display_name?.toLowerCase().includes(filter.toLowerCase()) &&
      !c.from_number.includes(filter)
    )
      return false;
    if (providerFilter && c.provider !== providerFilter) return false;
    return true;
  });

  function handleTest(id: number) {
    setBusy(id);
    startTransition(async () => {
      const r = await testConexaoAction(id);
      setBusy(null);
      if (r.ok) {
        alert(r.data.ok ? "✓ Conexão funcionando" : `✗ ${r.data.message}`);
        router.refresh();
      } else {
        alert(`Erro: ${r.error}`);
      }
    });
  }

  function handleDisconnect(id: number) {
    if (!confirm("Desconectar essa conexão? (Sessão WhatsApp será fechada)"))
      return;
    setBusy(id);
    startTransition(async () => {
      const r = await disconnectConexaoAction(id);
      setBusy(null);
      if (r.ok) router.refresh();
      else alert(`Erro: ${r.error}`);
    });
  }

  function handleDelete(id: number) {
    if (!confirm("Excluir conexão? (Soft-delete, histórico preservado)")) return;
    setBusy(id);
    startTransition(async () => {
      const r = await deleteConexaoAction(id);
      setBusy(null);
      if (r.ok) {
        setConexoes((prev) => prev.filter((c) => c.id !== id));
      } else {
        alert(`Erro: ${r.error}`);
      }
    });
  }

  function handleSetDefault(id: number) {
    // Marca conexão como padrão (is_default=true). Backend faz unset batch
    // das outras da mesma empresa automaticamente (single-default invariant).
    setBusy(id);
    startTransition(async () => {
      const r = await patchConexaoAction(id, { is_default: true });
      setBusy(null);
      if (r.ok) {
        // Reflete imediato na UI sem esperar refresh do servidor
        setConexoes((prev) =>
          prev.map((c) => ({
            ...c,
            is_default: c.id === id,
          }))
        );
        router.refresh();
      } else {
        alert(`Erro ao marcar como padrão: ${r.error}`);
      }
    });
  }

  return (
    <>
      {/* Filtros + botão Nova */}
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex-1 min-w-[200px]">
          <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Nome / número
          </label>
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <input
              value={filter}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                setFilter(e.target.value)
              }
              placeholder="Filtrar..."
              className={`${inputCls} pl-9`}
            />
          </div>
        </div>
        <div className="min-w-[160px]">
          <label className="mb-1 block text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Provider
          </label>
          <select
            value={providerFilter}
            onChange={(e) => setProviderFilter(e.target.value)}
            className="h-9 w-full rounded-md border border-border/40 bg-background px-2 text-sm"
          >
            <option value="">Todos</option>
            <option value="waba">WhatsApp Oficial</option>
            <option value="evolution">Evolution</option>
            <option value="twilio_sandbox">Twilio Sandbox</option>
            <option value="twilio_prod">Twilio Prod</option>
          </select>
        </div>
        <Button onClick={() => setShowNew(true)} className="gap-1.5">
          <PlusCircle className="h-4 w-4" />
          Nova conexão
        </Button>
      </div>

      {/* Tabela */}
      <div className="rounded-lg border border-border/40">
        {filtered.length === 0 ? (
          <div className="flex flex-col items-center gap-2 p-12 text-sm text-muted-foreground">
            <Smartphone className="h-8 w-8 opacity-50" />
            <p>Nenhuma conexão cadastrada.</p>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setShowNew(true)}
              className="mt-2"
            >
              Adicionar a primeira
            </Button>
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="border-b border-border/40 bg-muted/20">
              <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
                <th className="px-3 py-2 font-medium">Nome</th>
                <th className="px-3 py-2 font-medium">Número</th>
                <th className="px-3 py-2 font-medium">Provider</th>
                <th className="px-3 py-2 font-medium">Estado</th>
                <th className="px-3 py-2 font-medium">Padrão</th>
                <th className="w-32 px-3 py-2 font-medium text-right">Ações</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((c) => (
                <tr
                  key={c.id}
                  className="border-b border-border/20 last:border-0 hover:bg-muted/10"
                >
                  <td className="px-3 py-2">
                    {c.display_name || (
                      <span className="text-muted-foreground italic">
                        sem nome
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs">
                    {c.from_number.startsWith("evolution:") ? (
                      <span className="text-muted-foreground">
                        (aguardando QR)
                      </span>
                    ) : (
                      c.from_number
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <ProviderBadge provider={c.provider} />
                  </td>
                  <td className="px-3 py-2">
                    <StateBadge
                      state={c.connection_state || "pending"}
                    />
                  </td>
                  <td className="px-3 py-2">
                    <button
                      type="button"
                      onClick={() =>
                        !c.is_default && handleSetDefault(c.id)
                      }
                      disabled={busy === c.id || c.is_default}
                      title={
                        c.is_default
                          ? "Conexão padrão da empresa"
                          : "Marcar como padrão"
                      }
                      className={cn(
                        "inline-flex items-center justify-center rounded-md p-1 transition-colors",
                        c.is_default
                          ? "cursor-default text-amber-400"
                          : "cursor-pointer text-muted-foreground hover:bg-muted/30 hover:text-amber-400",
                        busy === c.id && "opacity-50"
                      )}
                      aria-label={
                        c.is_default ? "Conexão padrão" : "Marcar como padrão"
                      }
                    >
                      <Star
                        className={cn(
                          "h-4 w-4",
                          c.is_default && "fill-amber-400"
                        )}
                      />
                    </button>
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex items-center justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        title="Testar"
                        disabled={busy === c.id}
                        onClick={() => handleTest(c.id)}
                        className="h-7 w-7 p-0"
                      >
                        <CircleCheck className="h-3.5 w-3.5" />
                      </Button>
                      {(c.provider === "evolution" ||
                        c.provider === "waba") && (
                        <Button
                          variant="ghost"
                          size="sm"
                          title="Desconectar"
                          disabled={busy === c.id}
                          onClick={() => handleDisconnect(c.id)}
                          className="h-7 w-7 p-0"
                        >
                          <WifiOff className="h-3.5 w-3.5" />
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        size="sm"
                        title="Detalhes"
                        onClick={() => router.push(`/connections/${c.id}`)}
                        className="h-7 w-7 p-0"
                      >
                        <ChevronRight className="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        title="Excluir"
                        disabled={busy === c.id}
                        onClick={() => handleDelete(c.id)}
                        className="h-7 w-7 p-0 text-rose-400 hover:text-rose-300"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <p className="text-xs text-muted-foreground">
        {filtered.length} {filtered.length === 1 ? "conexão" : "conexões"}
        {filter || providerFilter ? " filtradas" : ""}
      </p>

      {showNew && (
        <NewConnectionModal
          onClose={(refresh) => {
            setShowNew(false);
            if (refresh) router.refresh();
          }}
        />
      )}
    </>
  );
}
