"use client";

import { useEffect, useRef, useState, useTransition } from "react";
import Link from "next/link";
import {
  Bot,
  Captions,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Eraser,
  FileText,
  Hand,
  MoreVertical,
  Pencil,
  RefreshCw,
  Send,
  ShieldOff,
  TriangleAlert,
  UserPlus,
  X,
  XCircle,
} from "lucide-react";

import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import type {
  AtendenteStatus,
  Atendimento,
  AtendimentoMensagem,
  Departamento,
  ModeloMensagem,
  WabaTemplate,
} from "@/lib/api";
import { cn } from "@/lib/utils";

import {
  apagarMensagemAction,
  claimAction,
  closeAction,
  devolverParaIaAction,
  criarNotaInternaAction,
  editarMensagemAction,
  incluirNumeroSemIaAction,
  loadAtendentesOnlineAction,
  enviarTemplateAction,
  loadDepartamentosAction,
  loadMensagensAction,
  loadModelosAction,
  loadTemplatesAprovadosAction,
  marcarAtendimentoLidoAction,
  reprocessarMensagemAction,
  resetThreadAction,
  responderAction,
  transcreverMensagemAction,
  transferAction,
  transferDepartamentoAction,
} from "./actions";
import { usePermission } from "@/hooks/use-permission";
import { BolhaMenu } from "./bolha-menu";
import {
  AnexoPreview,
  ComposerMidiaBotoes,
  criarAnexo,
  descartarAnexo,
  enviarAnexo,
  imagemColada,
  type AnexoPendente,
} from "./composer-midia";
import { ModelosPopover } from "./modelos-popover";
import { PainelCliente } from "./painel-cliente";
import { SITUACAO_AJUDA, SITUACAO_CLASSE, SITUACAO_LABEL } from "./situacao";
import { TagPopover } from "./tag-popover";

interface Props {
  atendimento: Atendimento;
  onClose: () => void;
  /**
   * `drawer` = overlay sobre a fila (comportamento antigo, mantido no mobile).
   * `painel` = coluna fixa ao lado da lista, que é o layout de desktop.
   *
   * O drawer obrigava o operador a escolher entre VER a fila e LER a conversa:
   * o backdrop escuro cobria a lista inteira. Toda inbox de helpdesk — e o
   * Inbox do Chatvolt — resolve isso com duas colunas fixas.
   */
  modo?: "drawer" | "painel";
  /**
   * Chamado quando uma ação de estado (atender, devolver à IA, transferir)
   * deu certo. Sem ele, o drawer FECHA a conversa (comportamento do overlay
   * antigo); com ele, a conversa fica aberta e quem chamou revalida a fila
   * pra o cabeçalho refletir o novo estado. Resolver/abandonar sempre fecha:
   * a conversa sai da caixa.
   */
  onAcaoConcluida?: () => void;
}

function formatTime(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("pt-BR");
}

