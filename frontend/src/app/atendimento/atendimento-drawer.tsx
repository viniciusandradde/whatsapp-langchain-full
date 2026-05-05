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
import type {
  Atendimento,
  AtendimentoMensagem,
  ModeloMensagem,
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
  const [isPending, startTransition] = useTransition();

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

  // Polling 3s enquanto drawer aberto + atendimento ativo + aba focada.
  // Pausa em background (Page Visibility API) pra não consumir API à toa
  // quando operador troca de aba; retoma + faz reload imediato ao voltar.
  // Para automaticamente quando atendimento é fechado/abandonado.
  useEffect(() => {
    const isActive =
      atendimento.status === "aguardando" ||
      atendimento.status === "em_andamento";
    if (!isActive) return;

    let timer: ReturnType<typeof setInterval> | null = null;

    function start() {
      if (timer) return;
      timer = setInterval(() => {
        if (document.visibilityState === "visible") void silentReload();
      }, 3000);
    }
    function stop() {
      if (timer) {
        clearInterval(timer);
        timer = null;
      }
    }
    function onVisibilityChange() {
      if (document.visibilityState === "visible") {
        void silentReload();
        start();
      } else {
        stop();
      }
    }

    if (document.visibilityState === "visible") start();
    document.addEventListener("visibilitychange", onVisibilityChange);

    return () => {
      stop();
      document.removeEventListener("visibilitychange", onVisibilityChange);
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

  const isOpen =
    atendimento.status === "aguardando" || atendimento.status === "em_andamento";

  function handleTransfer() {
    const userId = prompt(
      "ID do operador para transferência (Better Auth user_id):"
    );
    if (!userId) return;
    runAction(() => transferAction(atendimento.id, userId.trim()));
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
        <header className="flex items-start justify-between gap-4 border-b p-5">
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h2 className="truncate text-lg font-semibold">
                {atendimento.cliente_nome ?? atendimento.cliente_telefone ?? "Cliente"}
              </h2>
              <Badge variant={statusVariant(atendimento.status)}>
                {STATUS_LABEL[atendimento.status]}
              </Badge>
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

        <div className="flex flex-1 flex-col overflow-hidden">
          <div className="flex items-center justify-between border-b px-5 py-2">
            <span className="text-xs uppercase tracking-wide text-muted-foreground">
              Conversa
            </span>
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

            {!loading && mensagens && mensagens.length === 0 && (
              <p className="text-sm text-muted-foreground">
                Nenhuma mensagem registrada para este atendimento ainda.
              </p>
            )}

            {mensagens?.map((m) => (
              <MessageBubbles key={m.id} m={m} />
            ))}
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
            <Button
              variant="ghost"
              onClick={handleTransfer}
              disabled={isPending}
            >
              <UserPlus className="size-3.5" />
              Transferir
            </Button>
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

function MessageBubbles({ m }: { m: AtendimentoMensagem }) {
  // Cada row pode gerar 2 bolhas: a inbound (cliente) e a response (agente).
  // Quando inbound veio só com mídia, mostramos chip da media_type.
  const bubbles: { side: "in" | "out"; text: string; meta?: string }[] = [];

  if (m.incoming_message) {
    bubbles.push({ side: "in", text: m.incoming_message });
  }
  if (m.media_url) {
    bubbles.push({
      side: "in",
      text: `[mídia ${m.media_type ?? ""}]`.trim(),
      meta: m.media_url,
    });
  }
  // Marker do handoff humano — o worker grava no `response` quando pula o
  // agente IA. Não renderiza como bolha (a inbound já fica visível); só
  // exibe um divider sutil pra deixar claro que o agente foi pulado.
  const isHandoff = m.response?.startsWith("[handoff humano");
  if (m.response && !isHandoff) {
    bubbles.push({ side: "out", text: m.response });
  }
  if (m.error) {
    bubbles.push({ side: "out", text: `Erro: ${m.error}`, meta: "erro" });
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
            <p className="whitespace-pre-wrap">{b.text}</p>
            <p className="mt-1 font-mono text-[10px] text-muted-foreground">
              {formatTime(m.created_at)} · {b.side === "out" ? "agente" : "cliente"}
              {b.meta && b.meta !== "erro" && (
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
