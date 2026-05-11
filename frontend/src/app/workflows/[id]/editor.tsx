"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, useTransition } from "react";
import {
  ArrowLeft,
  Code2,
  Loader2,
  Power,
  Save,
  Workflow as WorkflowIcon,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { WorkflowDetail } from "@/lib/api";

import { toggleWorkflowActiveAction, updateWorkflowAction } from "./actions";

const inputCls =
  "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus-visible:ring-1 focus-visible:ring-ring";
const textareaCls =
  "flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm focus:outline-none focus-visible:ring-1 focus-visible:ring-ring font-mono";
const labelCls = "text-sm font-medium";
const helpCls = "text-xs text-muted-foreground";

interface Props {
  workflow: WorkflowDetail;
}

export function WorkflowEditor({ workflow }: Props) {
  const router = useRouter();
  const [nome, setNome] = useState(workflow.nome);
  const [descricao, setDescricao] = useState(workflow.descricao ?? "");
  const [definicaoText, setDefinicaoText] = useState(
    JSON.stringify(workflow.definicao, null, 2)
  );
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<
    { kind: "ok" | "err"; msg: string } | null
  >(null);
  const [isPending, startTransition] = useTransition();
  const [isToggling, startToggle] = useTransition();
  const [ativo, setAtivo] = useState(workflow.ativo);

  const definicaoChanged =
    definicaoText !== JSON.stringify(workflow.definicao, null, 2);
  const nomeChanged = nome !== workflow.nome;
  const descChanged = descricao !== (workflow.descricao ?? "");
  const dirty = definicaoChanged || nomeChanged || descChanged;

  const nodeCount = (() => {
    try {
      const parsed = JSON.parse(definicaoText);
      const nodes = parsed?.nodes;
      return nodes && typeof nodes === "object" ? Object.keys(nodes).length : 0;
    } catch {
      return null;
    }
  })();

  async function handleSave() {
    setFeedback(null);
    setJsonError(null);

    const body: Parameters<typeof updateWorkflowAction>[1] = {};
    if (nomeChanged) body.nome = nome;
    if (descChanged) body.descricao = descricao;
    if (definicaoChanged) {
      let parsed: unknown;
      try {
        parsed = JSON.parse(definicaoText);
      } catch (e) {
        setJsonError(e instanceof Error ? e.message : "JSON inválido.");
        return;
      }
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        setJsonError("Definição precisa ser um objeto JSON.");
        return;
      }
      const obj = parsed as Record<string, unknown>;
      if (!obj.entry || typeof obj.entry !== "string") {
        setJsonError("Falta `entry` (string com id do node inicial).");
        return;
      }
      if (!obj.nodes || typeof obj.nodes !== "object") {
        setJsonError("Falta `nodes` (objeto com a definição dos nodes).");
        return;
      }
      const nodes = obj.nodes as Record<string, unknown>;
      if (!(obj.entry in nodes)) {
        setJsonError(`Entry '${obj.entry}' não está em nodes.`);
        return;
      }
      body.definicao = obj;
    }

    startTransition(async () => {
      const r = await updateWorkflowAction(workflow.id, body);
      if (r.ok) {
        setFeedback({
          kind: "ok",
          msg: r.versao
            ? `Salvo! Nova versão: ${r.versao}.`
            : "Alterações salvas.",
        });
        router.refresh();
      } else {
        setFeedback({ kind: "err", msg: r.error ?? "Erro ao salvar." });
      }
    });
  }

  function handleToggle() {
    setFeedback(null);
    startToggle(async () => {
      const r = await toggleWorkflowActiveAction(workflow.id);
      if (r.ok) {
        setAtivo(r.ativo ?? false);
        setFeedback({
          kind: "ok",
          msg: r.ativo
            ? "Workflow ativado — worker começa a usar."
            : "Workflow desativado.",
        });
        router.refresh();
      } else {
        setFeedback({ kind: "err", msg: r.error ?? "Erro." });
      }
    });
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Link href="/workflows">
            <Button variant="ghost" size="sm">
              <ArrowLeft className="size-4" />
              Workflows
            </Button>
          </Link>
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
            <WorkflowIcon className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-xl font-semibold">{workflow.nome}</h1>
            <code className="text-xs text-muted-foreground">
              {workflow.slug} · versão {workflow.versao}
              {workflow.versao_ativa_id &&
                ` · publicada #${workflow.versao_ativa_id}`}
            </code>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant={ativo ? "default" : "secondary"}>
            {ativo ? "Ativo" : "Inativo"}
          </Badge>
          <Button
            variant="outline"
            size="sm"
            onClick={handleToggle}
            disabled={isToggling}
          >
            {isToggling ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Power className="size-4" />
            )}
            {ativo ? "Desativar" : "Ativar"}
          </Button>
        </div>
      </div>

      {feedback && (
        <p
          className={
            feedback.kind === "ok"
              ? "rounded-md border border-emerald-500/40 bg-emerald-500/10 p-3 text-sm text-emerald-700 dark:text-emerald-300"
              : "rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive"
          }
        >
          {feedback.msg}
        </p>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Metadados</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <label className={labelCls}>Nome</label>
            <input
              value={nome}
              onChange={(e) => setNome(e.target.value)}
              maxLength={120}
              className={inputCls}
            />
          </div>
          <div className="space-y-2">
            <label className={labelCls}>Descrição</label>
            <textarea
              value={descricao}
              onChange={(e) => setDescricao(e.target.value)}
              maxLength={500}
              rows={2}
              className={textareaCls.replace(" font-mono", "")}
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <Code2 className="size-4" />
              Definição (JSON)
            </CardTitle>
            <span className={helpCls}>
              {nodeCount !== null ? `${nodeCount} nodes` : "JSON inválido"}
            </span>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          <textarea
            value={definicaoText}
            onChange={(e) => {
              setDefinicaoText(e.target.value);
              setJsonError(null);
            }}
            spellCheck={false}
            rows={28}
            className={textareaCls + " text-xs leading-relaxed"}
          />
          <p className={helpCls}>
            Schema: <code>{`{ "entry": "<node_id>", "nodes": { ... } }`}</code>.
            Salvar cria uma nova versão imutável em{" "}
            <code>workflow_chatbot_version</code> — versões antigas continuam
            referenciáveis pelos atendimentos em andamento.
          </p>
          {jsonError && (
            <p className="rounded-md border border-destructive/50 bg-destructive/10 p-2 text-xs text-destructive">
              {jsonError}
            </p>
          )}
        </CardContent>
      </Card>

      <div className="flex items-center justify-end gap-2">
        <Button
          onClick={handleSave}
          disabled={!dirty || isPending}
          className="min-w-32"
        >
          {isPending ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <Save className="size-4" />
          )}
          Salvar
        </Button>
      </div>
    </div>
  );
}