export function AtendimentoDrawer({
  atendimento,
  onClose,
  modo = "drawer",
  onAcaoConcluida,
}: Props) {
  const [mensagens, setMensagens] = useState<AtendimentoMensagem[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const podeGerirSemIa = usePermission("whitelist.manage");
  const [semIaOpen, setSemIaOpen] = useState(false);
  const [semIaPending, setSemIaPending] = useState(false);
  const [composer, setComposer] = useState("");
  const [composerInterna, setComposerInterna] = useState(false);
  // Mig 172 — edição de mensagem enviada reusa o composer. Mutuamente
  // exclusivo com nota interna (espelha o `_editando` do app Android):
  // entrar em edição desliga a nota, e o checkbox fica desabilitado.
  const [editando, setEditando] = useState<{
    id: number;
    original: string;
  } | null>(null);
  const [templateModalOpen, setTemplateModalOpen] = useState(false);
  const [sending, setSending] = useState(false);
  // Anexo pendente (foto, documento, nota de voz gravada) — o "Enviar" de
  // sempre manda, com o texto do composer como legenda. Ver composer-midia.tsx.
  const [anexo, setAnexo] = useState<AnexoPendente | null>(null);
  const [arrastando, setArrastando] = useState(false);
  const anexoRef = useRef<AnexoPendente | null>(null);
  useEffect(() => {
    anexoRef.current = anexo;
  }, [anexo]);
  // Fechou a conversa com anexo pendente: solta o object URL da prévia.
  useEffect(() => () => descartarAnexo(anexoRef.current), []);
  function anexar(file: File) {
    const r = criarAnexo(file);
    if (!r.ok) {
      setError(r.error);
      return;
    }
    setError(null);
    descartarAnexo(anexo);
    setAnexo(r.anexo);
    composerRef.current?.focus();
  }
  function removerAnexo() {
    descartarAnexo(anexo);
    setAnexo(null);
  }
  const [modelos, setModelos] = useState<ModeloMensagem[] | null>(null);
  const [modelosOpen, setModelosOpen] = useState(false);
  // Atalho "/" no composer vazio (leva fila) — popover de busca de modelos,
  // separado do painel do kebab (modelosOpen) que continua existindo.
  const [slashOpen, setSlashOpen] = useState(false);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
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
  const [atendentesOnline, setAtendentesOnline] = useState<AtendenteStatus[]>(
    []
  );
  const [loadingAtds, setLoadingAtds] = useState(false);
  // Guarda "já tentei carregar" por fora do resultado — usar `.length === 0`
  // como sinal de "ainda não carreguei" (abaixo) é indistinguível de "carreguei
  // e a empresa não tem nenhum" (ex.: nenhum atendente online agora, caso
  // normal), e a cada resolução da promise o efeito reavaliava a MESMA
  // condição vazia e disparava a Server Action de novo — sem debounce, na
  // velocidade da rede. Gerou uma rajada de centenas de req/s de um usuário
  // só (20/09) até estourar o rate limit admin. `false` mantém retentativa
  // em falha real; `true` só quando a resposta veio `ok` (mesmo com 0 itens).
  const deptosCarregados = useRef(false);
  const atdsCarregados = useRef(false);

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

  // Scroll estilo WhatsApp: a conversa abre na ÚLTIMA mensagem e acompanha
  // as novas, mas quem rolou pra cima lendo histórico não é puxado de volta
  // — `grudadoNoFimRef` rastreia se o usuário está perto do fim (via
  // onScroll) e só aí a chegada de mensagem re-ancora.
  const timelineRef = useRef<HTMLDivElement | null>(null);
  const grudadoNoFimRef = useRef(true);
  const primeiraCargaRef = useRef(true);

  useEffect(() => {
    primeiraCargaRef.current = true;
    grudadoNoFimRef.current = true;
    void reload();
    // Marca como lido após 1s (debounce) — evita race quando user só
    // tangencia o item (esc rápido). Fire-and-forget; ignore erro.
    const t = window.setTimeout(() => {
      void marcarAtendimentoLidoAction(atendimento.id);
    }, 1000);
    return () => window.clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [atendimento.id]);

  useEffect(() => {
    if (!mensagens) return;
    const el = timelineRef.current;
    if (!el) return;
    if (primeiraCargaRef.current || grudadoNoFimRef.current) {
      el.scrollTop = el.scrollHeight;
      primeiraCargaRef.current = false;
      // Mídia que carrega depois estica o conteúdo — re-ancora no frame
      // seguinte pra primeira abertura não parar "quase" no fim.
      requestAnimationFrame(() => {
        if (grudadoNoFimRef.current) el.scrollTop = el.scrollHeight;
      });
    }
  }, [mensagens, activeTab]);

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

  function runAction(
    fn: () => Promise<{ ok: true } | { ok: false; error: string }>,
    opts: { encerra?: boolean } = {}
  ) {
    setError(null);
    startTransition(async () => {
      const r = await fn();
      if (!r.ok) {
        setError(r.error);
        return;
      }
      if (onAcaoConcluida) {
        onAcaoConcluida();
        // Resolver/abandonar tira a conversa da caixa: o painel não tem o
        // que mostrar e fecha; o resto fica aberto com o estado novo.
        if (opts.encerra) onClose();
      } else {
        onClose();
      }
    });
  }

  // Lazy: carrega departamentos + atendentes online só quando user abre o
  // popover, e só uma vez (guard por ref, não por tamanho — ver acima).
  // Via server actions — api.ts é server-only.
  useEffect(() => {
    if (!transferOpen) return;
    if (!deptosCarregados.current && !loadingDeps) {
      setLoadingDeps(true);
      loadDepartamentosAction()
        .then((r) => {
          if (r.ok) {
            setDepartamentos(r.departamentos);
            deptosCarregados.current = true;
          }
        })
        .finally(() => setLoadingDeps(false));
    }
    if (!atdsCarregados.current && !loadingAtds) {
      setLoadingAtds(true);
      loadAtendentesOnlineAction()
        .then((r) => {
          if (r.ok) {
            setAtendentesOnline(r.atendentes);
            atdsCarregados.current = true;
          }
        })
        .finally(() => setLoadingAtds(false));
    }
  }, [transferOpen, loadingDeps, loadingAtds]);

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
    runAction(() => closeAction(atendimento.id, status), { encerra: true });
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
      `Conversa resetada (${r.rowsDeleted} registros removidos).\n` +
        `Thread: ${r.threadId}\n\n` +
        "Próxima mensagem do cliente vai começar do zero."
    );
  }

  async function confirmarIncluirSemIa() {
    const telefone = atendimento.cliente_telefone;
    if (!telefone) return;
    setSemIaPending(true);
    const r = await incluirNumeroSemIaAction(
      telefone,
      atendimento.cliente_nome ?? null
    );
    setSemIaPending(false);
    if (!r.ok) {
      toast.error(r.error);
      return;
    }
    setSemIaOpen(false);
    toast.success(
      "Número incluído na lista de números sem IA. Gerencie em Conectividade → Números sem IA."
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

  function abrirSlashModelos() {
    if (modelos === null) {
      void loadModelosAction().then((r) => {
        if (r.ok) setModelos(r.modelos);
      });
    }
    setSlashOpen(true);
  }

  function escolherModeloSlash(m: ModeloMensagem) {
    setComposer(m.conteudo);
    setSlashOpen(false);
    composerRef.current?.focus();
  }

  function iniciarEdicao(m: AtendimentoMensagem) {
    setEditando({ id: m.id, original: m.response ?? "" });
    setComposer(m.response ?? "");
    setComposerInterna(false);
  }

  function sairEdicao() {
    setEditando(null);
    setComposer("");
  }

  async function handleSend() {
    const text = composer.trim();
    if (sending) return;
    if (anexo && !editando && !composerInterna) {
      // Mídia: uma mensagem só, o texto vai de legenda (vazio é permitido).
      setSending(true);
      setError(null);
      const r = await enviarAnexo(atendimento.id, anexo, text);
      if (!r.ok) {
        setError(r.error);
        setSending(false);
        return;
      }
      removerAnexo();
      setComposer("");
      setSending(false);
      await reload();
      return;
    }
    if (!text) return;
    setSending(true);
    setError(null);
    const r = editando
      ? await editarMensagemAction(atendimento.id, editando.id, text)
      : composerInterna
        ? await criarNotaInternaAction(atendimento.id, text)
        : await responderAction(atendimento.id, text);
    if (!r.ok) {
      // Inclui o 400 de janela vencida (15min) — a frase do backend já é
      // amigável ("Este canal não permite editar…" / janela expirada).
      setError(r.error);
      setSending(false);
      return;
    }
    setComposer("");
    setEditando(null);
    setSending(false);
    // Recarrega timeline para incluir a msg recém-criada/editada.
    await reload();
  }

  const conteudo = (
      <aside
        className={
          modo === "painel"
            ? "flex h-full min-h-0 w-full flex-col bg-card"
            : "flex h-full w-full max-w-3xl flex-col bg-card shadow-2xl"
        }
        onClick={(e) => e.stopPropagation()}
      >
        <header className="sticky top-0 z-10 flex items-start justify-between gap-3 border-b bg-card p-3 md:px-5 md:py-3">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
              <h2 className="truncate text-lg font-semibold">
                {atendimento.cliente_nome ?? atendimento.cliente_telefone ?? "Cliente"}
              </h2>
              <Badge
                variant="outline"
                className={SITUACAO_CLASSE[atendimento.situacao]}
                title={SITUACAO_AJUDA[atendimento.situacao]}
              >
                {SITUACAO_LABEL[atendimento.situacao]}
              </Badge>
              {atendimento.protocolo && (
                <Badge variant="outline" className="font-mono text-[10px]">
                  #{atendimento.protocolo}
                </Badge>
              )}
              <span className="font-mono text-[11px] text-muted-foreground">
                #{atendimento.id}
              </span>
              <TagPopover atendimentoId={atendimento.id} />
              {atendimento.qtde_resposta_invalida > 0 && (
                <Badge
                  variant="outline"
                  className="text-[10px]"
                  title={`Cliente errou ${atendimento.qtde_resposta_invalida}× no menu/CSAT`}
                >
                  <TriangleAlert className="size-3" />
                  {atendimento.qtde_resposta_invalida}
                </Badge>
              )}
              {!atendimento.iniciado_cliente && (
                <Badge variant="outline" className="text-[10px]" title="outbound">
                  outbound
                </Badge>
              )}
              {atendimento.solicitou_encerramento && (
                <Badge variant="outline" className="text-[10px]">
                  pediu encerrar
                </Badge>
              )}
            </div>
            <p className="mt-0.5 font-mono text-[11px] text-muted-foreground truncate">
              {atendimento.cliente_telefone ?? "—"} · {atendimento.agente_atual}
              {atendimento.cliente_id && (
                <>
                  {" · "}
                  <Link
                    href={`/clientes/${atendimento.cliente_id}`}
                    className="underline hover:text-foreground"
                  >
                    ver ficha
                  </Link>
                </>
              )}
            </p>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <MoreActionsMenu
              onLoadModelos={() => void openModelosDropdown()}
              onResetThread={() => void handleResetThread()}
              onIncluirSemIa={
                podeGerirSemIa && atendimento.cliente_telefone
                  ? () => setSemIaOpen(true)
                  : undefined
              }
            />
            {semIaOpen && (
              <Dialog open onOpenChange={(v) => !v && setSemIaOpen(false)}>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                      <ShieldOff className="size-4" />
                      Incluir {atendimento.cliente_telefone} nos números sem IA
                    </DialogTitle>
                    <DialogDescription>
                      Nenhuma conexão da empresa vai responder automaticamente a
                      esse número — sem agente, menu ou mensagens automáticas —
                      até que ele seja removido na tela Números sem IA.
                    </DialogDescription>
                  </DialogHeader>
                  <DialogFooter>
                    <Button
                      variant="outline"
                      onClick={() => setSemIaOpen(false)}
                      disabled={semIaPending}
                    >
                      Cancelar
                    </Button>
                    <Button
                      onClick={() => void confirmarIncluirSemIa()}
                      disabled={semIaPending}
                    >
                      {semIaPending ? "Incluindo…" : "Incluir número"}
                    </Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
            )}
            <Button variant="ghost" size="icon" onClick={onClose} aria-label="Fechar">
              <X className="size-4" />
            </Button>
          </div>
        </header>

        <TriagemCard atendimento={atendimento} />
        <ColetaPreviaCard atendimento={atendimento} />
        <PainelCliente
          atendimentoId={atendimento.id}
          clienteId={atendimento.cliente_id}
          clienteNome={atendimento.cliente_nome ?? null}
          clienteTelefone={atendimento.cliente_telefone ?? null}
        />

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
                onClick={() => void reload()}
                disabled={loading}
              >
                <RefreshCw className={cn("size-3.5", loading && "animate-spin")} />
                Atualizar
              </Button>
            </div>
          </div>

          <div
            ref={timelineRef}
            onScroll={(e) => {
              const el = e.currentTarget;
              grudadoNoFimRef.current =
                el.scrollHeight - el.scrollTop - el.clientHeight < 120;
            }}
            className="flex-1 space-y-3 overflow-y-auto px-5 py-4"
          >
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
                  <MessageBubbles
                    key={m.id}
                    m={m}
                    atendimentoId={atendimento.id}
                    onReprocessado={reload}
                    onEditar={iniciarEdicao}
                  />
                ))}
              </>
            )}

            {activeTab === "arquivos" && <ArquivosTab mensagens={mensagens} />}
          </div>
        </div>

        {isOpen && modelosOpen && (
          <div className="fixed right-6 top-20 z-30 max-h-72 w-80 overflow-y-auto rounded-md border bg-popover shadow-lg">
            {modelos === null ? (
              <p className="p-3 text-xs text-muted-foreground">Carregando…</p>
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

        {isOpen && (
          <div
            className="relative border-t bg-background/40 p-3"
            onDragOver={(e) => {
              if (editando || composerInterna) return;
              if (!Array.from(e.dataTransfer.types).includes("Files")) return;
              e.preventDefault();
              setArrastando(true);
            }}
            onDragLeave={(e) => {
              if (e.currentTarget.contains(e.relatedTarget as Node | null)) return;
              setArrastando(false);
            }}
            onDrop={(e) => {
              setArrastando(false);
              if (editando || composerInterna) return;
              const f = e.dataTransfer.files?.[0];
              if (!f) return;
              e.preventDefault();
              anexar(f);
            }}
          >
            {arrastando && (
              <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center rounded-md border-2 border-dashed border-brand-primary/60 bg-background/90 text-sm font-medium text-brand-primary">
                Solte para anexar
              </div>
            )}
            {slashOpen && (
              <ModelosPopover
                modelos={modelos}
                onEscolher={escolherModeloSlash}
                onFechar={() => {
                  setSlashOpen(false);
                  composerRef.current?.focus();
                }}
              />
            )}
            {editando && (
              <div className="mb-2 flex items-center justify-between gap-2 rounded-md border border-brand-primary/40 bg-brand-primary/5 px-2 py-1.5 text-xs">
                <span className="flex items-center gap-1.5 font-medium">
                  <Pencil className="size-3 shrink-0" />
                  Editando mensagem — Enter salva, Esc cancela
                </span>
                <button
                  type="button"
                  aria-label="Cancelar edição"
                  onClick={sairEdicao}
                  className="text-muted-foreground hover:text-foreground"
                >
                  <X className="size-3.5" />
                </button>
              </div>
            )}
            <div className="mb-2 flex items-center gap-3">
              <label className="flex cursor-pointer items-center gap-1.5 text-xs text-muted-foreground">
                <input
                  type="checkbox"
                  checked={composerInterna}
                  disabled={editando !== null || anexo !== null}
                  onChange={(e) => setComposerInterna(e.target.checked)}
                  className="h-3.5 w-3.5"
                />
                <span className={composerInterna ? "font-medium text-amber-600 dark:text-amber-400" : ""}>
                  Nota interna (não envia pro cliente)
                </span>
              </label>
              <button
                type="button"
                onClick={() => setTemplateModalOpen(true)}
                className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                title="Enviar template HSM aprovado (reabre fora da janela 24h)"
              >
                <FileText className="size-3.5" /> Template
              </button>
            </div>
            {anexo && (
              <AnexoPreview anexo={anexo} enviando={sending} onRemover={removerAnexo} />
            )}
            <div className="flex items-end gap-2">
              <ComposerMidiaBotoes
                disabled={sending || editando !== null || composerInterna}
                onAnexo={(a) => {
                  descartarAnexo(anexo);
                  setError(null);
                  setAnexo(a);
                }}
                onErro={setError}
              />
              <textarea
                ref={composerRef}
                value={composer}
                onChange={(e) => setComposer(e.target.value)}
                onPaste={(e) => {
                  if (editando || composerInterna) return;
                  const img = imagemColada(e);
                  if (!img) return;
                  e.preventDefault();
                  anexar(img);
                }}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    void handleSend();
                  }
                  if (e.key === "Escape" && editando) {
                    e.preventDefault();
                    sairEdicao();
                  }
                  // "/" no composer VAZIO abre a busca de modelos — com texto
                  // já digitado, "/" é só um caractere (URLs, datas).
                  if (e.key === "/" && composer === "") {
                    e.preventDefault();
                    abrirSlashModelos();
                  }
                }}
                placeholder={
                  editando
                    ? "Corrija o texto da mensagem…"
                    : composerInterna
                      ? "Anotação privada da equipe… (não aparece pro cliente)"
                      : anexo
                        ? anexo.tipo === "audio"
                          ? "Enter envia a nota de voz"
                          : "Legenda (opcional)… Enter envia"
                        : "Digite a resposta para o cliente… (Enter envia, Shift+Enter quebra linha)"
                }
                rows={2}
                disabled={sending}
                className={`flex w-full resize-none rounded-md border px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:opacity-60 ${
                  composerInterna
                    ? "border-amber-400/60 bg-amber-50/40 dark:bg-amber-950/20"
                    : "border-input bg-background"
                }`}
              />
              <Button
                onClick={() => void handleSend()}
                disabled={sending || (!composer.trim() && !anexo)}
              >
                <Send className="size-3.5" />
                {sending ? "Enviando…" : editando ? "Salvar" : "Enviar"}
              </Button>
            </div>
          </div>
        )}

        {templateModalOpen && (
          <TemplateComposerModal
            atendimentoId={atendimento.id}
            conexaoId={atendimento.conexao_id}
            provider={atendimento.conexao_provider}
            onClose={() => setTemplateModalOpen(false)}
            onSent={() => {
              setTemplateModalOpen(false);
              void reload();
            }}
          />
        )}

        {isOpen && (
          <footer className="flex flex-wrap items-center justify-end gap-1 border-t px-3 py-2">
            {atendimento.status === "aguardando" && (
              <Button
                size="sm"
                onClick={() => runAction(() => claimAction(atendimento.id))}
                disabled={isPending}
              >
                <Hand className="size-3.5" />
                Atender
              </Button>
            )}
            {/* Desfaz o "Atender". Enquanto o atendimento tem dono o worker cala
                o agente, e até existir este botão assumir era irreversível: as
                saídas eram fechar (dispara a pesquisa de satisfação) ou
                transferir (avisa o cliente). Nada é enviado ao cliente aqui — a
                IA só volta a responder. */}
            {atendimento.status === "em_andamento" && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() =>
                  runAction(() => devolverParaIaAction(atendimento.id))
                }
                disabled={isPending}
                title="A IA volta a responder este cliente. Nada é enviado a ele."
              >
                <Bot className="size-3.5" />
                Devolver para a IA
              </Button>
            )}
            <div className="relative">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setTransferOpen((v) => !v)}
                disabled={isPending}
              >
                <UserPlus className="size-3.5" />
                Transferir
              </Button>
              {transferOpen && (
                <>
                  {/* backdrop só no mobile pra fechar tocando fora */}
                  <button
                    type="button"
                    aria-label="Fechar transferência"
                    className="fixed inset-0 z-10 bg-black/40 sm:hidden"
                    onClick={handleCancelTransfer}
                  />
                  <div className="fixed inset-x-2 bottom-2 z-20 rounded-lg border bg-background p-3 shadow-xl sm:absolute sm:inset-x-auto sm:bottom-full sm:right-0 sm:mb-2 sm:w-80 sm:rounded-md">
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
                    <select
                      value={transferUserId}
                      onChange={(e) => setTransferUserId(e.target.value)}
                      className="mb-3 w-full rounded-md border border-input bg-background px-2 py-1.5 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                      aria-label="Atendente online de destino"
                    >
                      <option value="">
                        {loadingAtds
                          ? "Carregando…"
                          : atendentesOnline.length === 0
                            ? "Nenhum atendente online no momento"
                            : "Selecione o atendente"}
                      </option>
                      {atendentesOnline.map((a) => (
                        <option key={a.user_id} value={a.user_id}>
                          {a.nome || a.email || a.user_id}
                          {a.count_atendimentos_abertos > 0
                            ? ` (${a.count_atendimentos_abertos} abertos)`
                            : ""}
                        </option>
                      ))}
                    </select>
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
                </>
              )}
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => handleClose("resolvido")}
              disabled={isPending}
            >
              <CheckCircle2 className="size-3.5" />
              Resolver
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => handleClose("abandonado")}
              disabled={isPending}
            >
              <XCircle className="size-3.5" />
              Abandonar
            </Button>
          </footer>
        )}
      </aside>
  );

  // No desktop a conversa é coluna fixa; no mobile continua sendo overlay,
  // porque 390px não comportam duas colunas.
  if (modo === "painel") return conteudo;

  return (
    <div
      className="fixed inset-0 z-50 flex items-stretch justify-end bg-black/50 backdrop-blur-sm"
      onClick={onClose}
    >
      {conteudo}
    </div>
  );
}

