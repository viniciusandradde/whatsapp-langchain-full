"use client";

import { useState, useTransition } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Loader2,
  Plug,
  Plus,
  TestTube2,
  Trash2,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type { ApiConnection, ProviderSpec } from "@/lib/api";

import {
  deleteApiConnectionAction,
  loadApiConnectionsAction,
  loadApiProvidersAction,
  testApiConnectionAction,
} from "./actions";
import { NewConnectionModal } from "./new-connection-modal";

interface Props {
  initialConnections: ApiConnection[];
}

/**
 * Section "Conexões de API" — lista conexões cadastradas + botão Nova.
 *
 * Wareline e Google Calendar continuam em cards próprios acima (legacy
 * storage). Esta section cobre todos os providers não-legacy do catálogo.
 */
export function ApiConnectionsSection({ initialConnections }: Props) {
  const [connections, setConnections] =
    useState<ApiConnection[]>(initialConnections);
  const [modalOpen, setModalOpen] = useState(false);
  const [providers, setProviders] = useState<ProviderSpec[]>([]);
  const [loading, setLoading] = useState(false);
  const [testingId, setTestingId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [testResults, setTestResults] = useState<
    Record<number, { ok: boolean; mensagem: string }>
  >({});
  const [, startTransition] = useTransition();

  const openModal = async () => {
    setLoading(true);
    const r = await loadApiProvidersAction(false);
    setLoading(false);
    if (r.ok) {
      setProviders(r.providers);
      setModalOpen(true);
    }
  };

  const refresh = async () => {
    const r = await loadApiConnectionsAction();
    if (r.ok) setConnections(r.connections);
  };

  const handleTest = (id: number) => {
    setTestingId(id);
    startTransition(async () => {
      const r = await testApiConnectionAction(id);
      setTestingId(null);
      setTestResults((prev) => ({
        ...prev,
        [id]: { ok: r.ok, mensagem: r.mensagem },
      }));
      void refresh();
    });
  };

  const handleDelete = (conn: ApiConnection) => {
    if (
      !confirm(
        `Remover conexão "${conn.label}" (${conn.provider_nome})? As tools que usam essa conexão vão parar de funcionar.`
      )
    )
      return;
    setDeletingId(conn.id);
    startTransition(async () => {
      const r = await deleteApiConnectionAction(conn.id);
      setDeletingId(null);
      if (r.ok) {
        setConnections((prev) => prev.filter((c) => c.id !== conn.id));
      } else {
        alert(`Erro: ${r.error}`);
      }
    });
  };

  return (
    <div className="rounded-lg border bg-card p-4 md:p-6">
      <div className="mb-4 flex items-start gap-3">
        <div className="rounded-md bg-brand-primary/10 p-2">
          <Plug className="h-5 w-5 text-brand-primary" />
        </div>
        <div className="flex-1">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="text-lg font-semibold">Conexões de API</h2>
              <p className="text-sm text-muted-foreground">
                Integre o painel com APIs externas (Asaas, custom, etc.).
                Wareline e Google Calendar têm cards próprios acima.
              </p>
            </div>
            <Button
              onClick={openModal}
              disabled={loading}
              size="sm"
            >
              {loading ? (
                <Loader2 className="mr-1 h-4 w-4 animate-spin" />
              ) : (
                <Plus className="mr-1 h-4 w-4" />
              )}
              Nova conexão
            </Button>
          </div>
        </div>
      </div>

      {connections.length === 0 ? (
        <div className="rounded-md border border-dashed bg-muted/30 p-6 text-center text-sm text-muted-foreground">
          Nenhuma conexão cadastrada ainda. Clique em &ldquo;Nova conexão&rdquo;
          pra adicionar.
        </div>
      ) : (
        <ul className="space-y-2">
          {connections.map((conn) => {
            const tr = testResults[conn.id];
            return (
              <li
                key={conn.id}
                className="rounded-md border bg-background p-3"
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{conn.label}</span>
                      <Badge variant="outline" className="text-xs">
                        {conn.provider_nome}
                      </Badge>
                      {!conn.ativo && (
                        <Badge variant="secondary" className="text-xs">
                          Inativa
                        </Badge>
                      )}
                    </div>
                    {conn.base_url && (
                      <p className="mt-0.5 truncate font-mono text-xs text-muted-foreground">
                        {conn.base_url}
                      </p>
                    )}
                    {(tr || conn.ultimo_teste_at) && (
                      <p className="mt-1 flex items-center gap-1 text-xs">
                        {(tr?.ok ?? conn.ultimo_teste_ok) ? (
                          <CheckCircle2 className="h-3 w-3 text-emerald-600 dark:text-emerald-400" />
                        ) : (
                          <AlertCircle className="h-3 w-3 text-destructive" />
                        )}
                        <span
                          className={
                            (tr?.ok ?? conn.ultimo_teste_ok)
                              ? "text-emerald-700 dark:text-emerald-400"
                              : "text-destructive"
                          }
                        >
                          {tr?.mensagem ??
                            (conn.ultimo_teste_ok
                              ? `Testado OK em ${new Date(conn.ultimo_teste_at!).toLocaleString("pt-BR")}`
                              : conn.ultimo_teste_erro ?? "Falhou")}
                        </span>
                      </p>
                    )}
                  </div>
                  <div className="flex shrink-0 gap-1">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => handleTest(conn.id)}
                      disabled={testingId === conn.id || deletingId === conn.id}
                      title="Testar conexão"
                    >
                      {testingId === conn.id ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <TestTube2 className="h-4 w-4" />
                      )}
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => handleDelete(conn)}
                      disabled={testingId === conn.id || deletingId === conn.id}
                      className="hover:text-destructive"
                      title="Remover"
                    >
                      {deletingId === conn.id ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Trash2 className="h-4 w-4" />
                      )}
                    </Button>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}

      {modalOpen && (
        <NewConnectionModal
          providers={providers}
          onClose={(refreshed) => {
            setModalOpen(false);
            if (refreshed) void refresh();
          }}
        />
      )}
    </div>
  );
}
