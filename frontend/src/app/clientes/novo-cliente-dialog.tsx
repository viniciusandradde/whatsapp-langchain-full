"use client";

import { useState, useTransition } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { UserPlus } from "lucide-react";
import { toast } from "sonner";

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
import { Label } from "@/components/ui/label";
import type { Cliente } from "@/lib/api";
import { ESTAGIOS_FUNIL, TEMPERATURAS } from "@/lib/lead";

import { criarClienteAction } from "./actions";

const SELECT =
  "h-9 w-full rounded-md border border-input bg-background px-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring";

/** Botão + diálogo "Novo cliente" (cadastro manual, mig 201). */
export function NovoClienteDialog() {
  const router = useRouter();
  const [aberto, setAberto] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [existenteId, setExistenteId] = useState<number | null>(null);
  const [pendente, startTransition] = useTransition();

  function enviar(form: FormData) {
    const v = (k: string) => {
      const s = String(form.get(k) ?? "").trim();
      return s === "" ? null : s;
    };
    setErro(null);
    setExistenteId(null);
    startTransition(async () => {
      const r = await criarClienteAction({
        telefone: v("telefone") ?? "",
        nome: v("nome"),
        email: v("email"),
        source: v("origem"),
        lifecycle_stage: v("estagio") as Cliente["lifecycle_stage"],
        temperatura: v("temperatura") as Cliente["temperatura"],
      });
      if (!r.ok) {
        setErro(r.error);
        setExistenteId(r.existenteId ?? null);
        return;
      }
      setAberto(false);
      toast.success("Cliente cadastrado");
      router.push(`/clientes/${r.id}`);
    });
  }

  return (
    <>
      <Button type="button" onClick={() => setAberto(true)}>
        <UserPlus className="size-4" />
        Novo cliente
      </Button>
      <Dialog
        open={aberto}
        onOpenChange={(v) => {
          setAberto(v);
          if (!v) {
            setErro(null);
            setExistenteId(null);
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Novo cliente</DialogTitle>
            <DialogDescription>
              Só o telefone é obrigatório. O resto dá para completar depois na ficha.
            </DialogDescription>
          </DialogHeader>
          <form action={enviar} className="space-y-3" id="form-novo-cliente">
            <div className="space-y-1.5">
              <Label htmlFor="nc-telefone">Telefone (WhatsApp)</Label>
              <Input
                id="nc-telefone"
                name="telefone"
                required
                inputMode="tel"
                autoComplete="off"
                placeholder="(67) 99999-0000"
              />
              <p className="text-xs text-muted-foreground">
                Com DDD. Número de outro país: comece com + e o código do país.
              </p>
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="nc-nome">Nome</Label>
              <Input id="nc-nome" name="nome" maxLength={200} autoComplete="off" />
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="nc-email">E-mail</Label>
                <Input id="nc-email" name="email" type="email" maxLength={200} />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="nc-origem">Origem</Label>
                <Input
                  id="nc-origem"
                  name="origem"
                  maxLength={120}
                  placeholder="Instagram, indicação, feira…"
                />
              </div>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="nc-estagio">Estágio do funil</Label>
                <select id="nc-estagio" name="estagio" className={SELECT} defaultValue="">
                  <option value="">Sem estágio</option>
                  {ESTAGIOS_FUNIL.map((e) => (
                    <option key={e.valor} value={e.valor}>
                      {e.rotulo}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="nc-temperatura">Temperatura</Label>
                <select id="nc-temperatura" name="temperatura" className={SELECT} defaultValue="">
                  <option value="">Sem temperatura</option>
                  {TEMPERATURAS.map((t) => (
                    <option key={t.valor} value={t.valor}>
                      {t.rotulo}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            {erro && (
              <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">
                {erro}{" "}
                {existenteId && (
                  <Link href={`/clientes/${existenteId}`} className="font-medium underline">
                    Abrir cadastro
                  </Link>
                )}
              </p>
            )}
          </form>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setAberto(false)}>
              Cancelar
            </Button>
            <Button type="submit" form="form-novo-cliente" disabled={pendente}>
              {pendente ? "Salvando…" : "Cadastrar"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
