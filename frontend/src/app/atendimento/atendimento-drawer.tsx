"use client";

import { useEffect, useRef, useState, useTransition } from "react";
import Link from "next/link";
import {
  CheckCircle2,
  ChevronDown,
  Eraser,
  Hand,
  RefreshCw,
  Send,
  UserPlus,
  X,
  XCircle,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  getDepartamentos,
  type Atendimento,
  type AtendimentoMensagem,
  type Departamento,
  type ModeloMensagem,
} from "@/lib/api";
import { cn } from "@/lib/utils";

import {
  claimAction,
  closeAction,
  loadMensagensAction,
  loadModelosAction,
  resetThreadAction,
  responderAction,
  transferAction,
  transferDepartamentoAction,
} from "./actions";

interface Props {
  atendimento: Atendimento;
  onClose: () => void;
}

const STATUS_LABEL: Record<Atendimento["status"], string> = {
  aguardando: "Aguardando",
  em_andamento: "Em andamento",
  resolvido: "Resolvido",
  abandonado: "Abandonado",
};

function statusVariant(
  status: Atendimento["status"]
): "default" | "secondary" | "destructive" | "outline" {
  if (status === "em_andamento") return "default";
  if (status === "aguardando") return "secondary";
  if (status === "abandonado") return "destructive";
  return "outline";
}

function formatTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("pt-BR");
}