// Card "Triagem IA" — renderiza só quando o agente classificou ou
// gerou resumo. Aparece logo abaixo do header do drawer pra o atendente
// Menu kebab (⋮) no header com ações secundárias do atendimento.
// "Inserir modelo" dispara o dropdown de modelos absoluto perto do header.
// "Resetar conversa" é admin-only — limpa thread do agente (LangGraph checkpointer).
function MoreActionsMenu({
  onLoadModelos,
  onResetThread,
  onIncluirSemIa,
}: {
  onLoadModelos: () => void;
  onResetThread: () => void;
  /** Ausente quando o usuário não tem `whitelist.manage` ou não há telefone. */
  onIncluirSemIa?: () => void;
}) {
  const [open, setOpen] = useState(false);

  return (
    <div className="relative">
      <Button
        variant="ghost"
        size="icon"
        onClick={() => setOpen((v) => !v)}
        aria-label="Mais ações"
        title="Mais ações"
      >
        <MoreVertical className="size-4" />
      </Button>
      {open && (
        <>
          <button
            type="button"
            aria-label="Fechar menu"
            className="fixed inset-0 z-10"
            onClick={() => setOpen(false)}
          />
          <div className="absolute right-0 top-full z-20 mt-1 min-w-[200px] overflow-hidden rounded-md border bg-popover shadow-lg">
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                onLoadModelos();
              }}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-accent"
            >
              <FileText className="size-3.5" />
              Inserir modelo de mensagem
            </button>
            {onIncluirSemIa && (
              <button
                type="button"
                onClick={() => {
                  setOpen(false);
                  onIncluirSemIa();
                }}
                className="flex w-full items-center gap-2 px-3 py-2 text-left text-sm hover:bg-accent"
              >
                <ShieldOff className="size-3.5" />
                Incluir em números sem IA
              </button>
            )}
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                onResetThread();
              }}
              className="flex w-full items-center gap-2 border-t px-3 py-2 text-left text-sm text-amber-600 hover:bg-accent dark:text-amber-400"
            >
              <Eraser className="size-3.5" />
              Resetar conversa do agente
            </button>
          </div>
        </>
      )}
    </div>
  );
}

