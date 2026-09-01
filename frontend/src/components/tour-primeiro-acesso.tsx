"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Headphones, Inbox } from "lucide-react";

import { usePermissionsContext } from "@/components/permissions-context";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

/**
 * Guia de primeiro acesso do atendente (mig 171).
 *
 * Quem recebe a senha pelo convite entra e não sabe onde atender. Como o
 * login já cai direto na fila (`/atendimento`, decisão em `app/page.tsx`),
 * o guia não ensina mais o caminho até ela — ensina a usá-la: abrir uma
 * conversa, clicar em Atender e responder.
 *
 * Não confundir com `/onboarding`: aquele é o wizard da EMPRESA quando ela
 * ainda não está configurada (passos de admin). Este é do usuário, aparece
 * uma vez e marca em `auth."user".tour_operador_at`.
 *
 * Só aparece para quem tem `atendimento.read` — sem essa permissão a pessoa
 * nem cai na fila, e o roteiro seria mentira.
 */
export function TourPrimeiroAcesso() {
  const { hasPerm } = usePermissionsContext();
  const router = useRouter();
  const [passo, setPasso] = useState<0 | 1 | 2>(0);
  const [aberto, setAberto] = useState(false);

  useEffect(() => {
    if (!hasPerm("atendimento.read")) return;
    let vivo = true;
    fetch("/api/proxy/tour", { cache: "no-store" })
      .then((r) => r.json())
      .then((d) => {
        if (!vivo || d.visto) return;
        setAberto(true);
      })
      .catch(() => {});
    return () => {
      vivo = false;
    };
  }, [hasPerm]);

  function encerrar(irParaFila: boolean) {
    setAberto(false);
    // Best-effort: se a marcação falhar, o guia reaparece no próximo acesso —
    // preferível a engolir o erro e a pessoa nunca mais ver o caminho.
    void fetch("/api/proxy/tour", { method: "POST" }).catch(() => {});
    if (irParaFila) router.push("/atendimento");
  }

  function avancar() {
    if (passo === 0) {
      setPasso(1);
      return;
    }
    if (passo === 1) {
      setPasso(2);
      return;
    }
    encerrar(true);
  }

  if (!aberto) return null;

  const conteudo = [
    {
      titulo: "Bem-vindo ao Chat Nexus",
      descricao:
        "Esta é a fila de atendimento: as conversas dos clientes esperam aqui por você. Em dois passos você atende a primeira.",
      corpo: null,
    },
    {
      titulo: "Passo 1 — abra uma conversa",
      descricao:
        "Na lista à esquerda, cada linha é um cliente esperando. Clique numa conversa pra ver as mensagens.",
      corpo: (
        <div className="flex items-center gap-2 rounded-md border bg-accent/40 px-3 py-2 text-sm">
          <Inbox className="size-4 shrink-0" />
          <span className="font-medium">Fila de atendimento</span>
        </div>
      ),
    },
    {
      titulo: "Passo 2 — atenda e responda",
      descricao:
        "Com a conversa aberta, clique em Atender pra assumir o cliente e responda pelo campo de mensagem. Enter envia; Shift+Enter quebra linha.",
      corpo: (
        <div className="flex items-center gap-2 rounded-md border bg-accent/40 px-3 py-2 text-sm">
          <Headphones className="size-4 shrink-0" />
          <span className="font-medium">Atender</span>
        </div>
      ),
    },
  ][passo];

  return (
    <Dialog open onOpenChange={(v) => !v && encerrar(false)}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{conteudo.titulo}</DialogTitle>
          <DialogDescription>{conteudo.descricao}</DialogDescription>
        </DialogHeader>
        {conteudo.corpo}
        <DialogFooter>
          <Button variant="ghost" onClick={() => encerrar(false)}>
            Pular guia
          </Button>
          <Button onClick={avancar}>
            {passo === 2 ? "Começar a atender" : "Continuar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
