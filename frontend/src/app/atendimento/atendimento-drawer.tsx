"use client";

import { useEffect, useReducer, useRef, useState, useTransition } from "react";
import { FileText, Loader2, Lock, Pencil, Send, ShieldOff, X } from "lucide-react";

import { toast } from "sonner";

import { ConfirmDestrutivo } from "@/components/confirm-destrutivo";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { useLarguraElemento } from "@/hooks/use-largura-elemento";
import { useLocalStorage } from "@/hooks/use-local-storage";
import { usePermission } from "@/hooks/use-permission";
import type { Atendimento, AtendimentoMensagem, ModeloMensagem, WabaTemplate } from "@/lib/api";
import { cn } from "@/lib/utils";

import {
  claimAction,
  closeAction,
  criarNotaInternaAction,
  devolverParaIaAction,
  editarMensagemAction,
  enviarTemplateAction,
  incluirNumeroSemIaAction,
  loadMensagensAction,
  loadModelosAction,
  loadTemplatesAprovadosAction,
  marcarAtendimentoLidoAction,
  resetThreadAction,
  responderAction,
  transferAction,
  transferDepartamentoAction,
} from "./actions";
import { AvisoIa } from "./aviso-ia";
import { CabecalhoConversa } from "./cabecalho-conversa";
import { ComposerMenu } from "./composer-menu";
import {
  ACCEPT_ANEXO,
  AnexosPreview,
  ComposerMidiaBotoes,
  criarAnexos,
  descartarAnexos,
  enviarAnexo,
  imagemColada,
  type AnexoPendente,
} from "./composer-midia";
import { GrupoMensagens, NotaInterna } from "./grupo-mensagens";
import { PainelInfo } from "./info-conversa";
import { ModelosPopover } from "./modelos-popover";
import { montarTimeline } from "./timeline";
import { TransferirDialog } from "./transferir-dialog";

