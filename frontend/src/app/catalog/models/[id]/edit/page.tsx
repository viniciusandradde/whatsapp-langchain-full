import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, Brain, Trash2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { getModeloLLM } from "@/lib/api";
import { requireSession } from "@/lib/session";

import { deleteModeloAction, updateModeloAction } from "./actions";

export const dynamic = "force-dynamic";

const inputCls =
  "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus-visible:ring-1 focus-visible:ring-ring";
const labelCls = "text-sm font-medium";

interface PageProps {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ error?: string }>;
}

export default async function EditModeloPage({ params, searchParams }: PageProps) {
  await requireSession();
  const { id } = await params;
  const idNum = Number(id);
  if (!Number.isFinite(idNum)) notFound();

  let modeloMaybe: Awaited<ReturnType<typeof getModeloLLM>> | null = null;
  try {
    modeloMaybe = await getModeloLLM(idNum);
  } catch {
    notFound();
  }
  if (!modeloMaybe) notFound();
  const modelo = modeloMaybe!;
  if (modelo.empresa_id === null) {
    // Globais não são editáveis. Mostra mensagem amigável + voltar.
    return (
      <div className="space-y-6">
        <Link
          href="/catalog/models"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-4" />
          Voltar
        </Link>
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            <Brain className="mx-auto mb-3 size-8 opacity-50" />
            <p>Modelos globais não podem ser editados.</p>
            <p className="mt-1 text-xs">
              <code>{modelo.provedor}/{modelo.nome}</code> é seedado pelo
              sistema. Se precisar de override de custo, crie um modelo
              custom com o mesmo nome.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  const errorMsg = (await searchParams).error ?? null;

  return (
    <div className="space-y-6">
      <Link
        href="/catalog/models"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" />
        Voltar
      </Link>

      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
            <Brain className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold">{modelo.nome}</h1>
            <p className="mt-0.5 text-sm text-muted-foreground">
              <code>{modelo.provedor}/{modelo.nome}</code> · custom desta empresa
            </p>
          </div>
        </div>
        <Badge variant={modelo.ativo ? "outline" : "secondary"}>
          {modelo.ativo ? "ativo" : "inativo"}
        </Badge>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Editar modelo</CardTitle>
        </CardHeader>
        <CardContent>
          {errorMsg && (
            <p className="mb-3 rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
              {errorMsg}
            </p>
          )}
          <form
            action={async (fd: FormData) => {
              "use server";
              await updateModeloAction(idNum, fd);
            }}
            className="space-y-4"
          >
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1">
                <label className={labelCls}>Nome (não pode trocar provedor)</label>
                <input
                  name="nome"
                  defaultValue={modelo.nome}
                  required
                  maxLength={120}
                  className={inputCls}
                />
              </div>
              <div className="space-y-1">
                <label className={labelCls}>Janela de contexto (tokens)</label>
                <input
                  name="janela_contexto"
                  type="number"
                  defaultValue={modelo.janela_contexto ?? ""}
                  className={inputCls}
                />
              </div>
              <div className="space-y-1">
                <label className={labelCls}>Custo input ($/M tokens)</label>
                <input
                  name="custo_input_mtok"
                  type="number"
                  step="0.0001"
                  defaultValue={modelo.custo_input_mtok ?? ""}
                  className={inputCls}
                />
              </div>
              <div className="space-y-1">
                <label className={labelCls}>Custo output ($/M tokens)</label>
                <input
                  name="custo_output_mtok"
                  type="number"
                  step="0.0001"
                  defaultValue={modelo.custo_output_mtok ?? ""}
                  className={inputCls}
                />
              </div>
              <div className="space-y-1 sm:col-span-2">
                <label className={labelCls}>Descrição</label>
                <input
                  name="descricao"
                  defaultValue={modelo.descricao ?? ""}
                  maxLength={500}
                  className={inputCls}
                />
              </div>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                name="ativo"
                defaultChecked={modelo.ativo}
                className="size-4"
              />
              Modelo ativo (disponível pra agentes)
            </label>
            <div className="flex justify-between gap-2 pt-2">
              <form
                action={async () => {
                  "use server";
                  await deleteModeloAction(idNum);
                }}
              >
                <Button type="submit" variant="destructive">
                  <Trash2 className="size-4" />
                  Deletar
                </Button>
              </form>
              <Button type="submit">Salvar</Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
