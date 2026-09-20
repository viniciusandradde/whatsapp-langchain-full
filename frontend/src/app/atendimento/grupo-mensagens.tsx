"use client";

import { useState } from "react";
import { Lock, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { ConfirmDestrutivo } from "@/components/confirm-destrutivo";
import { cn } from "@/lib/utils";
import type { AtendimentoMensagem } from "@/lib/api";

import { apagarMensagemAction, reprocessarMensagemAction } from "./actions";
import { BolhaMenu } from "./bolha-menu";
import { MediaPreview, TranscricaoAudio } from "./bolha-midia";
import {
  formatarDataHoraCompleta,
  formatarHoraCurta,
  type Bolha,
  type GrupoBolhas,
  type Nota,
} from "./timeline";

/**
 * Um grupo de bolhas consecutivas do mesmo remetente: UM cabeçalho
 * ("Cliente · 15:08") e os balões empilhados com pouco espaço — como no
 * WhatsApp. Data completa, remetente e id ficam no menu de cada bolha e no
 * `title`, não repetidos em cada balão.
 */
export function GrupoMensagens({
  grupo,
  atendimentoId,
  agora,
  onAlterou,
  onEditar,
}: {
  grupo: GrupoBolhas;
  atendimentoId: number;
  /** Relógio injetado (tick da conversa) — mantém o render puro. */
  agora: Date;
  /** Recarrega a timeline depois de apagar/reprocessar. */
  onAlterou: () => void;
  /** Mig 172 — pede ao drawer pra entrar em modo edição com esta mensagem. */
  onEditar?: (m: AtendimentoMensagem) => void;
}) {
  const saida = grupo.lado === "out";
  return (
    <div className={cn("flex flex-col gap-0.5", saida ? "items-end" : "items-start")}>
      <p
        className={cn(
          "mb-0.5 px-1 font-mono text-[10px] text-muted-foreground",
          saida && "text-right"
        )}
      >
        {grupo.remetente} · {formatarHoraCurta(grupo.inicio, agora)}
      </p>
      {grupo.bolhas.map((b) => (
        <BolhaItem
          key={b.chave}
          bolha={b}
          atendimentoId={atendimentoId}
          onAlterou={onAlterou}
          onEditar={onEditar}
        />
      ))}
    </div>
  );
}

function BolhaItem({
  bolha: b,
  atendimentoId,
  onAlterou,
  onEditar,
}: {
  bolha: Bolha;
  atendimentoId: number;
  onAlterou: () => void;
  onEditar?: (m: AtendimentoMensagem) => void;
}) {
  const m = b.msg;
  // Guardas do menu (paridade com o app): bolha apagada ou de erro é inerte;
  // Copiar exige texto; Editar/Apagar só na resposta outbound e só quando o
  // servidor calculou que a janela ainda vale.
  const inerte = b.kind === "text" && (b.erro === true || b.apagada === true);
  const copiavel = inerte
    ? null
    : b.kind === "text"
      ? b.text
      : [b.caption, b.transcrevivel ? m.transcricao : null].filter(Boolean).join("\n") || null;
  const podeEditar =
    !inerte && b.lado === "out" && b.kind === "text" && m.pode_editar_resposta === true;
  const podeApagar = !inerte && b.lado === "out" && m.pode_apagar_resposta === true;
  const detalhes = `${formatarDataHoraCompleta(m.created_at)} · ${b.remetente} · #${m.id}`;

  async function apagar() {
    const r = await apagarMensagemAction(atendimentoId, m.id);
    if (!r.ok) {
      // Janela de 48h vencida ou canal sem suporte (WABA) — frase do backend.
      toast.error(r.error);
      return;
    }
    toast.success("Mensagem apagada para todos");
    onAlterou();
  }

  const conteudo = (
    <div
      title={detalhes}
      className={cn(
        "rounded-2xl px-3 py-1.5 text-sm",
        b.lado === "out"
          ? "rounded-br-md bg-primary/15 text-foreground"
          : "rounded-bl-md bg-secondary text-foreground",
        b.kind === "text" && b.erro && "border border-destructive/40 bg-destructive/5"
      )}
    >
      {b.kind === "media" ? (
        <>
          <MediaPreview url={b.mediaUrl} type={b.mediaType} caption={b.caption} />
          {b.transcrevivel && (
            <TranscricaoAudio
              atendimentoId={atendimentoId}
              mensagemId={m.id}
              transcricao={m.transcricao ?? null}
            />
          )}
        </>
      ) : (
        <p className={cn("whitespace-pre-wrap wrap-anywhere", b.apagada && "italic text-muted-foreground")}>
          {b.text}
        </p>
      )}
      {b.kind === "text" && b.erro && (
        <div className="mt-1 flex items-center justify-between gap-2">
          <span className="truncate font-mono text-[10px] text-muted-foreground">
            erro · {(m.error ?? "").slice(0, 60)}
          </span>
          {b.podeReprocessar && (
            <BotaoReprocessar
              atendimentoId={atendimentoId}
              messageId={m.id}
              onReprocessado={onAlterou}
              compacto
            />
          )}
        </div>
      )}
    </div>
  );

  // O teto de largura fica no invólucro (filho direto da linha flex): na
  // bolha em si, a porcentagem resolvia contra o wrapper do menu — que
  // encolhe ao conteúdo — e o texto quebrava cedo demais.
  return (
    <div className={cn("flex w-full", b.lado === "out" ? "justify-end" : "justify-start")}>
      <div className="min-w-0 max-w-[85%] sm:max-w-[75%]">
        <BolhaMenu
          copiarTexto={copiavel}
          podeEditar={podeEditar}
          podeApagar={podeApagar}
          detalhes={detalhes}
          onEditar={onEditar ? () => onEditar(m) : undefined}
          onApagar={apagar}
        >
          {conteudo}
        </BolhaMenu>
      </div>
    </div>
  );
}

/** Nota interna — largura cheia, tom de aviso, nunca vai ao cliente. */
export function NotaInterna({ nota, agora }: { nota: Nota; agora: Date }) {
  const m = nota.msg;
  return (
    <div className="flex justify-center">
      <div className="w-full max-w-[92%] rounded-lg border border-warning/40 bg-warning/10 px-3 py-1.5 text-sm">
        <p className="mb-0.5 flex items-center gap-1 font-mono text-[10px] text-warning">
          <Lock className="size-3" aria-hidden />
          Nota interna · {m.criado_por_user_id ?? "—"} · {formatarHoraCurta(m.created_at, agora)}
        </p>
        <p className="whitespace-pre-wrap wrap-anywhere text-foreground">{m.response}</p>
      </div>
    </div>
  );
}

/**
 * Botão de reprocesso — mensagem que ficou SEM resposta pro cliente
 * (`failed`, ou pulada por modo manual / lista de bloqueio). Confirma antes:
 * manda WhatsApp real e gasta token. O backend revalida os gates e devolve
 * 409 com frase acionável se a condição ainda vale.
 */
export function BotaoReprocessar({
  atendimentoId,
  messageId,
  onReprocessado,
  compacto = false,
}: {
  atendimentoId: number;
  messageId: number;
  onReprocessado: () => void;
  compacto?: boolean;
}) {
  const [enviando, setEnviando] = useState(false);
  const [confirmando, setConfirmando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);

  async function reprocessar() {
    if (enviando) return;
    setEnviando(true);
    setErro(null);
    const r = await reprocessarMensagemAction(atendimentoId, messageId);
    setEnviando(false);
    if (r.ok) onReprocessado();
    else setErro(r.error);
  }

  return (
    <div className={cn("flex flex-col gap-1", compacto ? "items-end" : "items-start")}>
      <button
        type="button"
        onClick={() => setConfirmando(true)}
        disabled={enviando}
        className="inline-flex items-center gap-1 rounded-md border border-foreground/15 px-2 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-foreground/5 disabled:opacity-50"
      >
        <RefreshCw className={cn("size-3", enviando && "animate-spin")} aria-hidden />
        {enviando ? "Reprocessando…" : "Reprocessar com IA"}
      </button>
      {erro ? <span className="text-[11px] text-destructive">{erro}</span> : null}
      <ConfirmDestrutivo
        aberto={confirmando}
        onAbertoChange={setConfirmando}
        titulo="Reprocessar esta mensagem com a IA?"
        descricao="A IA vai responder e o cliente recebe a mensagem no WhatsApp."
        rotuloAcao="Reprocessar"
        tom="serio"
        onConfirmar={() => void reprocessar()}
      />
    </div>
  );
}
