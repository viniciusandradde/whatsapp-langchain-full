"use client";

import { useEffect, useState, useTransition } from "react";
import { useRouter } from "next/navigation";
import { MessageSquarePlus } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { usePermission } from "@/hooks/use-permission";
import type { Conexao, WabaTemplate } from "@/lib/api";

import { iniciarConversaAction, loadTemplatesAprovadosAction } from "./actions";

function _bodyText(t: WabaTemplate): string {
  const body = t.componentes_json.find(
    (c) => (c.type || "").toUpperCase() === "BODY"
  );
  return body?.text ?? "";
}

function _varKeys(t: WabaTemplate): string[] {
  const found = new Set<string>();
  for (const m of _bodyText(t).matchAll(/\{\{(\d+)\}\}/g)) found.add(m[1]);
  return [...found].sort((a, b) => Number(a) - Number(b));
}

/**
 * Botão + modal "Nova conversa" (mig 170) — o operador inicia contato ativo.
 *
 * Evolution: texto livre. WABA/Twilio: template aprovado obrigatório (fora da
 * janela de 24h não existe texto livre; mesma régua do composer). A conversa
 * criada nasce atribuída a quem iniciou — a IA não entra.
 */
export function NovaConversaBotao({
  clienteInicial,
}: {
  /** Pré-preenche telefone/nome (entrada pela ficha do cliente). */
  clienteInicial?: { telefone: string; nome: string | null };
}) {
  const pode = usePermission("atendimento.iniciar");
  const [aberto, setAberto] = useState(false);
  if (!pode) return null;
  return (
    <>
      <Button
        type="button"
        variant="outline"
        size="sm"
        className="gap-1.5"
        onClick={() => setAberto(true)}
      >
        <MessageSquarePlus className="size-4" />
        Nova conversa
      </Button>
      {aberto && (
        <NovaConversaModal
          clienteInicial={clienteInicial}
          onFechar={() => setAberto(false)}
        />
      )}
    </>
  );
}