export function AtendimentoDrawer({ atendimento, onClose }: Props) {
  const [mensagens, setMensagens] = useState<AtendimentoMensagem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [composer, setComposer] = useState("");
  const [sending, setSending] = useState(false);
  const [modelos, setModelos] = useState<ModeloMensagem[] | null>(null);
  const [modelosOpen, setModelosOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<"conversa" | "arquivos">("conversa");
  const [isPending, startTransition] = useTransition();

  // Transferência (Sprint V) — popover inline com 2 modos.
  const [transferOpen, setTransferOpen] = useState(false);
  const [transferMode, setTransferMode] = useState<"departamento" | "atendente">(
    "departamento"
  );
  const [transferDepId, setTransferDepId] = useState<number | "">("");
  const [transferUserId, setTransferUserId] = useState("");
  const [departamentos, setDepartamentos] = useState<Departamento[]>([]);
  const [loadingDeps, setLoadingDeps] = useState(false);

  async function reload() {
    setLoading(true);
    setError(null);
    const r = await loadMensagensAction(atendimento.id);
    if (!r.ok) setError(r.error);
    else setMensagens(r.mensagens);
    setLoading(false);
  }

  // Silent reload: usado pelo polling — não toca em `loading` pra evitar
  // flicker no UI a cada 3s. Erros transitórios são engolidos pra não
  // poluir o painel com banner vermelho a cada falha de rede.
  const reloadingRef = useRef(false);
  async function silentReload() {
    if (reloadingRef.current) return;
    reloadingRef.current = true;
    try {
      const r = await loadMensagensAction(atendimento.id);
      if (r.ok) setMensagens(r.mensagens);
    } finally {
      reloadingRef.current = false;
    }
  }

  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [atendimento.id]);

  // E2.E SSE: substitui polling 3s por EventSource. Backend dispara
  // eventos via Postgres LISTEN/NOTIFY (mig 035) — chega <1s do INSERT
  // da mensagem. Fallback automático: EventSource reconecta sozinho se
  // a conexão cair, e em erro fatal a gente cai pra polling 5s como
  // safety net.
  useEffect(() => {
    const isActive =
      atendimento.status === "aguardando" ||
      atendimento.status === "em_andamento";
    if (!isActive) return;

    let es: EventSource | null = null;
    let fallbackTimer: ReturnType<typeof setInterval> | null = null;
    let openedOk = false;

    function startFallbackPolling() {
      if (fallbackTimer) return;
      fallbackTimer = setInterval(() => {
        if (document.visibilityState === "visible") void silentReload();
      }, 5000);
    }

    function stopFallback() {
      if (fallbackTimer) {
        clearInterval(fallbackTimer);
        fallbackTimer = null;
      }
    }

    function connectSse() {
      es = new EventSource(`/api/sse/atendimento/${atendimento.id}`);

      es.addEventListener("connected", () => {
        openedOk = true;
        stopFallback();
        // Sync de baseline (caso tenha perdido eventos antes da conexão)
        void silentReload();
      });

      es.addEventListener("mensagem", () => {
        if (document.visibilityState === "visible") void silentReload();
      });

      es.addEventListener("status_changed", () => {
        if (document.visibilityState === "visible") void silentReload();
      });

      es.onerror = () => {
        // EventSource auto-reconecta. Mas se nunca abriu (ex: 401, 500),
        // entra em loop de reconexão ineficiente — ativa polling fallback
        // após 1ª falha.
        if (!openedOk) startFallbackPolling();
      };
    }

    connectSse();

    return () => {
      es?.close();
      stopFallback();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [atendimento.id, atendimento.status]);

  function runAction(fn: () => Promise<{ ok: true } | { ok: false; error: string }>) {
    setError(null);
    startTransition(async () => {
      const r = await fn();
      if (!r.ok) setError(r.error);
      else onClose();
    });
  }

  // Lazy: carrega departamentos só quando user abre o popover de transferência
  // pela 1ª vez. Evita chamada extra ao abrir um drawer só pra responder.
  useEffect(() => {
    if (!transferOpen || departamentos.length > 0 || loadingDeps) return;
    setLoadingDeps(true);
    getDepartamentos()
      .then((r) => setDepartamentos(r.departamentos.filter((d) => d.ativo)))
      .catch(() => {
        /* silencioso — UI mostra select vazio se falhar */
      })
      .finally(() => setLoadingDeps(false));
  }, [transferOpen, departamentos.length, loadingDeps]);

  const isOpen =
    atendimento.status === "aguardando" || atendimento.status === "em_andamento";

  function handleConfirmTransfer() {
    if (transferMode === "departamento") {
      if (!transferDepId) return;
      runAction(() =>
        transferDepartamentoAction(atendimento.id, Number(transferDepId))
      );
    } else {
      if (!transferUserId.trim()) return;
      runAction(() =>
        transferAction(atendimento.id, transferUserId.trim())
      );
    }
    setTransferOpen(false);
  }

  function handleCancelTransfer() {
    setTransferOpen(false);
    setTransferDepId("");
    setTransferUserId("");
  }

  function handleClose(status: "resolvido" | "abandonado") {
    if (
      !confirm(
        `Fechar atendimento como ${status === "resolvido" ? "resolvido" : "abandonado"}?`
      )
    )
      return;
    runAction(() => closeAction(atendimento.id, status));
  }

  async function handleResetThread() {
    if (
      !confirm(
        "Resetar conversa do agente?\n\n" +
          "Apaga o histórico LangGraph (checkpoint) deste número.\n" +
          "Próxima mensagem começa do zero — útil quando o agente está\n" +
          "replicando padrão errado das últimas respostas.\n\n" +
          "Não afeta: mensagens da timeline, memórias semânticas, dados do cliente."
      )
    )
      return;
    setError(null);
    const r = await resetThreadAction(atendimento.id);
    if (!r.ok) {
      setError(r.error);
      return;
    }
    alert(
      `✅ Conversa resetada (${r.rowsDeleted} rows removidas).\n` +
        `Thread: ${r.threadId}\n\n` +
        "Próxima mensagem do cliente vai começar do zero."
    );
  }

  async function openModelosDropdown() {
    if (modelos === null) {
      const r = await loadModelosAction();
      if (r.ok) setModelos(r.modelos);
      else setError(r.error);
    }
    setModelosOpen((v) => !v);
  }

  function insertModelo(m: ModeloMensagem) {
    setComposer((prev) => (prev ? `${prev}\n${m.conteudo}` : m.conteudo));
    setModelosOpen(false);
  }

  async function handleSend() {
    const text = composer.trim();
    if (!text || sending) return;
    setSending(true);
    setError(null);
    const r = await responderAction(atendimento.id, text);
    if (!r.ok) {
      setError(r.error);
      setSending(false);
      return;
    }
    setComposer("");
    setSending(false);
    // Recarrega timeline para incluir a outbound recém-enviada.
    await reload();
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-stretch justify-end bg-black/50 backdrop-blur-sm"
      onClick={onClose}
    >
      <aside
        className="flex h-full w-full max-w-2xl flex-col bg-card shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="sticky top-0 z-10 flex items-start justify-between gap-3 border-b bg-card p-3 md:p-5">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h2 className="truncate text-lg font-semibold">
                {atendimento.cliente_nome ?? atendimento.cliente_telefone ?? "Cliente"}
              </h2>
              <Badge variant={statusVariant(atendimento.status)}>
                {STATUS_LABEL[atendimento.status]}
              </Badge>
              {atendimento.protocolo && (
                <Badge variant="outline" className="font-mono text-[10px]">
                  #{atendimento.protocolo}
                </Badge>
              )}
              {atendimento.qtde_resposta_invalida > 0 && (
                <Badge
                  variant="outline"
                  className="text-[10px]"
                  title={`Cliente errou ${atendimento.qtde_resposta_invalida}× no menu/CSAT`}
                >
                  ⚠ {atendimento.qtde_resposta_invalida} inválidas
                </Badge>
              )}
              {!atendimento.iniciado_cliente && (
                <Badge
                  variant="outline"
                  className="text-[10px]"
                  title="Atendimento aberto via outbound (operador/campanha)"
                >
                  outbound
                </Badge>
              )}
              {atendimento.solicitou_encerramento && (
                <Badge variant="outline" className="text-[10px]">
                  pediu encerrar
                </Badge>
              )}
            </div>
            <p className="mt-0.5 font-mono text-xs text-muted-foreground">
              {atendimento.cliente_telefone ?? "—"} · atendimento #{atendimento.id} ·{" "}
              {atendimento.agente_atual}
            </p>
            {atendimento.cliente_id && (
              <Link
                href={`/clientes/${atendimento.cliente_id}`}
                className="mt-1 inline-block text-xs text-muted-foreground underline hover:text-foreground"
              >
                Ver ficha do cliente
              </Link>
            )}
          </div>
          <Button variant="ghost" size="icon" onClick={onClose} aria-label="Fechar">
            <X className="size-4" />
          </Button>
        </header>

        <TriagemCard atendimento={atendimento} />

        <div className="flex flex-1 flex-col overflow-hidden">
          <div className="flex items-center justify-between border-b px-5 py-2">
            <div className="flex items-center gap-3 text-xs uppercase tracking-wide">
              <button
                type="button"
                onClick={() => setActiveTab("conversa")}
                className={cn(
                  "border-b-2 px-1 py-1 transition-colors",
                  activeTab === "conversa"
                    ? "border-foreground text-foreground"
                    : "border-transparent text-muted-foreground hover:text-foreground"
                )}
              >
                Conversa
              </button>
              <button
                type="button"
                onClick={() => setActiveTab("arquivos")}
                className={cn(
                  "border-b-2 px-1 py-1 transition-colors",
                  activeTab === "arquivos"
                    ? "border-foreground text-foreground"
                    : "border-transparent text-muted-foreground hover:text-foreground"
                )}
              >
                Arquivos
                {(() => {
                  const count = mensagens?.filter((m) => m.media_url).length ?? 0;
                  return count > 0 ? ` · ${count}` : "";
                })()}
              </button>
            </div>
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => void handleResetThread()}
                disabled={loading || isPending}
                title="Resetar histórico do agente (admin only)"
              >
                <Eraser className="size-3.5" />
                Resetar
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => void reload()}
                disabled={loading}
              >
                <RefreshCw className={cn("size-3.5", loading && "animate-spin")} />
                Atualizar
              </Button>
            </div>
          </div>

          <div className="flex-1 space-y-3 overflow-y-auto px-5 py-4">
            {error && (
              <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
                {error}
              </div>
            )}

            {loading && !mensagens && (
              <p className="text-sm text-muted-foreground">Carregando mensagens…</p>
            )}

            {activeTab === "conversa" && (
              <>
                {!loading && mensagens && mensagens.length === 0 && (
                  <p className="text-sm text-muted-foreground">
                    Nenhuma mensagem registrada para este atendimento ainda.
                  </p>
                )}
                {mensagens?.map((m) => (
                  <MessageBubbles key={m.id} m={m} />
                ))}
              </>
            )}

            {activeTab === "arquivos" && <ArquivosTab mensagens={mensagens} />}
          </div>
        </div>

        {isOpen && (
          <div className="relative border-t bg-background/40 p-3">
            <div className="mb-2 flex items-center justify-between">
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => void openModelosDropdown()}
                disabled={sending}
              >
                <ChevronDown className="size-3.5" />
                Modelos
              </Button>
              {modelosOpen && (
                <div className="absolute bottom-full left-3 z-10 mb-1 max-h-72 w-80 overflow-y-auto rounded-md border bg-popover shadow-lg">
                  {modelos === null ? (
                    <p className="p-3 text-xs text-muted-foreground">
                      Carregando…
                    </p>
                  ) : modelos.length === 0 ? (
                    <p className="p-3 text-xs text-muted-foreground">
                      Nenhum modelo cadastrado. Crie em <strong>/modelos</strong>.
                    </p>
                  ) : (
                    <ul className="py-1">
                      {modelos.map((m) => (
                        <li key={m.id}>
                          <button
                            type="button"
                            onClick={() => insertModelo(m)}
                            className="flex w-full flex-col items-start gap-0.5 px-3 py-2 text-left text-sm hover:bg-accent"
                          >
                            <span className="font-medium">{m.titulo}</span>
                            <span className="line-clamp-2 text-xs text-muted-foreground">
                              {m.conteudo}
                            </span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </div>
            <div className="flex items-end gap-2">
              <textarea
                value={composer}
                onChange={(e) => setComposer(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void handleSend();
                  }
                }}
                placeholder="Digite a resposta para o cliente… (Enter envia, Shift+Enter quebra linha)"
                rows={2}
                disabled={sending}
                className="flex w-full resize-none rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:opacity-60"
              />
              <Button
                onClick={() => void handleSend()}
                disabled={sending || !composer.trim()}
              >
                <Send className="size-3.5" />
                {sending ? "Enviando…" : "Enviar"}
              </Button>
            </div>
          </div>
        )}

        {isOpen && (
          <footer className="flex flex-wrap items-center justify-end gap-2 border-t p-4">
            {atendimento.status === "aguardando" && (
              <Button
                onClick={() => runAction(() => claimAction(atendimento.id))}
                disabled={isPending}
              >
                <Hand className="size-3.5" />
                Atender
              </Button>
            )}
            <div className="relative">
              <Button
                variant="ghost"
                onClick={() => setTransferOpen((v) => !v)}
                disabled={isPending}
              >
                <UserPlus className="size-3.5" />
                Transferir
              </Button>
              {transferOpen && (
                <div className="absolute bottom-full right-0 mb-2 w-80 rounded-md border bg-background p-3 shadow-lg z-10">
                  <div className="mb-2 text-xs font-semibold text-muted-foreground">
                    Transferir atendimento
                  </div>
                  <div className="mb-3 flex gap-3 text-sm">
                    <label className="inline-flex items-center gap-1.5">
                      <input
                        type="radio"
                        checked={transferMode === "departamento"}
                        onChange={() => setTransferMode("departamento")}
                      />
                      Para departamento
                    </label>
                    <label className="inline-flex items-center gap-1.5">
                      <input
                        type="radio"
                        checked={transferMode === "atendente"}
                        onChange={() => setTransferMode("atendente")}
                      />
                      Para atendente
                    </label>
                  </div>
                  {transferMode === "departamento" ? (
                    <select
                      value={transferDepId}
                      onChange={(e) =>
                        setTransferDepId(
                          e.target.value ? Number(e.target.value) : ""
                        )
                      }
                      className="mb-3 w-full rounded-md border border-input bg-background px-2 py-1.5 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                      aria-label="Departamento de destino"
                    >
                      <option value="">
                        {loadingDeps
                          ? "Carregando…"
                          : departamentos.length === 0
                            ? "Nenhum departamento ativo"
                            : "Selecione o departamento"}
                      </option>
                      {departamentos.map((d) => (
                        <option key={d.id} value={d.id}>
                          {d.nome}
                        </option>
                      ))}
                    </select>
                  ) : (
                    <input
                      type="text"
                      value={transferUserId}
                      onChange={(e) => setTransferUserId(e.target.value)}
                      placeholder="user_id (Better Auth)"
                      className="mb-3 w-full rounded-md border border-input bg-background px-2 py-1.5 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                      aria-label="ID do atendente"
                    />
                  )}
                  <div className="flex justify-end gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={handleCancelTransfer}
                      disabled={isPending}
                    >
                      Cancelar
                    </Button>
                    <Button
                      size="sm"
                      onClick={handleConfirmTransfer}
                      disabled={
                        isPending ||
                        (transferMode === "departamento"
                          ? !transferDepId
                          : !transferUserId.trim())
                      }
                    >
                      Confirmar
                    </Button>
                  </div>
                </div>
              )}
            </div>
            <Button
              variant="ghost"
              onClick={() => handleClose("resolvido")}
              disabled={isPending}
            >
              <CheckCircle2 className="size-3.5" />
              Resolver
            </Button>
            <Button
              variant="ghost"
              onClick={() => handleClose("abandonado")}
              disabled={isPending}
            >
              <XCircle className="size-3.5" />
              Abandonar
            </Button>
          </footer>
        )}
      </aside>
    </div>
  );
}

// Card "Triagem IA" — renderiza só quando o agente classificou ou
// gerou resumo. Aparece logo abaixo do header do drawer pra o atendente
// pegar contexto rápido sem ler conversa toda.
function TriagemCard({ atendimento }: { atendimento: Atendimento }) {
  const has =
    atendimento.resumo_ia ||
    atendimento.classificacao ||
    atendimento.prioridade ||
    atendimento.sentimento;
  if (!has) return null;

  const prioColor: Record<string, string> = {
    urgente: "bg-red-500/15 text-red-700 dark:text-red-300 border-red-500/40",
    alta: "bg-orange-500/15 text-orange-700 dark:text-orange-300 border-orange-500/40",
    media: "bg-blue-500/15 text-blue-700 dark:text-blue-300 border-blue-500/40",
    baixa: "bg-muted text-muted-foreground border-muted",
  };
  const sentColor: Record<string, string> = {
    frustrado: "bg-red-500/15 text-red-700 dark:text-red-300 border-red-500/40",
    negativo: "bg-amber-500/15 text-amber-700 dark:text-amber-300 border-amber-500/40",
    neutro: "bg-muted text-muted-foreground border-muted",
    positivo: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border-emerald-500/40",
  };

  return (
    <div className="border-b bg-muted/30 px-5 py-3">
      <div className="mb-2 flex items-center gap-2 text-xs uppercase tracking-wide text-muted-foreground">
        <span>🧠 Triagem IA</span>
        {atendimento.triagem_completa && (
          <Badge variant="outline" className="text-[10px]">
            completa
          </Badge>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        {atendimento.prioridade && (
          <span
            className={`inline-flex items-center rounded border px-2 py-0.5 text-[11px] font-medium ${prioColor[atendimento.prioridade] || ""}`}
          >
            prioridade: {atendimento.prioridade}
          </span>
        )}
        {atendimento.sentimento && (
          <span
            className={`inline-flex items-center rounded border px-2 py-0.5 text-[11px] font-medium ${sentColor[atendimento.sentimento] || ""}`}
          >
            sentimento: {atendimento.sentimento}
          </span>
        )}
        {atendimento.classificacao && (
          <Badge variant="outline" className="text-[10px] font-mono">
            {atendimento.classificacao}
          </Badge>
        )}
      </div>
      {atendimento.resumo_ia && (
        <div className="mt-2 rounded-md bg-background/60 p-2 text-xs">
          <div className="mb-1 font-semibold uppercase text-muted-foreground tracking-wide text-[10px]">
            Resumo do agente
          </div>
          <pre className="whitespace-pre-wrap font-sans leading-relaxed">
            {atendimento.resumo_ia}
          </pre>
        </div>
      )}
    </div>
  );
}

// Aba "Arquivos" — agrega todas as mídias do atendimento (imagens,
// áudios, vídeos, PDFs/documentos) num grid. Filter client-side do array
// `mensagens` que já está carregado — não faz fetch adicional.
function ArquivosTab({
  mensagens,
}: {
  mensagens: AtendimentoMensagem[] | null;
}) {
  const arquivos = (mensagens ?? []).filter((m) => m.media_url);
  if (arquivos.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        Nenhum arquivo enviado neste atendimento.
      </p>
    );
  }
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {arquivos.map((m) => (
        <div
          key={m.id}
          className="rounded-md border bg-muted/20 p-2"
          title={m.created_at ? new Date(m.created_at).toLocaleString() : ""}
        >
          <MediaPreview
            url={m.media_url!}
            type={m.media_type}
            caption={m.incoming_message}
          />
          <p className="mt-1 text-[10px] text-muted-foreground">
            {m.created_at && formatTime(m.created_at)} ·{" "}
            <span className="font-mono">{m.media_type ?? "—"}</span>
          </p>
        </div>
      ))}
    </div>
  );
}

function MessageBubbles({ m }: { m: AtendimentoMensagem }) {
  // Cada row pode gerar bolhas distintas: media (inbound), texto inbound,
  // resposta agente. Mídia é renderizada inline como <img>/<audio>/link.
  type Bubble =
    | { side: "in" | "out"; kind: "text"; text: string; meta?: string }
    | { side: "in"; kind: "media"; mediaUrl: string; mediaType: string | null; caption?: string };

  const bubbles: Bubble[] = [];

  if (m.media_url) {
    bubbles.push({
      side: "in",
      kind: "media",
      mediaUrl: m.media_url,
      mediaType: m.media_type ?? null,
      caption: m.incoming_message ?? undefined,
    });
  } else if (m.incoming_message) {
    bubbles.push({ side: "in", kind: "text", text: m.incoming_message });
  }

  // Marker do handoff humano — o worker grava no `response` quando pula o
  // agente IA. Não renderiza como bolha (a inbound já fica visível); só
  // exibe um divider sutil pra deixar claro que o agente foi pulado.
  const isHandoff = m.response?.startsWith("[handoff humano");
  if (m.response && !isHandoff) {
    bubbles.push({ side: "out", kind: "text", text: m.response });
  }
  if (m.error) {
    bubbles.push({ side: "out", kind: "text", text: `Erro: ${m.error}`, meta: "erro" });
  }

  return (
    <div className="space-y-2">
      {bubbles.map((b, i) => (
        <div
          key={i}
          className={cn("flex", b.side === "out" ? "justify-end" : "justify-start")}
        >
          <div
            className={cn(
              "max-w-[80%] rounded-2xl px-3 py-2 text-sm",
              b.side === "out"
                ? "bg-primary/15 text-foreground"
                : "bg-secondary text-foreground"
            )}
          >
            {b.kind === "media" ? (
              <MediaPreview
                url={b.mediaUrl}
                type={b.mediaType}
                caption={b.caption}
              />
            ) : (
              <p className="whitespace-pre-wrap">{b.text}</p>
            )}
            <p className="mt-1 font-mono text-[10px] text-muted-foreground">
              {formatTime(m.created_at)} · {b.side === "out" ? "agente" : "cliente"}
              {b.kind === "text" && b.meta && b.meta !== "erro" && (
                <>
                  {" · "}
                  <a
                    href={b.meta}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="underline"
                  >
                    abrir
                  </a>
                </>
              )}
            </p>
          </div>
        </div>
      ))}
      {isHandoff && (
        <p className="px-2 text-[10px] uppercase tracking-wide text-muted-foreground">
          ⏸ agente pausado — operador respondendo
        </p>
      )}
    </div>
  );
}

function MediaPreview({
  url,
  type,
  caption,
}: {
  url: string;
  type: string | null;
  caption?: string;
}) {
  const mime = (type || "").toLowerCase();

  // Suporta data: URLs (worker pré-fetch via Evolution) e URLs HTTP regulares.
  // Browser renderiza data URL inline em <img>/<audio> sem backend extra.
  if (mime.startsWith("image/")) {
    return (
      <div className="space-y-1">
        <a href={url} target="_blank" rel="noopener noreferrer">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={url}
            alt={caption || "imagem do cliente"}
            className="max-h-64 max-w-full rounded-lg border border-border/40 object-contain"
          />
        </a>
        {caption && (
          <p className="whitespace-pre-wrap text-xs text-muted-foreground">
            {caption}
          </p>
        )}
      </div>
    );
  }

  if (mime.startsWith("audio/")) {
    return (
      <div className="space-y-1">
        <audio
          controls
          src={url}
          className="w-full max-w-xs"
          preload="metadata"
        >
          Seu navegador não suporta player de áudio.
        </audio>
        {caption && (
          <p className="whitespace-pre-wrap text-xs text-muted-foreground">
            {caption}
          </p>
        )}
      </div>
    );
  }

  if (mime.startsWith("video/")) {
    return (
      <div className="space-y-1">
        <video
          controls
          src={url}
          className="max-h-64 max-w-full rounded-lg border border-border/40"
          preload="metadata"
        >
          Seu navegador não suporta vídeo.
        </video>
        {caption && (
          <p className="whitespace-pre-wrap text-xs text-muted-foreground">
            {caption}
          </p>
        )}
      </div>
    );
  }

  // Documento (PDF/DOCX) ou tipo desconhecido — link de download
  return (
    <div className="space-y-1">
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        download
        className="inline-flex items-center gap-1.5 rounded-md border border-border/40 bg-background px-2 py-1 text-xs underline hover:bg-muted"
      >
        📎 {type || "documento"} — abrir
      </a>
      {caption && (
        <p className="whitespace-pre-wrap text-xs text-muted-foreground">
          {caption}
        </p>
      )}
    </div>
  );
}