// pegar contexto rápido sem ler conversa toda.
function TriagemCard({ atendimento }: { atendimento: Atendimento }) {
  const [collapsed, setCollapsed] = useCollapseState(
    `triagem-${atendimento.id}`,
    false,
  );
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
      <button
        type="button"
        onClick={() => setCollapsed(!collapsed)}
        className="mb-2 flex w-full items-center justify-between gap-2 text-xs uppercase tracking-wide text-muted-foreground hover:text-foreground transition-colors"
        aria-expanded={!collapsed}
        aria-label={collapsed ? "Expandir triagem" : "Recolher triagem"}
      >
        <span className="flex items-center gap-2">
          <span>Triagem da IA</span>
          {atendimento.triagem_completa && (
            <Badge variant="outline" className="text-[10px]">
              completa
            </Badge>
          )}
        </span>
        {collapsed ? (
          <ChevronDown className="size-3.5" />
        ) : (
          <ChevronUp className="size-3.5" />
        )}
      </button>
      {!collapsed && (
        <>
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
        </>
      )}
    </div>
  );
}

// Card "Coleta prévia" — exibe as respostas do wizard de coleta que
// rodou antes de chegar no atendente. Inclui label da pergunta e valor
// pra contexto. Renderiza só quando `coleta_resumo` está populado.
function ColetaPreviaCard({ atendimento }: { atendimento: Atendimento }) {
  const [collapsed, setCollapsed] = useCollapseState(
    `coleta-${atendimento.id}`,
    false,
  );
  const resumo = atendimento.coleta_resumo;
  if (!resumo || !resumo.respostas) return null;
  const entries = Object.entries(resumo.respostas);
  if (entries.length === 0) return null;

  return (
    <div className="border-b bg-blue-500/5 px-5 py-3">
      <button
        type="button"
        onClick={() => setCollapsed(!collapsed)}
        className="mb-2 flex w-full items-center justify-between gap-2 text-xs uppercase tracking-wide text-muted-foreground hover:text-foreground transition-colors"
        aria-expanded={!collapsed}
        aria-label={collapsed ? "Expandir coleta prévia" : "Recolher coleta prévia"}
      >
        <span className="flex items-center gap-2">
          <span>Coleta prévia</span>
          {resumo.item_label && (
            <Badge variant="outline" className="text-[10px]">
              via &ldquo;{resumo.item_label}&rdquo;
            </Badge>
          )}
          {collapsed && (
            <span className="normal-case text-[10px] text-muted-foreground/70">
              ({entries.length} {entries.length === 1 ? "campo" : "campos"})
            </span>
          )}
        </span>
        {collapsed ? (
          <ChevronDown className="size-3.5" />
        ) : (
          <ChevronUp className="size-3.5" />
        )}
      </button>
      {!collapsed && (
        <dl className="space-y-1.5 text-xs">
          {entries.map(([key, val]) => (
            <div key={key} className="flex flex-col gap-0.5">
              <dt className="text-[11px] font-medium text-muted-foreground">
                {val.label}
              </dt>
              <dd className="rounded-md bg-background/70 px-2 py-1 font-mono text-foreground">
                {val.valor || (
                  <span className="text-muted-foreground italic">
                    (sem resposta)
                  </span>
                )}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

// Hook simples: estado de collapse persistido em localStorage por chave
// (preferência por atendimento). Default `initialCollapsed` na primeira
// montagem; depois carrega valor do storage.
function useCollapseState(
  key: string,
  initialCollapsed: boolean,
): [boolean, (next: boolean) => void] {
  const storageKey = `atendimento-card-collapsed:${key}`;
  const [collapsed, setCollapsedState] = useState(initialCollapsed);

  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const saved = window.localStorage.getItem(storageKey);
      if (saved !== null) setCollapsedState(saved === "1");
    } catch {
      // localStorage indisponível (privacy mode) — ignora
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey]);

  const setCollapsed = (next: boolean) => {
    setCollapsedState(next);
    if (typeof window === "undefined") return;
    try {
      window.localStorage.setItem(storageKey, next ? "1" : "0");
    } catch {
      // ignora
    }
  };

  return [collapsed, setCollapsed];
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

/**
 * Botão de reprocesso — só aparece em mensagem que ficou SEM resposta pro
 * cliente: `failed`, ou pulada por conexão em modo manual / número na
 * whitelist. Handoff humano fica de fora (atendente assumiu).
 *
 * Confirma antes: manda WhatsApp real e gasta token. O backend revalida os
 * gates e devolve 409 com frase acionável se a condição ainda vale.
 */
function BotaoReprocessar({
  atendimentoId,
  messageId,
  onReprocessado,
}: {
  atendimentoId: number;
  messageId: number;
  onReprocessado: () => void;
}) {
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function clicar() {
    if (enviando) return;
    if (
      !window.confirm(
        "Reprocessar esta mensagem? A IA vai responder e o cliente receberá " +
          "a mensagem no WhatsApp."
      )
    ) {
      return;
    }
    setEnviando(true);
    setErro(null);
    const r = await reprocessarMensagemAction(atendimentoId, messageId);
    setEnviando(false);
    if (r.ok) onReprocessado();
    else setErro(r.error);
  }

  return (
    <div className="flex flex-col items-center gap-1">
      <button
        type="button"
        onClick={clicar}
        disabled={enviando}
        className="inline-flex items-center gap-1 rounded-md border border-foreground/15 px-2 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-foreground/5 disabled:opacity-50"
      >
        {enviando ? "Reprocessando…" : "↻ Reprocessar com IA"}
      </button>
      {erro ? <span className="text-[11px] text-destructive">{erro}</span> : null}
    </div>
  );
}

function MessageBubbles({
  m,
  atendimentoId,
  onReprocessado,
  onEditar,
}: {
  m: AtendimentoMensagem;
  atendimentoId: number;
  onReprocessado: () => void;
  /** Mig 172 — pede ao drawer pra entrar em modo edição com esta mensagem. */
  onEditar?: (m: AtendimentoMensagem) => void;
}) {
  // Cada row pode gerar bolhas distintas: media (inbound), texto inbound,
  // resposta agente. Mídia é renderizada inline como <img>/<audio>/link.
  type Bubble =
    | {
        side: "in" | "out";
        kind: "text";
        text: string;
        meta?: string;
        /** Apagada para todos (mig 172): renderiza em itálico, apagado. */
        apagada?: boolean;
      }
    | {
        side: "in" | "out";
        kind: "media";
        /** URL do proxy do Next — o conteúdo NÃO vem na lista. */
        mediaUrl: string;
        mediaType: string | null;
        caption?: string;
        /** Só inbound de áudio (mig 169): habilita transcrição no painel. */
        mensagemId?: number;
        transcricao?: string | null;
      };

  const bubbles: Bubble[] = [];

  if (m.media_disponivel || m.media_url) {
    bubbles.push({
      side: "in",
      kind: "media",
      mediaUrl:
        m.media_url ??
        `/api/proxy/midia/${atendimentoId}/${m.id}?lado=in`,
      mediaType: m.media_type ?? null,
      caption: m.incoming_message ?? undefined,
      mensagemId: m.id,
      transcricao: m.transcricao,
    });
  } else if (m.incoming_message) {
    bubbles.push({ side: "in", kind: "text", text: m.incoming_message });
  }

  // Markers de skip do agente — o worker grava no `response` quando pula o
  // agente IA (handoff humano ou conexão em modo manual/IA desligada). Não
  // renderiza como bolha (a inbound já fica visível); só exibe um divider
  // sutil pra deixar claro que o agente foi pulado.
  const isHandoff =
    m.response?.startsWith("[handoff humano") ||
    m.response?.startsWith("[modo manual") ||
    m.response?.startsWith("[whitelist") ||
    // Marker novo (mig 143 / gate da fila): a IA já transferiu e o
    // atendimento aguarda atendente. Sem esta linha o texto interno
    // vazaria como bolha de resposta na timeline do operador.
    m.response?.startsWith("[fila do departamento") ||
    // Mig 144: o cliente escreveu de novo enquanto o modelo pensava, então
    // esta resposta foi engolida e o turno seguinte respondeu tudo. Nada foi
    // enviado ao cliente — não pode aparecer como bolha.
    m.response?.startsWith("[resposta superada");

  // Mensagem que ficou SEM resposta pro cliente. Handoff fica de fora: lá um
  // atendente assumiu, e a IA responder por cima seria pior que o problema.
  // O backend revalida tudo — isto só decide se o botão aparece.
  const podeReprocessar =
    m.status === "failed" ||
    m.response?.startsWith("[modo manual") === true ||
    m.response?.startsWith("[whitelist") === true;
  // Mídia enviada PELO OPERADOR (mig 146) — o app Android manda foto, documento
  // e nota de voz. Fica em `response_media_url`, separada da inbound: o lado da
  // bolha vem da origem do campo, e reusar `media_url` poria o que o operador
  // mandou do lado do cliente. Quando há mídia, `response` é a LEGENDA dela, e
  // não uma segunda bolha de texto.
  if (m.response_media_disponivel || m.response_media_url) {
    bubbles.push({
      side: "out",
      kind: "media",
      mediaUrl:
        m.response_media_url ??
        `/api/proxy/midia/${atendimentoId}/${m.id}?lado=out`,
      mediaType: m.response_media_type ?? null,
      caption: !isHandoff && m.response ? m.response : undefined,
    });
  } else if (m.response && !isHandoff) {
    // Apagada para todos (mig 172): o cliente não vê mais nada, então exibir o
    // texto aqui faria o painel afirmar que a mensagem foi entregue. O texto
    // continua no banco para auditoria — quem precisa dele consulta lá, não
    // pela timeline.
    bubbles.push(
      m.response_apagada
        ? { side: "out", kind: "text", text: "Mensagem apagada", apagada: true }
        : { side: "out", kind: "text", text: m.response }
    );
  }
  if (m.error) {
    // NUNCA renderizar o detalhe técnico do erro como texto visível.
    // O backend já manda string sanitizada tipo `processing_failed:Xerror`,
    // mas como blindagem renderizamos sempre uma frase fixa pro operador;
    // detalhe vai pra `meta` (linha cinza menor) só pra correlação rápida
    // com logs do worker. Erro real fica no `docker logs worker`.
    bubbles.push({
      side: "out",
      kind: "text",
      text: "Falha ao processar essa mensagem. Tente reenviar ou entre em contato com o suporte.",
      meta: `erro · ${m.error.slice(0, 80)}`,
    });
  }

  // Sprint 1.3 — nota interna fica visualmente distinta (fundo amarelo,
  // ocupa largura cheia centrada, label "🔒 Nota interna · <autor>")
  if (m.interna && m.response) {
    return (
      <div className="flex justify-center">
        <div className="w-full max-w-[90%] rounded-lg border border-amber-400/40 bg-amber-50/70 px-3 py-2 text-sm dark:border-amber-500/40 dark:bg-amber-950/30">
          <p className="mb-1 flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-amber-700 dark:text-amber-400">
            Nota interna · {m.criado_por_user_id ?? "—"}
          </p>
          <p className="whitespace-pre-wrap text-foreground">{m.response}</p>
          <p className="mt-1 font-mono text-[10px] text-muted-foreground">
            {formatTime(m.created_at)}
          </p>
        </div>
      </div>
    );
  }

  async function apagar() {
    const r = await apagarMensagemAction(atendimentoId, m.id);
    if (!r.ok) {
      // Janela de 48h vencida ou canal sem suporte (WABA) — frase do backend.
      toast.error(r.error);
      return;
    }
    toast.success("Mensagem apagada para todos");
    onReprocessado();
  }

  return (
    <div className="space-y-2">
      {bubbles.map((b, i) => {
        // Guardas do menu (paridade com o app): bolha apagada ou de erro é
        // inerte; Copiar exige texto; Editar/Apagar só na resposta outbound e
        // só quando o servidor calculou que a janela ainda vale.
        const ehErro = b.kind === "text" && b.meta?.startsWith("erro") === true;
        const inerte = ehErro || (b.kind === "text" && b.apagada === true);
        const copiavel = inerte
          ? null
          : b.kind === "text"
            ? b.text
            : [b.caption, b.transcricao].filter(Boolean).join("\n") || null;
        const podeEditar =
          !inerte &&
          b.side === "out" &&
          b.kind === "text" &&
          m.pode_editar_resposta === true;
        const podeApagar =
          !inerte && b.side === "out" && m.pode_apagar_resposta === true;
        const bolha = (
          <div
            className={cn(
              "max-w-[80%] rounded-2xl px-3 py-2 text-sm",
              b.side === "out"
                ? "bg-primary/15 text-foreground"
                : "bg-secondary text-foreground"
            )}
          >
            {b.kind === "media" ? (
              <>
                <MediaPreview
                  url={b.mediaUrl}
                  type={b.mediaType}
                  caption={b.caption}
                />
                {b.side === "in" &&
                  b.mensagemId !== undefined &&
                  (b.mediaType ?? "").startsWith("audio/") && (
                    <TranscricaoAudio
                      atendimentoId={atendimentoId}
                      mensagemId={b.mensagemId}
                      transcricao={b.transcricao ?? null}
                    />
                  )}
              </>
            ) : (
              <p
                className={cn(
                  "whitespace-pre-wrap",
                  b.apagada && "italic text-muted-foreground"
                )}
              >
                {b.text}
              </p>
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
        );
        return (
          <div
            key={i}
            className={cn(
              "flex",
              b.side === "out" ? "justify-end" : "justify-start"
            )}
          >
            <BolhaMenu
              copiarTexto={copiavel}
              podeEditar={podeEditar}
              podeApagar={podeApagar}
              onEditar={onEditar ? () => onEditar(m) : undefined}
              onApagar={apagar}
            >
              {bolha}
            </BolhaMenu>
          </div>
        );
      })}
      {isHandoff && (
        <p className="px-2 text-[10px] uppercase tracking-wide text-muted-foreground">
          {/* Antes os 3 markers mostravam "operador respondendo" — verdade só
              no handoff. Em modo manual/whitelist NINGUÉM respondeu, e essa
              é exatamente a situação que deixou uma cliente sem resposta. */}
          {m.response?.startsWith("[handoff humano")
            ? "agente pausado — operador respondendo"
            : m.response?.startsWith("[modo manual")
              ? "IA desligada nesta conexão — ninguém respondeu"
              : "número na lista de bloqueio da IA — ninguém respondeu"}
        </p>
      )}
      {podeReprocessar && (
        <BotaoReprocessar
          atendimentoId={atendimentoId}
          messageId={m.id}
          onReprocessado={onReprocessado}
        />
      )}
    </div>
  );
}

/**
 * Transcrição da nota de voz pro operador (mig 169).
 *
 * Se a mensagem já tem transcrição (automática por conexão ou de um clique
 * anterior), mostra o texto direto. Senão, oferece o botão — o servidor é
 * idempotente, então cliques repetidos não pagam LLM de novo.
 */
function TranscricaoAudio({
  atendimentoId,
  mensagemId,
  transcricao,
}: {
  atendimentoId: number;
  mensagemId: number;
  transcricao: string | null;
}) {
  const [texto, setTexto] = useState<string | null>(transcricao);
  const [transcrevendo, setTranscrevendo] = useState(false);

  async function transcrever() {
    setTranscrevendo(true);
    const r = await transcreverMensagemAction(atendimentoId, mensagemId);
    setTranscrevendo(false);
    if (!r.ok) {
      toast.error(r.error);
      return;
    }
    setTexto(r.transcricao);
  }

  if (texto !== null) {
    return (
      <p className="mt-1 whitespace-pre-wrap border-l-2 border-muted-foreground/30 pl-2 text-xs text-muted-foreground">
        <span className="font-medium">Transcrição:</span> {texto}
      </p>
    );
  }
  return (
    <Button
      type="button"
      variant="ghost"
      size="sm"
      className="mt-1 h-7 gap-1 px-2 text-xs text-muted-foreground"
      onClick={() => void transcrever()}
      disabled={transcrevendo}
    >
      <Captions className="size-3.5" />
      {transcrevendo ? "Transcrevendo…" : "Transcrever"}
    </Button>
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

function _bodyText(t: WabaTemplate): string {
  const body = t.componentes_json.find(
    (c) => (c.type || "").toUpperCase() === "BODY"
  );
  return body?.text ?? "";
}

function _varKeys(t: WabaTemplate): string[] {
  const found = new Set<string>();
  for (const m of _bodyText(t).matchAll(/\{\{(\d+)\}\}/g)) found.add(m[1]);
  return [...found].sort((a, b) => Number(a) - Number(b));
}

/** Modal pra enviar um template HSM aprovado ao cliente (reabre fora da 24h). */
function TemplateComposerModal({
  atendimentoId,
  conexaoId,
  provider,
  onClose,
  onSent,
}: {
  atendimentoId: number;
  conexaoId: number;
  provider?: string | null;
  onClose: () => void;
  onSent: () => void;
}) {
  const [templates, setTemplates] = useState<WabaTemplate[] | null>(null);
  const [selId, setSelId] = useState<number | null>(null);
  const [vars, setVars] = useState<Record<string, string>>({});
  const [error, setError] = useState<string | null>(null);
  const [sending, startSend] = useTransition();

  // Só o WABA tem template HSM (espelha _validate_conexao do backend).
  const suporta = provider === "waba";

  useEffect(() => {
    // Conexão sem suporte a HSM (ex: Evolution): nem chama o endpoint (daria
    // 400). O render mostra a nota amigável; nada de setState aqui.
    if (!suporta) return;
    let alive = true;
    loadTemplatesAprovadosAction(conexaoId).then((r) => {
      if (!alive) return;
      if (r.ok) setTemplates(r.data);
      else setError(r.error);
    });
    return () => {
      alive = false;
    };
  }, [conexaoId, suporta]);

  const sel = templates?.find((t) => t.id === selId) ?? null;
  const keys = sel ? _varKeys(sel) : [];

  function confirmar() {
    if (!sel) return;
    setError(null);
    startSend(async () => {
      const r = await enviarTemplateAction(atendimentoId, sel.id, vars);
      if (r.ok) onSent();
      else setError(r.error);
    });
  }

  return (
    <div className="absolute inset-0 z-30 flex items-center justify-center bg-black/50 p-4">
      <div className="w-full max-w-md rounded-xl border bg-card shadow-xl">
        <div className="flex items-center justify-between border-b px-4 py-3">
          <h3 className="flex items-center gap-2 text-sm font-semibold">
            <FileText className="size-4" /> Enviar template
          </h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X className="size-4" />
          </button>
        </div>
        <div className="space-y-3 px-4 py-4 text-sm">
          {!suporta ? (
            <p className="text-xs text-muted-foreground">
              Templates disponíveis apenas para conexões WhatsApp Oficial (WABA)
              . Esta conexão não suporta templates.
            </p>
          ) : templates === null ? (
            <p className="text-xs text-muted-foreground">Carregando templates aprovados…</p>
          ) : templates.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              Nenhum template aprovado nesta conexão. Crie/aprove em Conexões → Templates.
            </p>
          ) : (
            <>
              <select
                value={selId ?? ""}
                onChange={(e) => {
                  setSelId(e.target.value ? Number(e.target.value) : null);
                  setVars({});
                }}
                className="w-full rounded-md border bg-background px-3 py-2 text-sm"
              >
                <option value="">Selecione um template…</option>
                {templates.map((t) => (
                  <option key={t.id} value={t.id}>
                    {t.nome} ({t.idioma})
                  </option>
                ))}
              </select>
              {sel && (
                <p className="rounded-md bg-muted/50 p-2 text-xs text-muted-foreground whitespace-pre-wrap">
                  {_bodyText(sel)}
                </p>
              )}
              {keys.map((k) => (
                <div key={k}>
                  <label className="mb-0.5 block text-xs text-muted-foreground">
                    Variável {`{{${k}}}`}
                  </label>
                  <input
                    value={vars[k] ?? ""}
                    onChange={(e) =>
                      setVars((p) => ({ ...p, [k]: e.target.value }))
                    }
                    className="w-full rounded-md border bg-background px-2 py-1 text-sm"
                    placeholder={k === "1" ? "ex: nome do cliente" : ""}
                  />
                </div>
              ))}
            </>
          )}
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>
        <div className="flex justify-end gap-2 border-t px-4 py-3">
          <Button variant="ghost" size="sm" onClick={onClose} disabled={sending}>
            Cancelar
          </Button>
          <Button
            size="sm"
            onClick={confirmar}
            disabled={sending || !sel || keys.some((k) => !(vars[k] ?? "").trim())}
          >
            {sending ? "Enviando…" : "Enviar template"}
          </Button>
        </div>
      </div>
    </div>
  );
}
