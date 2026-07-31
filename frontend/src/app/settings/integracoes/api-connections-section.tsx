"use client";

import { useState, useTransition } from "react";
import {
  AlertCircle,
  Calendar,
  CheckCircle2,
  ExternalLink,
  Loader2,
  Plug,
  Plus,
  Settings,
  TestTube2,
  Trash2,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import type {
  ApiConnection,
  GoogleCalendarConfig,
  ProviderSpec,
} from "@/lib/api";

import {
  deleteApiConnectionAction,
  disconnectGoogleCalendarAction,
  loadApiConnectionsAction,
  loadApiProvidersAction,
  startGoogleCalendarOAuthAction,
  testApiConnectionAction,
} from "./actions";
import { GoogleCalendarSettingsModal } from "./google-calendar-settings-modal";
import { NewConnectionModal } from "./new-connection-modal";
import { toast } from "sonner";

import { ConfirmDestrutivo } from "@/components/confirm-destrutivo";

interface Props {
  initialConnections: ApiConnection[];
  googleCalendarConfig: GoogleCalendarConfig | null;
}

/**
 * Section unificada "Integrações de API":
 * - Google Calendar (storage legacy, OAuth Web flow)
 * - Conexões cadastradas via api_connection (Custom REST, ...)
 *
 * Tudo na mesma lista visual. Quando user clica "+ Nova conexão" e
 * pickar Google Calendar, dispara OAuth Web flow do Google. Outros
 * providers usam form dinâmico.
 */
export function ApiConnectionsSection({
  initialConnections,
  googleCalendarConfig,
}: Props) {
  const [connections, setConnections] =
    useState<ApiConnection[]>(initialConnections);
  const [googleCfg, setGoogleCfg] = useState<GoogleCalendarConfig | null>(
    googleCalendarConfig,
  );
  const [modalOpen, setModalOpen] = useState(false);
  const [providers, setProviders] = useState<ProviderSpec[]>([]);
  const [loading, setLoading] = useState(false);
  const [testingId, setTestingId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [aRemover, setARemover] = useState<ApiConnection | null>(null);
  const [confirmandoGoogle, setConfirmandoGoogle] = useState(false);
  const [googleBusy, setGoogleBusy] = useState<
    "connecting" | "disconnecting" | null
  >(null);
  const [googleSettingsOpen, setGoogleSettingsOpen] = useState(false);
  const [testResults, setTestResults] = useState<
    Record<number, { ok: boolean; mensagem: string }>
  >({});
  const [, startTransition] = useTransition();

  const openModal = async () => {
    setLoading(true);
    // include_legacy=true: pra Google Calendar aparecer no picker
    const r = await loadApiProvidersAction(true);
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
    setDeletingId(conn.id);
    startTransition(async () => {
      const r = await deleteApiConnectionAction(conn.id);
      setDeletingId(null);
      if (r.ok) {
        setConnections((prev) => prev.filter((c) => c.id !== conn.id));
      } else {
        toast.error(r.error);
      }
    });
  };

  // --- Google Calendar (storage legacy, OAuth Web flow) ---

  const handleGoogleConnect = () => {
    setGoogleBusy("connecting");
    startTransition(async () => {
      const r = await startGoogleCalendarOAuthAction();
      setGoogleBusy(null);
      if (r.ok) {
        window.location.href = r.url;
      } else {
        toast.error(r.error);
      }
    });
  };

  const handleGoogleDisconnect = () => {
    setGoogleBusy("disconnecting");
    startTransition(async () => {
      const r = await disconnectGoogleCalendarAction();
      setGoogleBusy(null);
      if (r.ok) setGoogleCfg(null);
      else toast.error(r.error);
    });
  };

  const hasGoogle = googleCfg !== null;

  return (
    <>
    <div className="rounded-lg border bg-card p-4 md:p-6">
      <div className="mb-4 flex items-start gap-3">
        <div className="rounded-md bg-brand-primary/10 p-2">
          <Plug className="h-5 w-5 text-brand-primary" />
        </div>
        <div className="flex-1">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <h2 className="text-lg font-semibold">Integrações de API</h2>
              <p className="text-sm text-muted-foreground">
                Conecte sua empresa com APIs externas. Suporta Google Calendar
                (OAuth) e qualquer API REST customizada
                (Bearer/Basic/API Key).
              </p>
              <p className="mt-1 text-xs text-muted-foreground">
                Para cobrança da sua assinatura Chat Nexus, use{" "}
                <a href="/billing" className="text-brand-primary hover:underline">
                  Plano &amp; Cobrança
                </a>{" "}
                (gerenciado pelo Chat Nexus via Asaas).
              </p>
            </div>
            <Button onClick={openModal} disabled={loading} size="sm">
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

      <ul className="space-y-2">
        {/* Google Calendar (item especial — storage legacy) */}
        <li className="rounded-md border bg-background p-3">
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <Calendar className="h-4 w-4 text-brand-primary" />
                <span className="font-medium">Google Calendar</span>
                <Badge variant="outline" className="text-xs">
                  OAuth Web
                </Badge>
                {hasGoogle ? (
                  <Badge
                    variant={googleCfg!.ativo ? "default" : "secondary"}
                    className="text-xs"
                  >
                    {googleCfg!.ativo ? "Conectado" : "Inativo"}
                  </Badge>
                ) : (
                  <Badge variant="secondary" className="text-xs">
                    Não conectado
                  </Badge>
                )}
              </div>
              {hasGoogle && (
                <p className="mt-0.5 truncate text-xs text-muted-foreground">
                  {googleCfg!.google_email ?? "—"} · calendário{" "}
                  <code className="rounded bg-muted px-1 text-[10px]">
                    {googleCfg!.calendar_id}
                  </code>{" "}
                  · {googleCfg!.timezone}
                </p>
              )}
              {!hasGoogle && (
                <p className="mt-0.5 text-xs text-muted-foreground">
                  Permite o agente IA criar/cancelar eventos no seu
                  calendário Google.
                </p>
              )}
            </div>
            <div className="flex shrink-0 gap-1">
              {hasGoogle ? (
                <>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setGoogleSettingsOpen(true)}
                    title="Configuração avançada"
                  >
                    <Settings className="h-4 w-4" />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => setConfirmandoGoogle(true)}
                    disabled={googleBusy !== null}
                    className="hover:text-destructive"
                    title="Desconectar"
                  >
                    {googleBusy === "disconnecting" ? (
                      <Loader2 className="h-4 w-4 animate-spin" />
                    ) : (
                      <Trash2 className="h-4 w-4" />
                    )}
                  </Button>
                </>
              ) : (
                <Button
                  size="sm"
                  variant="outline"
                  onClick={handleGoogleConnect}
                  disabled={googleBusy !== null}
                >
                  {googleBusy === "connecting" && (
                    <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                  )}
                  <ExternalLink className="mr-1 h-4 w-4" />
                  Conectar com Google
                </Button>
              )}
            </div>
          </div>
        </li>

        {/* Conexões genéricas (api_connection) */}
        {connections.map((conn) => {
          const tr = testResults[conn.id];
          return (
            <li key={conn.id} className="rounded-md border bg-background p-3">
              <div className="flex flex-wrap items-start justify-between gap-2">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Plug className="h-4 w-4 text-muted-foreground" />
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
                        <CheckCircle2 className="h-3 w-3 text-success" />
                      ) : (
                        <AlertCircle className="h-3 w-3 text-destructive" />
                      )}
                      <span
                        className={
                          (tr?.ok ?? conn.ultimo_teste_ok)
                            ? "text-emerald-700 dark:text-success"
                            : "text-destructive"
                        }
                      >
                        {tr?.mensagem ??
                          (conn.ultimo_teste_ok
                            ? `Testado OK em ${new Date(conn.ultimo_teste_at!).toLocaleString("pt-BR")}`
                            : (conn.ultimo_teste_erro ?? "Falhou"))}
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
                    onClick={() => setARemover(conn)}
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

        {connections.length === 0 && (
          <li className="rounded-md border border-dashed bg-muted/30 p-4 text-center text-xs text-muted-foreground">
            Nenhuma outra conexão cadastrada. Use &ldquo;+ Nova conexão&rdquo;
            pra integrar Google Calendar, uma API REST ou um webhook.
          </li>
        )}
      </ul>

      {modalOpen && (
        <NewConnectionModal
          providers={providers}
          onClose={(refreshed) => {
            setModalOpen(false);
            if (refreshed) void refresh();
          }}
          onGoogleConnect={() => {
            setModalOpen(false);
            handleGoogleConnect();
          }}
        />
      )}
      {googleSettingsOpen && googleCfg && (
        <GoogleCalendarSettingsModal
          config={googleCfg}
          onClose={(updated) => {
            setGoogleSettingsOpen(false);
            if (updated) setGoogleCfg(updated);
          }}
        />
      )}
    </div>

      <ConfirmDestrutivo
        aberto={aRemover !== null}
        onAbertoChange={(v) => !v && setARemover(null)}
        titulo="Remover integração"
        objeto={aRemover ? `${aRemover.label} (${aRemover.provider_nome})` : undefined}
        descricao="As ferramentas do agente que usam esta conexão param de funcionar."
        rotuloAcao="Remover"
        onConfirmar={() => {
          if (aRemover) handleDelete(aRemover);
        }}
      />

      <ConfirmDestrutivo
        aberto={confirmandoGoogle}
        onAbertoChange={setConfirmandoGoogle}
        titulo="Desconectar Google Calendar"
        objeto="a agenda conectada"
        descricao="O agente para de consultar horários e de criar agendamentos até você reconectar."
        rotuloAcao="Desconectar"
        onConfirmar={handleGoogleDisconnect}
      />
    </>
  );
}
