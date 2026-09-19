"use client";

import { useEffect, useRef, useState } from "react";
import { FileText, Loader2, Mic, Paperclip, Square, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

/**
 * Áudio (nota de voz) e anexos pelo composer web — a parte que faltava para a
 * paridade com o ZigChat (`docs/ANALISE_AUDIO_ANEXO_ATENDIMENTO.md`).
 *
 * O backend já existia (`/responder-midia`, usado pelo app Android); aqui
 * entram o clipe, o microfone, a prévia e o envio pelo proxy
 * `/api/proxy/midia/{id}` (Route Handler — Server Action tem corpo de 1 MB).
 *
 * O ESTADO do anexo pendente mora no drawer (`anexo`/`setAnexo`): é o botão
 * "Enviar" de sempre que manda, com o texto do composer como legenda — uma
 * mensagem só, como no WhatsApp. Este arquivo tem a UI (botões, gravação,
 * prévia) e os helpers puros (validar, montar, enviar).
 *
 * A gravação usa `MediaRecorder` com o formato que o navegador der (WebM no
 * Chrome, MP4 no Safari, OGG no Firefox): quem converte para OGG/Opus — o
 * único que o WhatsApp aceita como nota de voz — é o servidor
 * (`shared/audio.py`). Gravar é por TOQUE (toque começa, toque para): igual
 * no desktop e no celular, sem gesto de segurar que escapa.
 */

export type TipoAnexo = "imagem" | "video" | "audio" | "documento";

export interface AnexoPendente {
  file: File;
  tipo: TipoAnexo;
  /** Object URL para a prévia; quem descarta chama `descartarAnexo`. */
  previewUrl: string;
}

/** Espelho de `MIDIA_MIMES_ACEITOS` e `MIDIA_MAX_BYTES` da API. */
const MIMES_ACEITOS = [
  "audio/",
  "image/jpeg",
  "image/png",
  "image/webp",
  "image/gif",
  "video/mp4",
  "application/pdf",
  "application/msword",
  "application/vnd.openxmlformats-officedocument",
  "application/vnd.ms-excel",
  "text/plain",
];
const TAMANHO_MAX_BYTES = 16 * 1024 * 1024;
// Tipos explícitos (sem `image/*`): no iPhone, restringir é o que faz o
// seletor entregar JPEG em vez de HEIC, que a API recusa.
export const ACCEPT_ANEXO =
  "image/jpeg,image/png,image/webp,image/gif,video/mp4,application/pdf,.doc,.docx,.xls,.xlsx,.txt";

function tipoDe(mime: string): TipoAnexo {
  if (mime.startsWith("image/")) return "imagem";
  if (mime.startsWith("video/")) return "video";
  if (mime.startsWith("audio/")) return "audio";
  return "documento";
}

function formatarTamanho(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

/** Valida tipo/tamanho como a API faria e monta o anexo com a prévia. */
export function criarAnexo(file: File): { ok: true; anexo: AnexoPendente } | { ok: false; error: string } {
  const mime = (file.type || "").toLowerCase();
  if (!MIMES_ACEITOS.some((m) => mime.startsWith(m))) {
    return { ok: false, error: `Tipo de arquivo não suportado (${mime || file.name}).` };
  }
  if (file.size === 0) return { ok: false, error: "O arquivo está vazio." };
  if (file.size > TAMANHO_MAX_BYTES) {
    return { ok: false, error: "Arquivo acima do limite de 16 MB." };
  }
  return {
    ok: true,
    anexo: { file, tipo: tipoDe(mime), previewUrl: URL.createObjectURL(file) },
  };
}

export function descartarAnexo(anexo: AnexoPendente | null): void {
  if (anexo) URL.revokeObjectURL(anexo.previewUrl);
}

/** Sobe o anexo pelo proxy; a legenda é o texto do composer. */
export async function enviarAnexo(
  atendimentoId: number,
  anexo: AnexoPendente,
  legenda: string
): Promise<{ ok: true } | { ok: false; error: string }> {
  const fd = new FormData();
  fd.set("arquivo", anexo.file, anexo.file.name);
  fd.set("legenda", legenda);
  try {
    const r = await fetch(`/api/proxy/midia/${atendimentoId}`, { method: "POST", body: fd });
    if (r.ok) return { ok: true };
    let error = "Não foi possível enviar o arquivo.";
    try {
      const j = (await r.json()) as { error?: unknown };
      if (typeof j.error === "string" && j.error) error = j.error;
    } catch {
      // sem corpo JSON: fica a frase genérica
    }
    return { ok: false, error };
  } catch {
    return { ok: false, error: "Sem conexão com o servidor. Tente de novo." };
  }
}

/** Primeira imagem colada da área de transferência, ou null. */
export function imagemColada(e: React.ClipboardEvent): File | null {
  for (const item of Array.from(e.clipboardData?.items ?? [])) {
    if (item.kind === "file" && item.type.startsWith("image/")) {
      const f = item.getAsFile();
      if (f) return f;
    }
  }
  return null;
}

// --- gravação ---------------------------------------------------------------

const MIMES_GRAVACAO = ["audio/ogg;codecs=opus", "audio/webm;codecs=opus", "audio/mp4"];

function mimeGravacao(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  return MIMES_GRAVACAO.find((m) => MediaRecorder.isTypeSupported(m));
}

function extensaoDe(mime: string): string {
  if (mime.includes("ogg")) return "ogg";
  if (mime.includes("webm")) return "webm";
  if (mime.includes("mp4")) return "m4a";
  return "bin";
}

function formatarSegundos(s: number): string {
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}

/** Acima disso o WhatsApp corta pelo tamanho de qualquer jeito. */
const GRAVACAO_MAX_SEGUNDOS = 10 * 60;

interface BotoesProps {
  disabled?: boolean;
  onAnexo: (anexo: AnexoPendente) => void;
  onErro: (mensagem: string) => void;
}

/**
 * Clipe + microfone. Durante a gravação, os dois viram cronômetro + Cancelar
 * + Parar; ao parar, a nota de voz vira um anexo pendente (prévia com player)
 * e o "Enviar" do composer manda.
 */
export function ComposerMidiaBotoes({ disabled, onAnexo, onErro }: BotoesProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const canceladoRef = useRef(false);
  const [gravando, setGravando] = useState(false);
  const [segundos, setSegundos] = useState(0);
  const [pedindoMic, setPedindoMic] = useState(false);
  const suportaGravacao =
    typeof navigator !== "undefined" &&
    !!navigator.mediaDevices?.getUserMedia &&
    typeof MediaRecorder !== "undefined";

  useEffect(() => {
    if (!gravando) return;
    const t = setInterval(() => setSegundos((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [gravando]);

  // Teto de duração: para sozinho e entrega o que gravou.
  useEffect(() => {
    if (gravando && segundos >= GRAVACAO_MAX_SEGUNDOS) {
      canceladoRef.current = false;
      recorderRef.current?.stop();
    }
  }, [segundos, gravando]);

  // Desmontou no meio da gravação (fechou a conversa): solta o microfone.
  useEffect(() => {
    return () => {
      canceladoRef.current = true;
      recorderRef.current?.state !== "inactive" && recorderRef.current?.stop();
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  function escolherArquivo(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    const r = criarAnexo(f);
    if (r.ok) onAnexo(r.anexo);
    else onErro(r.error);
  }

  async function iniciarGravacao() {
    if (!suportaGravacao) {
      onErro("Este navegador não grava áudio. Use o Chrome, o Firefox ou o Safari atual.");
      return;
    }
    setPedindoMic(true);
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setPedindoMic(false);
      onErro("Permissão do microfone negada. Libere o microfone para este site e tente de novo.");
      return;
    }
    setPedindoMic(false);
    const mime = mimeGravacao();
    let recorder: MediaRecorder;
    try {
      recorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
    } catch {
      stream.getTracks().forEach((t) => t.stop());
      onErro("Não foi possível iniciar a gravação neste navegador.");
      return;
    }
    chunksRef.current = [];
    canceladoRef.current = false;
    recorder.ondataavailable = (ev) => {
      if (ev.data.size > 0) chunksRef.current.push(ev.data);
    };
    recorder.onstop = () => {
      stream.getTracks().forEach((t) => t.stop());
      streamRef.current = null;
      recorderRef.current = null;
      setGravando(false);
      if (canceladoRef.current) return;
      const tipo = recorder.mimeType || mime || "audio/webm";
      const blob = new Blob(chunksRef.current, { type: tipo });
      if (blob.size === 0) {
        onErro("A gravação saiu vazia. Tente de novo.");
        return;
      }
      const file = new File([blob], `nota-de-voz.${extensaoDe(tipo)}`, { type: tipo });
      const r = criarAnexo(file);
      if (r.ok) onAnexo(r.anexo);
      else onErro(r.error);
    };
    recorderRef.current = recorder;
    streamRef.current = stream;
    setSegundos(0);
    setGravando(true);
    recorder.start(250);
  }

  function pararGravacao() {
    canceladoRef.current = false;
    recorderRef.current?.stop();
  }

  function cancelarGravacao() {
    canceladoRef.current = true;
    recorderRef.current?.stop();
  }

  if (gravando) {
    return (
      <div
        className="flex items-center gap-1.5 rounded-md border border-destructive/40 bg-destructive/5 px-2 py-1"
        role="status"
        aria-live="polite"
      >
        <span className="size-2 animate-pulse rounded-full bg-destructive" aria-hidden />
        <span className="font-mono text-xs tabular-nums">{formatarSegundos(segundos)}</span>
        <Button
          type="button"
          size="icon-xs"
          variant="ghost"
          onClick={cancelarGravacao}
          aria-label="Cancelar gravação"
          title="Cancelar gravação"
        >
          <X className="size-3.5" />
        </Button>
        <Button
          type="button"
          size="icon-xs"
          variant="default"
          onClick={pararGravacao}
          aria-label="Parar gravação"
          title="Parar e revisar"
        >
          <Square className="size-3" />
        </Button>
      </div>
    );
  }

  return (
    <div className="flex items-center gap-0.5">
      <Input
        ref={inputRef}
        type="file"
        accept={ACCEPT_ANEXO}
        onChange={escolherArquivo}
        className="sr-only"
        tabIndex={-1}
        aria-hidden
      />
      <Button
        type="button"
        size="icon"
        variant="ghost"
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
        aria-label="Anexar arquivo"
        title="Anexar imagem, vídeo ou documento (ou cole/arraste no composer)"
      >
        <Paperclip className="size-4" />
      </Button>
      <Button
        type="button"
        size="icon"
        variant="ghost"
        disabled={disabled || pedindoMic}
        onClick={() => void iniciarGravacao()}
        aria-label="Gravar nota de voz"
        title={
          suportaGravacao
            ? "Gravar nota de voz (toque para começar, toque para parar)"
            : "Este navegador não grava áudio"
        }
      >
        {pedindoMic ? <Loader2 className="size-4 animate-spin" /> : <Mic className="size-4" />}
      </Button>
    </div>
  );
}

interface PreviewProps {
  anexo: AnexoPendente;
  enviando?: boolean;
  onRemover: () => void;
}

/** Prévia do anexo pendente, acima do composer. */
export function AnexoPreview({ anexo, enviando, onRemover }: PreviewProps) {
  return (
    <div className="mb-2 flex items-center gap-3 rounded-md border bg-muted/40 p-2 text-xs">
      {anexo.tipo === "imagem" && (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={anexo.previewUrl}
          alt=""
          className="size-14 shrink-0 rounded object-cover"
        />
      )}
      {anexo.tipo === "video" && (
        <video src={anexo.previewUrl} muted className="size-14 shrink-0 rounded object-cover" />
      )}
      {anexo.tipo === "audio" && (
        <audio src={anexo.previewUrl} controls className="h-9 min-w-0 flex-1" />
      )}
      {anexo.tipo === "documento" && (
        <FileText className="size-6 shrink-0 text-muted-foreground" aria-hidden />
      )}
      <div className={cn("min-w-0", anexo.tipo === "audio" ? "shrink-0" : "flex-1")}>
        <p className="truncate font-medium">
          {anexo.tipo === "audio" ? "Nota de voz" : anexo.file.name}
        </p>
        <p className="text-muted-foreground">
          {formatarTamanho(anexo.file.size)}
          {anexo.tipo !== "audio" && " · o texto abaixo vai como legenda"}
        </p>
      </div>
      <Button
        type="button"
        size="icon-xs"
        variant="ghost"
        onClick={onRemover}
        disabled={enviando}
        aria-label="Remover anexo"
        title="Remover"
      >
        <X className="size-3.5" />
      </Button>
    </div>
  );
}
