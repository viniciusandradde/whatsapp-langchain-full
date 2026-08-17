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
import { useSidebar } from "@/components/ui/sidebar";

/**
 * Guia de primeiro acesso do atendente (mig 171).
 *
 * Quem recebe a senha pelo convite entra e não sabe onde atender. Este guia
 * mostra o caminho **Operação → Fila de atendimento** e termina abrindo a
 * tela.
 *
 * Não confundir com `/onboarding`: aquele é o wizard da EMPRESA quando ela
 * ainda não está configurada (passos de admin). Este é do usuário, aparece
 * uma vez e marca em `auth."user".tour_operador_at`.
 *
 * Só aparece para quem tem `atendimento.read` — sem essa permissão o grupo
 * "Operação" nem existe no menu, e apontar para ele seria mentira.
 */
export function TourPrimeiroAcesso() {
  const { hasPerm } = usePermissionsContext();
  const router = useRouter();
  const { setOpen } = useSidebar();
  const [passo, setPasso] = useState<0 | 1 | 2>(0);
  const [aberto, setAberto] = useState(false);

  useEffect(() => {
    if (!hasPerm("atendimento.read")) return;
    let vivo = true;
    fetch("/api/proxy/tour", { cache: "no-store" })
      .then((r) => r.json())
      .then((d) => {
        if (!vivo || d.visto) return;
        // Abrir o menu ANTES de começar: mexer no SidebarProvider no meio
        // dos passos re-renderiza a subárvore e derruba o diálogo (visto no
        // teste com Playwright).
        setOpen(true);
        setAberto(true);
      })
      .catch(() => {});
    return () => {
      vivo = false;
    };
  }, [hasPerm, setOpen]);

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
        "Em menos de um minuto você vai saber onde ficam as conversas dos clientes. É só seguir.",
      corpo: null,
    },
    {
      titulo: "Passo 1 — abra o menu Operação",
      descricao:
        "No menu à esquerda, o grupo Operação reúne tudo o que chega dos clientes.",
      corpo: (
        <div className="flex items-center gap-2 rounded-md border bg-accent/40 px-3 py-2 text-sm">
          <Headphones className="size-4 shrink-0" />
          <span className="font-medium">Operação</span>
        </div>
      ),
    },
    {
      titulo: "Passo 2 — entre na Fila de atendimento",
      descricao:
        "É onde as conversas esperam por você: abra uma, clique em Atender e responda pelo campo de mensagem.",
      corpo: (
        <div className="flex items-center gap-2 rounded-md border bg-accent/40 px-3 py-2 text-sm">
          <Inbox className="size-4 shrink-0" />
          <span className="font-medium">Fila de atendimento</span>
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
            {passo === 2 ? "Abrir a fila de atendimento" : "Continuar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
