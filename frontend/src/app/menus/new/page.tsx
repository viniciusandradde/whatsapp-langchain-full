import Link from "next/link";
import { ArrowLeft, ListTree } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getConexoes } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { createMenuAction } from "./actions";

export const dynamic = "force-dynamic";

interface PageProps {
  searchParams: Promise<{ error?: string }>;
}

const inputCls =
  "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus-visible:ring-1 focus-visible:ring-ring";
const textareaCls =
  "flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm focus:outline-none focus-visible:ring-1 focus-visible:ring-ring";
// `<select>` precisa de bg sólido + cor explícita nas options (dropdown
// nativo do OS não herda bg-transparent → some no dark mode).
const selectCls =
  "flex h-9 w-full rounded-md border border-input bg-background text-foreground px-3 py-1 text-sm shadow-sm focus:outline-none focus-visible:ring-1 focus-visible:ring-ring [&>option]:bg-background [&>option]:text-foreground";
const labelCls = "text-sm font-medium";
const helpCls = "text-xs text-muted-foreground";

export default async function NewMenuPage({ searchParams }: PageProps) {
  await requireSession();
  const params = await searchParams;
  const errorMsg = params.error ?? null;

  let conexoes: Awaited<ReturnType<typeof getConexoes>>["conexoes"] = [];
  try {
    const r = await getConexoes();
    conexoes = r.conexoes;
  } catch {
    // Lista de conexões é opcional — se falhar, mostra só "todas".
  }

  return (
    <div className="space-y-6">
      <Link
        href="/menus"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" />
        Voltar
      </Link>

      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
          <ListTree className="h-5 w-5 text-primary" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold">Novo menu chatbot</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Cria menu árvore. Items + ações configurados depois no editor.
          </p>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Dados básicos</CardTitle>
        </CardHeader>
        <CardContent>
          {errorMsg && (
            <p className="mb-3 rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
              {errorMsg}
            </p>
          )}
          <form action={createMenuAction} className="space-y-4">
            <div className="space-y-2">
              <label htmlFor="nome" className={labelCls}>
                Nome interno *
              </label>
              <input
                id="nome"
                name="nome"
                required
                maxLength={120}
                placeholder="Ex: Triagem inicial"
                className={inputCls}
              />
              <p className={helpCls}>
                Visível só pra equipe (não pro cliente).
              </p>
            </div>

            <div className="space-y-2">
              <label htmlFor="mensagem_boas_vindas" className={labelCls}>
                Mensagem de boas-vindas *
              </label>
              <textarea
                id="mensagem_boas_vindas"
                name="mensagem_boas_vindas"
                required
                maxLength={4000}
                rows={4}
                placeholder="Ex: Olá! Como posso te ajudar?"
                className={textareaCls}
              />
              <p className={helpCls}>
                Texto que aparece antes da lista numerada de opções.
              </p>
            </div>

            <div className="space-y-2">
              <label htmlFor="conexao_id" className={labelCls}>
                Conexão
              </label>
              <select
                id="conexao_id"
                name="conexao_id"
                defaultValue="all"
                className={selectCls}
              >
                <option value="all">Todas as conexões</option>
                {conexoes.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.display_name || c.from_number} ({c.provider})
                  </option>
                ))}
              </select>
              <p className={helpCls}>
                Menu só roda quando o cliente fala com essa conexão. Sem
                seleção, vale pra todas.
              </p>
            </div>

            <div className="space-y-2">
              <label htmlFor="trigger_keywords" className={labelCls}>
                Palavras-chave de retorno
              </label>
              <input
                id="trigger_keywords"
                name="trigger_keywords"
                defaultValue="menu, opcoes, inicio"
                placeholder="menu, opcoes, inicio"
                className={inputCls}
              />
              <p className={helpCls}>
                Separadas por vírgula. Cliente que digitar uma dessas a
                qualquer hora volta pra raiz do menu.
              </p>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <Link href="/menus">
                <Button type="button" variant="outline">
                  Cancelar
                </Button>
              </Link>
              <Button type="submit">Criar e editar</Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
