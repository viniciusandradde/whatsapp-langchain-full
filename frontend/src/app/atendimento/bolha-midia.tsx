"use client";

import { useState } from "react";
import { Captions, Paperclip } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";

import { transcreverMensagemAction } from "./actions";

/**
 * Mídia dentro da bolha (imagem, áudio, vídeo, documento) — a mesma peça
 * serve à timeline e à seção Arquivos do painel de informações.
 *
 * Suporta `data:` (worker pré-fetch via Evolution) e URL HTTP do proxy; o
 * navegador renderiza inline em <img>/<audio>/<video> sem backend extra.
 */
export function MediaPreview({
  url,
  type,
  caption,
  nome,
}: {
  url: string;
  type: string | null;
  caption?: string;
  /** Nome legível do arquivo, quando conhecido (rótulo do documento). */
  nome?: string | null;
}) {
  const mime = (type || "").toLowerCase();

  if (mime.startsWith("image/")) {
    return (
      <div className="space-y-1">
        <a href={url} target="_blank" rel="noopener noreferrer">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={url}
            alt={caption || "imagem"}
            className="max-h-64 max-w-full rounded-lg border border-border/40 object-contain"
          />
        </a>
        {caption && <p className="whitespace-pre-wrap text-sm">{caption}</p>}
      </div>
    );
  }

  if (mime.startsWith("audio/")) {
    return (
      <div className="space-y-1">
        {/* Largura fixa: dentro da bolha (que encolhe ao conteúdo) o player
            com `w-full` colapsava a zero. */}
        <audio controls src={url} className="w-64 max-w-full" preload="metadata">
          Seu navegador não suporta player de áudio.
        </audio>
        {caption && <p className="whitespace-pre-wrap text-sm">{caption}</p>}
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
        {caption && <p className="whitespace-pre-wrap text-sm">{caption}</p>}
      </div>
    );
  }

  // Documento (PDF/DOCX) ou tipo desconhecido — link de download. Sem o nome
  // real do arquivo (a row de saída ainda não o guarda), o rótulo vem do tipo.
  const rotulo = nome || rotuloDocumento(mime);
  return (
    <div className="space-y-1">
      <a
        href={url}
        target="_blank"
        rel="noopener noreferrer"
        download
        className="inline-flex max-w-full items-center gap-1.5 rounded-md border border-border/40 bg-background px-2 py-1 text-xs underline hover:bg-muted"
      >
        <Paperclip className="size-3.5 shrink-0" aria-hidden />
        <span className="truncate">{rotulo}</span>
        <span className="shrink-0 text-muted-foreground">— abrir</span>
      </a>
      {caption && <p className="whitespace-pre-wrap text-sm">{caption}</p>}
    </div>
  );
}

function rotuloDocumento(mime: string): string {
  if (mime.includes("pdf")) return "Documento PDF";
  if (mime.includes("word") || mime.includes("officedocument.wordprocessingml")) return "Documento Word";
  if (mime.includes("sheet") || mime.includes("excel")) return "Planilha";
  if (mime.includes("presentation") || mime.includes("powerpoint")) return "Apresentação";
  if (mime.includes("zip") || mime.includes("compressed")) return "Arquivo compactado";
  if (mime.startsWith("text/")) return "Arquivo de texto";
  return mime ? `Arquivo (${mime.split("/").pop()})` : "Documento";
}

/**
 * Transcrição da nota de voz pro operador (mig 169).
 *
 * Se a mensagem já tem transcrição (automática por conexão ou de um clique
 * anterior), mostra o texto direto. Senão, oferece o botão — o servidor é
 * idempotente, então cliques repetidos não pagam LLM de novo.
 */
export function TranscricaoAudio({
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
