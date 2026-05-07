import Link from "next/link";
import { ArrowLeft, Brain } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { requireSession } from "@/lib/session";

import { createModeloAction } from "./actions";

export const dynamic = "force-dynamic";

const inputCls =
  "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus-visible:ring-1 focus-visible:ring-ring";
const labelCls = "text-sm font-medium";
const helpCls = "text-xs text-muted-foreground";

interface PageProps {
  searchParams: Promise<{ error?: string }>;
}

export default async function NewModeloPage({ searchParams }: PageProps) {
  await requireSession();
  const params = await searchParams;
  const errorMsg = params.error ?? null;

  return (
    <div className="space-y-6">
      <Link
        href="/catalog/models"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" />
        Voltar
      </Link>
      <div className="flex items-center gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
          <Brain className="h-5 w-5 text-primary" />
        </div>
        <div>
          <h1 className="text-2xl font-semibold">Novo modelo custom</h1>
          <p className="mt-0.5 text-sm text-muted-foreground">
            Custom da empresa — visível só pra agentes desta empresa.
          </p>
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Identificação</CardTitle>
        </CardHeader>
        <CardContent>
          {errorMsg && (
            <p className="mb-3 rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
              {errorMsg}
            </p>
          )}
          <form action={createModeloAction} className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1">
                <label className={labelCls}>Provedor *</label>
                <input
                  name="provedor"
                  required
                  maxLength={60}
                  placeholder="Ex: openai, anthropic, google, openrouter"
                  className={inputCls}
                />
              </div>
              <div className="space-y-1">
                <label className={labelCls}>Nome do modelo *</label>
                <input
                  name="nome"
                  required
                  maxLength={120}
                  placeholder="Ex: gpt-4o-mini"
                  className={inputCls}
                />
              </div>
              <div className="space-y-1">
                <label className={labelCls}>Tipo</label>
                <select name="tipo" defaultValue="chat" className={inputCls}>
                  <option value="chat">Chat (text-to-text)</option>
                  <option value="embedding">Embedding</option>
                  <option value="midia">Mídia (multimodal)</option>
                  <option value="audio">Áudio (STT/TTS)</option>
                  <option value="imagem">Imagem (geração)</option>
                </select>
              </div>
              <div className="space-y-1">
                <label className={labelCls}>Janela de contexto (tokens)</label>
                <input
                  name="janela_contexto"
                  type="number"
                  placeholder="ex: 128000"
                  className={inputCls}
                />
              </div>
              <div className="space-y-1">
                <label className={labelCls}>Custo input ($/M tokens)</label>
                <input
                  name="custo_input_mtok"
                  type="number"
                  step="0.0001"
                  placeholder="ex: 0.15"
                  className={inputCls}
                />
              </div>
              <div className="space-y-1">
                <label className={labelCls}>Custo output ($/M tokens)</label>
                <input
                  name="custo_output_mtok"
                  type="number"
                  step="0.0001"
                  placeholder="ex: 0.60"
                  className={inputCls}
                />
              </div>
              <div className="space-y-1 sm:col-span-2">
                <label className={labelCls}>Descrição</label>
                <input
                  name="descricao"
                  maxLength={500}
                  placeholder="Ex: GPT-4o mini — barato, rápido, multimodal"
                  className={inputCls}
                />
              </div>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Link href="/catalog/models">
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
