"use client";

import { useState, useTransition } from "react";
import { BotOff } from "lucide-react";

import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

import { salvarRespostaCelularAction } from "../actions";

/** Espelho de `shared/resposta_celular.py::OPCOES_RETORNO_MINUTOS`. */
const OPCOES_MINUTOS = [30, 60, 120, 240, 1440] as const;
const NUNCA = "nunca";

function rotulo(minutos: number): string {
  if (minutos < 60) return `Depois de ${minutos} minutos`;
  const horas = minutos / 60;
  if (Number.isInteger(horas)) {
    return horas === 1 ? "Depois de 1 hora" : `Depois de ${horas} horas`;
  }
  return `Depois de ${minutos} minutos`;
}

function rotuloDoValor(v: string | null): string {
  if (!v || v === NUNCA) return "Só quando alguém tocar em Devolver à IA";
  return rotulo(Number(v));
}

interface Props {
  conexaoId: number;
  initialMinutos: number | null;
}

/**
 * Resposta pelo celular pausa a IA (ADR-008, mig 205).
 *
 * Quando o dono responde pelo celular (ou WhatsApp Web), a conversa fica com
 * ele e a IA se cala. Aqui ele escolhe se a IA volta sozinha depois de um
 * tempo sem resposta dele (`conexao.celular_retorno_ia_minutos`) ou só pelo
 * "Devolver à IA" da conversa (padrão).
 */
export function RespostaCelularPanel({ conexaoId, initialMinutos }: Props) {
  const [valor, setValor] = useState<string>(
    initialMinutos == null ? NUNCA : String(initialMinutos)
  );
  const [msg, setMsg] = useState<string | null>(null);
  const [saving, startSaving] = useTransition();

  // Valor gravado fora das opções (ajustado por outro caminho) continua
  // aparecendo e selecionável até alguém trocar.
  const opcoes: number[] = [...OPCOES_MINUTOS];
  if (initialMinutos != null && !opcoes.includes(initialMinutos)) {
    opcoes.push(initialMinutos);
    opcoes.sort((a, b) => a - b);
  }

  function handleChange(novo: string | null) {
    if (!novo || novo === valor) return;
    const anterior = valor;
    setValor(novo);
    setMsg(null);
    startSaving(async () => {
      const r = await salvarRespostaCelularAction(
        conexaoId,
        novo === NUNCA ? null : Number(novo)
      );
      if (!r.ok) {
        setValor(anterior);
        setMsg(`Erro: ${r.error}`);
        return;
      }
      setMsg("✓ Salvo.");
    });
  }

  return (
    <div className="rounded-lg border border-border/40 p-4 space-y-4">
      <div className="flex items-center gap-2">
        <BotOff className="h-5 w-5 shrink-0 text-primary" />
        <div>
          <div className="font-medium">Resposta pelo celular</div>
          <p className="text-xs text-muted-foreground">
            Quando você responde um cliente pelo celular ou pelo WhatsApp Web,
            a sua mensagem aparece na conversa como &quot;WhatsApp
            (celular)&quot; e a IA para de responder naquela conversa, para não
            falar por cima de você. Mensagens em grupos não contam.
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="space-y-1">
          <Label htmlFor="celular-retorno-ia">A IA volta a responder</Label>
          <Select value={valor} onValueChange={handleChange}>
            <SelectTrigger
              id="celular-retorno-ia"
              className="w-full"
              disabled={saving}
            >
              <SelectValue>{rotuloDoValor}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NUNCA}>{rotuloDoValor(NUNCA)}</SelectItem>
              {opcoes.map((m) => (
                <SelectItem key={m} value={String(m)}>
                  {rotulo(m)} sem resposta sua
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-end">
          <p className="text-xs text-muted-foreground">
            {valor === NUNCA
              ? "A conversa fica com você até alguém tocar em Devolver à IA na própria conversa."
              : "Se o cliente escrever e você não responder pelo celular nesse tempo, a IA retoma e responde à última mensagem dele. Mensagem com mais de um dia não é respondida."}
          </p>
        </div>
      </div>

      {msg && (
        <p
          className={
            msg.startsWith("✓")
              ? "text-xs text-muted-foreground"
              : "text-xs text-destructive"
          }
        >
          {msg}
        </p>
      )}
    </div>
  );
}