function NovaConversaModal({
  clienteInicial,
  onFechar,
}: {
  clienteInicial?: { telefone: string; nome: string | null };
  onFechar: () => void;
}) {
  const router = useRouter();
  // Conexão NÃO é escolha do operador: usamos a padrão da empresa (o
  // servidor resolve igual quando `conexao_id` vai vazio). Só carregamos a
  // lista pra saber o provider — WABA/Twilio exige template.
  const [conexoes, setConexoes] = useState<Conexao[] | null>(null);
  const [telefone, setTelefone] = useState(clienteInicial?.telefone ?? "");
  const [nome, setNome] = useState(clienteInicial?.nome ?? "");
  const [mensagem, setMensagem] = useState("");
  const [sugestoes, setSugestoes] = useState<
    { id: number; nome: string | null; telefone: string }[]
  >([]);
  const [templates, setTemplates] = useState<WabaTemplate[] | null>(null);
  const [templateId, setTemplateId] = useState<number | null>(null);
  const [vars, setVars] = useState<Record<string, string>>({});
  const [enviando, startEnviar] = useTransition();

  useEffect(() => {
    let vivo = true;
    fetch("/api/nova-conversa/opcoes")
      .then((r) => r.json())
      .then((d) => {
        if (vivo) setConexoes(d.conexao ? [d.conexao as Conexao] : []);
      })
      .catch(() => toast.error("Não foi possível carregar a conexão."));
    return () => {
      vivo = false;
    };
  }, []);

  // Padrão da empresa: `is_default` primeiro (a API já ordena assim).
  const conexao = conexoes?.[0] ?? null;
  const conexaoId = conexao?.id ?? "";
  const ehTemplate =
    conexao?.provider === "waba" ||
    (conexao?.provider?.startsWith("twilio") ?? false);

  // WABA/Twilio: carrega os templates aprovados quando a conexão muda.
  // Os resets (template/vars) ficam no handler do Select — setState síncrono
  // dentro de effect dispara render em cascata e o lint reprova.
  useEffect(() => {
    if (!ehTemplate || conexaoId === "") return;
    let alive = true;
    loadTemplatesAprovadosAction(conexaoId).then((r) => {
      if (!alive) return;
      if (r.ok) setTemplates(r.data);
      else toast.error(r.error);
    });
    return () => {
      alive = false;
    };
  }, [conexaoId, ehTemplate]);

  // Autocomplete de cliente existente (>=3 chars; nome ou telefone).
  useEffect(() => {
    if (clienteInicial) return;
    const q = telefone.trim();
    const t = window.setTimeout(() => {
      if (q.length < 3) {
        setSugestoes([]);
        return;
      }
      fetch(`/api/nova-conversa/opcoes?q=${encodeURIComponent(q)}`)
        .then((r) => r.json())
        .then((d) => setSugestoes(d.clientes ?? []))
        .catch(() => {});
    }, 300);
    return () => window.clearTimeout(t);
  }, [telefone, clienteInicial]);

  const sel = templates?.find((t) => t.id === templateId) ?? null;
  const keys = sel ? _varKeys(sel) : [];
  const pronto =
    conexaoId !== "" &&
    telefone.trim().length >= 8 &&
    (ehTemplate ? templateId !== null : mensagem.trim().length > 0);

  function enviar() {
    if (conexaoId === "") return;
    startEnviar(async () => {
      const r = await iniciarConversaAction({
        telefone: telefone.trim(),
        conexao_id: conexaoId,
        mensagem: ehTemplate ? undefined : mensagem.trim(),
        template_id: ehTemplate ? (templateId ?? undefined) : undefined,
        variaveis: ehTemplate ? vars : undefined,
        nome: nome.trim() || undefined,
      });
      if (!r.ok) {
        // 409 (opt-out/teto) e 400 já vêm com frase acionável do backend.
        toast.error(r.error);
        return;
      }
      toast.success(
        r.wasCreated
          ? "Conversa iniciada — ela está no topo da sua fila."
          : "Mensagem enviada na conversa já aberta com esse número."
      );
      onFechar();
      router.refresh();
    });
  }

  return (
    <Dialog open onOpenChange={(v) => !v && onFechar()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <MessageSquarePlus className="size-4" />
            Nova conversa
          </DialogTitle>
        </DialogHeader>

        <div className="space-y-3 text-sm">
          <div className="relative">
            <label className="mb-0.5 block text-xs text-muted-foreground">
              Telefone (com DDD) ou busque um cliente
            </label>
            <Input
              value={telefone}
              onChange={(e) => setTelefone(e.target.value)}
              placeholder="+55 67 99999-9999 ou nome do cliente"
              disabled={!!clienteInicial}
            />
            {sugestoes.length > 0 && (
              <ul className="absolute z-10 mt-1 w-full rounded-md border bg-popover shadow-lg">
                {sugestoes.map((c) => (
                  <li key={c.id}>
                    <button
                      type="button"
                      className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-accent"
                      onClick={() => {
                        setTelefone(c.telefone);
                        setNome(c.nome ?? "");
                        setSugestoes([]);
                      }}
                    >
                      <span>{c.nome || "Sem nome"}</span>
                      <span className="text-xs text-muted-foreground">
                        {c.telefone}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div>
            <label className="mb-0.5 block text-xs text-muted-foreground">
              Nome (opcional, para número novo)
            </label>
            <Input value={nome} onChange={(e) => setNome(e.target.value)} />
          </div>

          {!ehTemplate ? (
            <div>
              <label className="mb-0.5 block text-xs text-muted-foreground">
                Primeira mensagem
              </label>
              <Textarea
                value={mensagem}
                onChange={(e) => setMensagem(e.target.value)}
                rows={3}
              />
            </div>
          ) : (
            <div className="space-y-2">
              <label className="block text-xs text-muted-foreground">
                Template aprovado (obrigatório nesta conexão — janela de 24h)
              </label>
              {templates === null ? (
                <p className="text-xs text-muted-foreground">
                  Carregando templates…
                </p>
              ) : templates.length === 0 ? (
                <p className="text-xs text-muted-foreground">
                  Nenhum template aprovado nesta conexão. Crie/aprove em
                  Conexões → Templates.
                </p>
              ) : (
                <>
                  <Select
                    value={templateId === null ? null : String(templateId)}
                    onValueChange={(v: string | null) => {
                      setTemplateId(v ? Number(v) : null);
                      setVars({});
                    }}
                  >
                    <SelectTrigger className="w-full" aria-label="Template">
                      <SelectValue placeholder="Selecione um template…">
                        {(v: string | null) => {
                          const t = templates.find((x) => String(x.id) === v);
                          return t
                            ? `${t.nome} (${t.idioma})`
                            : "Selecione um template…";
                        }}
                      </SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      {templates.map((t) => (
                        <SelectItem key={t.id} value={String(t.id)}>
                          {t.nome} ({t.idioma})
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {sel && (
                    <p className="rounded-md bg-muted/50 p-2 text-xs text-muted-foreground whitespace-pre-wrap">
                      {_bodyText(sel)}
                    </p>
                  )}
                  {keys.map((k) => (
                    <div key={k}>
                      <label className="mb-0.5 block text-xs text-muted-foreground">
                        Variável {`{{${k}}}`}
                      </label>
                      <Input
                        value={vars[k] ?? ""}
                        onChange={(e) =>
                          setVars((p) => ({ ...p, [k]: e.target.value }))
                        }
                      />
                    </div>
                  ))}
                </>
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onFechar} disabled={enviando}>
            Cancelar
          </Button>
          <Button onClick={enviar} disabled={!pronto || enviando}>
            {enviando ? "Enviando…" : "Iniciar conversa"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