interface Props {
  atendimento: Atendimento;
  /** Nome do setor (a lista já tem o mapa id→nome; o drawer só exibe). */
  departamentoNome?: string | null;
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

/** Altura máxima do campo antes de rolar por dentro (~6 linhas). */
const COMPOSER_MAX_PX = 160;
/**
 * Largura mínima da coluna da conversa (em px) pra o painel de informações
 * abrir como 3ª coluna em vez de sheet: 320 do painel + ~560 de conversa.
 * Abaixo disso a conversa viraria uma tira — o que se viu a 1440px com os
 * dois sidebars abertos e a lista em 440.
 */
const LARGURA_MIN_COLUNA_INFO = 880;

/**
 * Conversa (conversa compacta, 2026-09): "menos interface, mais conversa".
 *
 * Do topo ao rodapé só o que a interação imediata precisa — cabeçalho de
 * uma linha e meia, a timeline ocupando o resto, o composer de uma linha.
 * Tudo o que era permanente (painel do cliente, abas, triagem, coleta, linha
 * de nota interna/template, barra com 4 ações) continua disponível, mas a
 * um toque: painel de informações (`info-conversa.tsx`), menu ⋮
 * (`cabecalho-conversa.tsx`) e menu `+` do composer (`composer-menu.tsx`).
 */
export function AtendimentoDrawer({
  atendimento,
  departamentoNome,
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
  // entrar em edição desliga a nota, e o item do menu fica desabilitado.
  const [editando, setEditando] = useState<{ id: number; original: string } | null>(null);
  const [templateModalOpen, setTemplateModalOpen] = useState(false);
  const [sending, setSending] = useState(false);
  // Anexos pendentes (fotos, documentos) — o "Enviar" de sempre manda todos
  // em sequência, o texto do composer vai de legenda no primeiro. A nota de
  // voz NÃO passa por aqui: parar a gravação envia na hora (como no
  // WhatsApp). Ver composer-midia.tsx.
  const [anexos, setAnexos] = useState<AnexoPendente[]>([]);
  const [enviandoIndice, setEnviandoIndice] = useState<number | null>(null);
  const [arrastando, setArrastando] = useState(false);
  const anexosRef = useRef<AnexoPendente[]>([]);
  const inputArquivoRef = useRef<HTMLInputElement | null>(null);
  useEffect(() => {
    anexosRef.current = anexos;
  }, [anexos]);
  // Fechou a conversa com anexos pendentes: solta os object URLs das prévias.
  useEffect(() => () => descartarAnexos(anexosRef.current), []);
  function anexar(files: Iterable<File>) {
    const { anexos: novos, erro } = criarAnexos(files);
    setError(erro);
    if (novos.length === 0) return;
    setAnexos((prev) => [...prev, ...novos]);
    composerRef.current?.focus();
  }
  function removerAnexo(indice: number) {
    setAnexos((prev) => {
      const alvo = prev[indice];
      if (alvo) descartarAnexos([alvo]);
      return prev.filter((_, i) => i !== indice);
    });
  }
  /** Nota de voz gravada: manda na hora, sem prévia nem segundo clique. */
  async function enviarNotaDeVoz(nota: AnexoPendente) {
    if (sending) return;
    setSending(true);
    setError(null);
    const r = await enviarAnexo(atendimento.id, nota, "");
    descartarAnexos([nota]);
    setSending(false);
    if (!r.ok) {
      setError(r.error);
      return;
    }
    await reload();
  }
  const [modelos, setModelos] = useState<ModeloMensagem[] | null>(null);
  // Busca de modelos ancorada ao composer — aberta pelo "/" no campo vazio,
  // pelo menu `+` e pelo ⋮ do cabeçalho (o painel antigo do kebab, flutuante
  // no canto, foi unificado aqui).
  const [modelosOpen, setModelosOpen] = useState(false);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  const [isPending, startTransition] = useTransition();

  // Painel de informações (contato, tags, triagem, histórico, arquivos):
  // coluna lateral no desktop (preferência lembrada) e bottom sheet no
  // celular (nasce fechado).
  const [infoDesktop, setInfoDesktop] = useLocalStorage<boolean>("atd-info-aberta", false);
  const [infoMobile, setInfoMobile] = useState(false);
  const [infoSecao, setInfoSecao] = useState<"contato" | "arquivos">("contato");
  const infoAberta = modo === "painel" ? infoDesktop : infoMobile;
  const [asideRef, larguraAside] = useLarguraElemento<HTMLElement>();
  const recipienteInfo: "coluna" | "lateral" | "inferior" =
    modo === "drawer"
      ? "inferior"
      : (larguraAside ?? 0) >= LARGURA_MIN_COLUNA_INFO
        ? "coluna"
        : "lateral";
  function definirInfo(v: boolean) {
    if (modo === "painel") setInfoDesktop(v);
    else setInfoMobile(v);
  }
  function abrirInfo(secao: "contato" | "arquivos" = "contato") {
    setInfoSecao(secao);
    // Já aberto no contato e tocou de novo no avatar: fecha (toggle).
    if (infoAberta && secao === "contato" && infoSecao === "contato") {
      definirInfo(false);
      return;
    }
    definirInfo(true);
  }

  // Diálogos das ações (no lugar de `confirm()`/`alert()` do navegador).
  const [transferOpen, setTransferOpen] = useState(false);
  const [confirmarFechar, setConfirmarFechar] = useState<"resolvido" | "abandonado" | null>(null);
  const [confirmarReset, setConfirmarReset] = useState(false);

  async function reload() {
    setLoading(true);
    setError(null);
    const r = await loadMensagensAction(atendimento.id);
    if (!r.ok) setError(r.error);
    else setMensagens(r.mensagens);
    setLoading(false);
  }

  // Silent reload: usado pelo SSE/polling — não toca em `loading` pra evitar
  // flicker. Erros transitórios são engolidos pra não poluir o painel.
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
  }, [mensagens]);

  // Relógio da timeline: o cabeçalho de grupo diz só a hora no MESMO dia —
  // uma conversa aberta à meia-noite precisa virar "18/09 · 23:58". Um tick
  // por minuto; o render lê `agora` do estado, como o React Compiler exige.
  const [agoraMs, tick] = useReducer(() => Date.now(), 0, () => Date.now());
  useEffect(() => {
    const t = setInterval(tick, 60_000);
    return () => clearInterval(t);
  }, []);

