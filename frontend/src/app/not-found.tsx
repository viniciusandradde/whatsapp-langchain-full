import Link from "next/link";
import { FileQuestion, Home } from "lucide-react";

export default function NotFound() {
  return (
    <div className="flex min-h-[60vh] flex-col items-center justify-center gap-6 p-8 text-center">
      <div className="flex size-24 items-center justify-center rounded-full bg-brand-primary/10">
        <FileQuestion className="size-12 text-brand-primary" />
      </div>
      <div className="space-y-2">
        <h1 className="text-4xl font-bold tracking-tight">404</h1>
        <p className="text-lg font-semibold">Página não encontrada</p>
        <p className="max-w-md text-sm text-muted-foreground">
          O endereço que você tentou abrir não existe ou foi movido. Verifique
          a URL ou volte pra home pra navegar pelo menu.
        </p>
      </div>
      <div className="flex flex-wrap gap-2">
        <Link
          href="/dashboard/atendimento"
          className="inline-flex h-9 items-center justify-center gap-1.5 rounded-md bg-brand-primary px-4 text-sm font-medium text-white hover:bg-brand-primary/90"
        >
          <Home className="size-4" />
          Voltar pra Home
        </Link>
        <Link
          href="/atendimento"
          className="inline-flex h-9 items-center justify-center rounded-md border border-white/15 bg-transparent px-4 text-sm font-medium hover:bg-white/5"
        >
          Ver Atendimentos
        </Link>
      </div>
    </div>
  );
}