  // E2.E SSE: substitui polling 3s por EventSource. Backend dispara
  // eventos via Postgres LISTEN/NOTIFY (mig 035) — chega <1s do INSERT
  // da mensagem. Fallback automático: EventSource reconecta sozinho se
  // a conexão cair, e em erro fatal a gente cai pra polling 5s como
  // safety net.
  useEffect(() => {
    const isActive =
      atendimento.status === "aguardando" || atendimento.status === "em_andamento";
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

  const isOpen =
    atendimento.status === "aguardando" || atendimento.status === "em_andamento";

  function transferir(destino: { departamentoId: number } | { userId: string }) {
    if ("departamentoId" in destino) {
      runAction(() => transferDepartamentoAction(atendimento.id, destino.departamentoId));
    } else {
      runAction(() => transferAction(atendimento.id, destino.userId));
    }
  }

  function fecharAtendimento(status: "resolvido" | "abandonado") {
    runAction(() => closeAction(atendimento.id, status), { encerra: true });
  }

  async function resetarConversa() {
    setError(null);
    const r = await resetThreadAction(atendimento.id);
    if (!r.ok) {
      setError(r.error);
      return;
    }
    toast.success(
      `Conversa do agente resetada (${r.rowsDeleted} registros). A próxima mensagem do cliente começa do zero.`
    );
  }

  async function confirmarIncluirSemIa() {
    const telefone = atendimento.cliente_telefone;
    if (!telefone) return;
    setSemIaPending(true);
    const r = await incluirNumeroSemIaAction(telefone, atendimento.cliente_nome ?? null);
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

  function abrirModelos() {
    if (modelos === null) {
      void loadModelosAction().then((r) => {
        if (r.ok) setModelos(r.modelos);
        else setError(r.error);
      });
    }
    setModelosOpen(true);
  }

  function escolherModelo(m: ModeloMensagem) {
    setComposer((prev) => (prev ? `${prev}\n${m.conteudo}` : m.conteudo));
    setModelosOpen(false);
    composerRef.current?.focus();
  }

  function iniciarEdicao(m: AtendimentoMensagem) {
    setEditando({ id: m.id, original: m.response ?? "" });
    setComposer(m.response ?? "");
    setComposerInterna(false);
    composerRef.current?.focus();
  }

  function sairEdicao() {
    setEditando(null);
    setComposer("");
  }

  async function handleSend() {
    const text = composer.trim();
    if (sending) return;
    if (anexos.length > 0 && !editando && !composerInterna) {
      // Mídia: um envio por arquivo, em sequência; a legenda vai no primeiro.
      // Falhou no meio → os que sobraram ficam na prévia pra tentar de novo.
      setSending(true);
      setError(null);
      const fila = [...anexos];
      for (let i = 0; i < fila.length; i++) {
        setEnviandoIndice(i);
        const r = await enviarAnexo(atendimento.id, fila[i], i === 0 ? text : "");
        if (!r.ok) {
          setError(`${fila[i].file.name}: ${r.error}`);
          descartarAnexos(fila.slice(0, i));
          setAnexos(fila.slice(i));
          setEnviandoIndice(null);
          setSending(false);
          await reload();
          return;
        }
      }
      descartarAnexos(fila);
      setAnexos([]);
      setEnviandoIndice(null);
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

  // Campo de uma linha que cresce com o texto até um teto; acima disso rola
  // por dentro. Sincronizado com o VALOR (não só com a digitação): enviar,
  // inserir modelo e entrar em edição também mudam a altura certa.
  useEffect(() => {
    const el = composerRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, COMPOSER_MAX_PX)}px`;
  }, [composer]);

  const agora = new Date(agoraMs);
  const itens = mensagens ? montarTimeline(mensagens, atendimento.id) : [];
  const podeEnviar = !sending && (composer.trim().length > 0 || anexos.length > 0);
  const rotuloEnviar = sending
    ? enviandoIndice !== null
      ? `Enviando ${enviandoIndice + 1}/${anexos.length}…`
      : "Enviando…"
    : editando
      ? "Salvar edição"
      : anexos.length > 1
        ? `Enviar ${anexos.length} anexos`
        : anexos.length === 1
          ? "Enviar anexo"
          : composerInterna
            ? "Salvar nota interna"
            : "Enviar";

  const conteudo = (
    <aside
      ref={asideRef}
      className={
        modo === "painel"
          ? "flex h-full min-h-0 w-full flex-row bg-card"
          : "flex h-full w-full max-w-3xl flex-row bg-card shadow-2xl"
      }
      onClick={(e) => e.stopPropagation()}
    >
      <div className="flex h-full min-h-0 min-w-0 flex-1 flex-col">
        <CabecalhoConversa
          atendimento={atendimento}
          departamentoNome={departamentoNome}
          modo={modo}
          pendente={isPending}
          infoAberta={infoAberta}
          onVoltar={onClose}
          onAbrirInfo={abrirInfo}
          acoes={{
            onAtender: () => runAction(() => claimAction(atendimento.id)),
            // Desfaz o "Atender". Enquanto o atendimento tem dono o worker
            // cala o agente; nada é enviado ao cliente aqui — a IA só volta
            // a responder.
            onDevolverParaIa: () => runAction(() => devolverParaIaAction(atendimento.id)),
            onTransferir: () => setTransferOpen(true),
            onResolver: () => setConfirmarFechar("resolvido"),
            onAbandonar: () => setConfirmarFechar("abandonado"),
            onInserirModelo: abrirModelos,
            onAtualizar: () => void reload(),
            onResetarConversa: () => setConfirmarReset(true),
            onIncluirSemIa:
              podeGerirSemIa && atendimento.cliente_telefone
                ? () => setSemIaOpen(true)
                : undefined,
          }}
        />

        {/* Timeline — ocupa tudo entre o cabeçalho e o composer. */}
        <div
          ref={timelineRef}
          onScroll={(e) => {
            const el = e.currentTarget;
            grudadoNoFimRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120;
          }}
          className="flex min-h-0 flex-1 flex-col gap-2.5 overflow-y-auto px-3 py-3 sm:px-4"
        >
          {error && (
            <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
              {error}
            </div>
          )}

          {loading && !mensagens && (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-3.5 animate-spin" aria-hidden />
              Carregando mensagens…
            </p>
          )}

          {!loading && mensagens && mensagens.length === 0 && (
            <p className="text-sm text-muted-foreground">
              Nenhuma mensagem registrada para este atendimento ainda.
            </p>
          )}

          {itens.map((item) =>
            item.tipo === "grupo" ? (
              <GrupoMensagens
                key={item.chave}
                grupo={item}
                atendimentoId={atendimento.id}
                agora={agora}
                onAlterou={() => void reload()}
                onEditar={iniciarEdicao}
              />
            ) : item.tipo === "nota" ? (
              <NotaInterna key={item.chave} nota={item} agora={agora} />
            ) : (
              <AvisoIa
                key={item.chave}
                aviso={item}
                atendimentoId={atendimento.id}
                onReprocessado={() => void reload()}
              />
            )
          )}
        </div>

        {isOpen && (
          <div
            className={cn(
              "relative shrink-0 border-t px-2 py-1.5 sm:px-3",
              composerInterna ? "bg-warning/10" : "bg-background/40"
            )}
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
              const files = Array.from(e.dataTransfer.files ?? []);
              if (files.length === 0) return;
              e.preventDefault();
              anexar(files);
            }}
          >
            {arrastando && (
              <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center rounded-md border-2 border-dashed border-brand-primary/60 bg-background/90 text-sm font-medium text-brand-primary">
                Solte para anexar
              </div>
            )}
            {modelosOpen && (
              <ModelosPopover
                modelos={modelos}
                onEscolher={escolherModelo}
                onFechar={() => {
                  setModelosOpen(false);
                  composerRef.current?.focus();
                }}
              />
            )}
            {/* Seletor de arquivos do menu `+` (colar/arrastar também anexam). */}
            <Input
              ref={inputArquivoRef}
              type="file"
              accept={ACCEPT_ANEXO}
              multiple
              onChange={(e) => {
                const files = Array.from(e.target.files ?? []);
                e.target.value = "";
                if (files.length) anexar(files);
              }}
              className="sr-only"
              tabIndex={-1}
              aria-hidden
            />

            {/* Modo do composer: só aparece quando NÃO é o envio normal. */}
            {editando && (
              <ModoComposer
                icone={Pencil}
                texto="Editando mensagem — Enter salva, Esc cancela"
                onSair={sairEdicao}
                rotuloSair="Cancelar edição"
                className="border-brand-primary/40 bg-brand-primary/5"
              />
            )}
            {composerInterna && !editando && (
              <ModoComposer
                icone={Lock}
                texto="Nota interna — só a equipe vê, não vai para o cliente"
                onSair={() => setComposerInterna(false)}
                rotuloSair="Voltar a responder ao cliente"
                className="border-warning/40 bg-warning/10 text-warning"
              />
            )}
            {anexos.length > 0 && (
              <AnexosPreview
                anexos={anexos}
                enviando={sending}
                enviandoIndice={enviandoIndice}
                onRemover={removerAnexo}
              />
            )}

            <div className="flex items-end gap-1">
              <ComposerMenu
                disabled={sending || editando !== null}
                notaInterna={composerInterna}
                onAnexar={() => inputArquivoRef.current?.click()}
                onTemplate={() => setTemplateModalOpen(true)}
                onNotaInterna={(v) => {
                  if (anexos.length > 0 && v) {
                    setError("Remova os anexos para escrever uma nota interna.");
                    return;
                  }
                  setComposerInterna(v);
                  composerRef.current?.focus();
                }}
                onModelo={abrirModelos}
              />
              <Textarea
                ref={composerRef}
                value={composer}
                onChange={(e) => setComposer(e.target.value)}
                onPaste={(e) => {
                  if (editando || composerInterna) return;
                  const img = imagemColada(e);
                  if (!img) return;
                  e.preventDefault();
                  anexar([img]);
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
                    abrirModelos();
                  }
                }}
                placeholder={
                  editando
                    ? "Corrija o texto da mensagem…"
                    : composerInterna
                      ? "Anotação privada da equipe…"
                      : anexos.length > 0
                        ? "Legenda (opcional)…"
                        : "Digite uma mensagem…"
                }
                rows={1}
                disabled={sending}
                aria-label={composerInterna ? "Nota interna" : "Mensagem para o cliente"}
                title="Enter envia · Shift+Enter quebra linha · / abre os modelos"
                className={cn(
                  "min-h-9 max-h-40 resize-none rounded-2xl px-3 py-1.5 text-sm leading-6",
                  composerInterna
                    ? "border-warning/50 bg-background focus-visible:border-warning"
                    : "bg-background"
                )}
              />
              <ComposerMidiaBotoes
                clipe={false}
                disabled={sending || editando !== null || composerInterna}
                onAnexos={(novos) => {
                  setError(null);
                  setAnexos((prev) => [...prev, ...novos]);
                }}
                onGravacao={(nota) => void enviarNotaDeVoz(nota)}
                onErro={setError}
              />
              <Button
                size="icon"
                onClick={() => void handleSend()}
                disabled={!podeEnviar}
                aria-label={rotuloEnviar}
                title={rotuloEnviar}
                className="shrink-0 rounded-full"
              >
                {sending ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : editando ? (
                  <Pencil className="size-4" />
                ) : (
                  <Send className="size-4" />
                )}
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
      </div>

      {/* Espera a 1ª medição do aside: montar como sheet e trocar pra coluna
          um frame depois faria o painel buscar tags e histórico duas vezes. */}
      <PainelInfo
        aberto={infoAberta && (modo === "drawer" || larguraAside !== undefined)}
        recipiente={recipienteInfo}
        onAbertoChange={definirInfo}
        atendimento={atendimento}
        departamentoNome={departamentoNome}
        mensagens={mensagens}
        secao={infoSecao}
        onFechar={() => definirInfo(false)}
      />

      <TransferirDialog
        aberto={transferOpen}
        onAbertoChange={setTransferOpen}
        pendente={isPending}
        onConfirmar={transferir}
      />

      <ConfirmDestrutivo
        aberto={confirmarFechar !== null}
        onAbertoChange={(v) => !v && setConfirmarFechar(null)}
        titulo={
          confirmarFechar === "abandonado"
            ? "Fechar como abandonado?"
            : "Resolver este atendimento?"
        }
        objeto={atendimento.cliente_nome ?? atendimento.cliente_telefone ?? undefined}
        descricao={
          confirmarFechar === "abandonado"
            ? "A conversa sai da caixa como encerrada sem resolução."
            : "A conversa sai da caixa como resolvida. Se a pesquisa de satisfação estiver ativa, o cliente recebe a pergunta."
        }
        rotuloAcao={confirmarFechar === "abandonado" ? "Abandonar" : "Resolver"}
        tom={confirmarFechar === "abandonado" ? "destrutivo" : "serio"}
        onConfirmar={() => {
          if (confirmarFechar) fecharAtendimento(confirmarFechar);
        }}
      />

      <ConfirmDestrutivo
        aberto={confirmarReset}
        onAbertoChange={setConfirmarReset}
        titulo="Resetar conversa do agente?"
        descricao={
          <>
            <p>
              Apaga o histórico LangGraph (checkpoint) deste número. A próxima
              mensagem começa do zero — útil quando o agente está replicando um
              padrão errado das últimas respostas.
            </p>
            <p>Não afeta: mensagens da timeline, memórias semânticas, dados do cliente.</p>
          </>
        }
        rotuloAcao="Resetar"
        onConfirmar={() => void resetarConversa()}
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
                Nenhuma conexão da empresa vai responder automaticamente a esse
                número — sem agente, menu ou mensagens automáticas — até que ele
                seja removido na tela Números sem IA.
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
              <Button onClick={() => void confirmarIncluirSemIa()} disabled={semIaPending}>
                {semIaPending ? "Incluindo…" : "Incluir número"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
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

/** Faixa fina acima do campo dizendo em que modo o composer está. */
function ModoComposer({
  icone: Icone,
  texto,
  rotuloSair,
  onSair,
  className,
}: {
  icone: React.ComponentType<{ className?: string }>;
  texto: string;
  rotuloSair: string;
  onSair: () => void;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "mb-1.5 flex items-center justify-between gap-2 rounded-md border px-2 py-1 text-xs",
        className
      )}
    >
      <span className="flex min-w-0 items-center gap-1.5 font-medium">
        <Icone className="size-3 shrink-0" />
        <span className="truncate">{texto}</span>
      </span>
      <button
        type="button"
        aria-label={rotuloSair}
        title={rotuloSair}
        onClick={onSair}
        className="shrink-0 rounded p-0.5 hover:bg-foreground/10"
      >
        <X className="size-3.5" />
      </button>
    </div>
  );
}

function _bodyText(t: WabaTemplate): string {
  const body = t.componentes_json.find((c) => (c.type || "").toUpperCase() === "BODY");
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
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <FileText className="size-4" /> Enviar template
          </DialogTitle>
          <DialogDescription>
            Template HSM aprovado — reabre a conversa fora da janela de 24h.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3 text-sm">
          {!suporta ? (
            <p className="text-xs text-muted-foreground">
              Templates disponíveis apenas para conexões WhatsApp Oficial (WABA).
              Esta conexão não suporta templates.
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
                aria-label="Template"
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
                  <Input
                    value={vars[k] ?? ""}
                    onChange={(e) => setVars((p) => ({ ...p, [k]: e.target.value }))}
                    placeholder={k === "1" ? "ex: nome do cliente" : ""}
                  />
                </div>
              ))}
            </>
          )}
          {error && <p className="text-xs text-destructive">{error}</p>}
        </div>
        <DialogFooter>
          <Button variant="outline" size="sm" onClick={onClose} disabled={sending}>
            Cancelar
          </Button>
          <Button
            size="sm"
            onClick={confirmar}
            disabled={sending || !sel || keys.some((k) => !(vars[k] ?? "").trim())}
          >
            {sending ? "Enviando…" : "Enviar template"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
