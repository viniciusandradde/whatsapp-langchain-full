"use client";

import Link from "next/link";
import { useEffect, useRef, useState, useTransition } from "react";
import { Megaphone, Plus, Send, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { Campanha, Conexao, WabaTemplate } from "@/lib/api";

import {
  createCampanhaAction,
  loadApprovedTemplatesAction,
  loadTagsAction,
  previewCrmAction,
  uploadCampanhaMediaAction,
} from "./actions";
import type { Tag } from "@/lib/api";

function _bodyText(t: WabaTemplate): string {
  return t.componentes_json.find((c) => (c.type || "").toUpperCase() === "BODY")?.text ?? "";
}

function _varKeys(t: WabaTemplate): string[] {
  const found = new Set<string>();
  for (const m of _bodyText(t).matchAll(/\{\{(\d+)\}\}/g)) found.add(m[1]);
  return [...found].sort((a, b) => Number(a) - Number(b));
}

interface Props {
  initialCampanhas: Campanha[];
  conexoes: Conexao[];
  loadError?: string | null;
}

const STATUS_LABELS: Record<Campanha["status"], string> = {
  draft: "rascunho",
  scheduled: "agendada",
  running: "em execução",
  done: "concluída",
  partial: "parcial",
  aborted: "abortada",
};

const STATUS_VARIANTS: Record<Campanha["status"], "default" | "outline" | "secondary" | "destructive"> = {
  draft: "outline",
  scheduled: "default",
  running: "default",
  done: "secondary",
  partial: "outline",
  aborted: "destructive",
};

export function CampanhasPageClient({
  initialCampanhas,
  conexoes,
  loadError,
}: Props) {
  const [campanhas, setCampanhas] = useState(initialCampanhas);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  // Modo de conteúdo: texto livre (janela 24h) OU template HSM aprovado.
  const [modo, setModo] = useState<"texto" | "template">("texto");
  const [conexaoId, setConexaoId] = useState<string>("");
  const [templates, setTemplates] = useState<WabaTemplate[]>([]);
  const [templateId, setTemplateId] = useState<number | null>(null);
  const [templateVars, setTemplateVars] = useState<Record<string, string>>({});

  // Anti-ban (migs 120/121): jitter min/max + kill-switch, com preset seguro.
  const [intervaloMin, setIntervaloMin] = useState(3000);
  const [intervaloMax, setIntervaloMax] = useState(8000);
  const [killPct, setKillPct] = useState(30);
  // Pausa longa periódica anti-ban (mig 127): a cada N envios, descansa M s.
  const [pausaCada, setPausaCada] = useState(0);
  const [pausaSeg, setPausaSeg] = useState(600);
  // Telefones controlado pra permitir pré-preenchimento vindo de Contatos.
  const [telefonesText, setTelefonesText] = useState("");
  // Mídia (foto) — mig 123. media_url relativo (/uploads/disparador/..).
  const [mediaUrl, setMediaUrl] = useState<string | null>(null);
  const [mediaUploading, setMediaUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  // Buscar do CRM (Slice A) — filtros que resolvem telefones de clientes.
  const [tagsDisponiveis, setTagsDisponiveis] = useState<Tag[]>([]);
  const [crmTags, setCrmTags] = useState<Set<string>>(new Set());
  const [crmSegmento, setCrmSegmento] = useState("");
  const [crmLifecycle, setCrmLifecycle] = useState("");
  const [crmSearch, setCrmSearch] = useState("");
  const [crmLoading, setCrmLoading] = useState(false);

  useEffect(() => {
    loadTagsAction().then((r) => {
      if (r.ok) setTagsDisponiveis(r.data);
    });
  }, []);

  function toggleCrmTag(nome: string) {
    setCrmTags((prev) => {
      const next = new Set(prev);
      if (next.has(nome)) next.delete(nome);
      else next.add(nome);
      return next;
    });
  }

  async function adicionarDoCrm() {
    setCrmLoading(true);
    setError(null);
    const r = await previewCrmAction({
      tags: crmTags.size ? [...crmTags] : undefined,
      segmento: crmSegmento.trim() || null,
      lifecycle_stage: crmLifecycle.trim() || null,
      search: crmSearch.trim() || null,
    });
    setCrmLoading(false);
    if (!r.ok) {
      setError(r.error);
      return;
    }
    // mescla com o textarea, dedupe.
    const atuais = new Set(
      telefonesText
        .split(/[\s,;]+/)
        .map((s) => s.trim())
        .filter(Boolean)
    );
    for (const t of r.data.telefones) atuais.add(t);
    setTelefonesText([...atuais].join("\n"));
    setSuccess(`${r.data.total} contato(s) do CRM adicionado(s) à lista.`);
  }

  async function handleMediaUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    setMediaUploading(true);
    setError(null);
    const fd = new FormData();
    fd.set("file", f);
    const r = await uploadCampanhaMediaAction(fd);
    setMediaUploading(false);
    if (!r.ok) {
      setError(r.error);
      return;
    }
    setMediaUrl(r.data.media_url);
  }

  function aplicarModoSeguro() {
    setIntervaloMin(5000);
    setIntervaloMax(15000);
    setKillPct(25);
    setPausaCada(50);
    setPausaSeg(600);
  }

  // Pré-preenche a lista quando vem da página de Contatos ("Criar campanha
  // com selecionados") — os telefones ficam no sessionStorage. setState fica
  // num microtask pra não violar set-state-in-effect do compiler.
  useEffect(() => {
    let tel: string | null = null;
    try {
      tel = sessionStorage.getItem("campanha_telefones");
      if (tel) sessionStorage.removeItem("campanha_telefones");
    } catch {
      tel = null;
    }
    if (!tel) return;
    const lista = tel;
    Promise.resolve().then(() => {
      setTelefonesText(lista);
      setCreating(true);
      aplicarModoSeguro();
    });
  }, []);

  // Carrega templates aprovados ao escolher conexão no modo template.
  // (setState só no callback async — evita set-state-in-effect do compiler.)
  useEffect(() => {
    if (modo !== "template" || !conexaoId) return;
    let alive = true;
    loadApprovedTemplatesAction(Number(conexaoId)).then((r) => {
      if (alive && r.ok) setTemplates(r.data);
    });
    return () => {
      alive = false;
    };
  }, [modo, conexaoId]);

  // Só consideramos templates carregados quando relevante (modo+conexão).
  const templatesAtivos =
    modo === "template" && conexaoId ? templates : [];
  const selTemplate = templatesAtivos.find((t) => t.id === templateId) ?? null;
  const templateKeys = selTemplate ? _varKeys(selTemplate) : [];

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    const fd = new FormData(e.currentTarget);
    const telefonesRaw = String(fd.get("telefones") || "").trim();
    const telefones = telefonesRaw
      .split(/[\s,;]+/)
      .map((s) => s.trim())
      .filter(Boolean);

    if (telefones.length === 0) {
      setError("Adicione ao menos 1 telefone.");
      return;
    }
    if (
      modo === "texto" &&
      !String(fd.get("mensagem") || "").trim() &&
      !mediaUrl
    ) {
      setError("Escreva uma mensagem ou anexe uma foto.");
      return;
    }
    if (modo === "template" && !templateId) {
      setError("Escolha um template aprovado (ou use Texto livre).");
      return;
    }
    if (modo === "template" && templateKeys.some((k) => !(templateVars[k] ?? "").trim())) {
      setError("Preencha todas as variáveis do template ({{nome}} usa o nome do cliente).");
      return;
    }

    const modeloRaw = String(fd.get("modelo_mensagem_id") || "").trim();
    const tagsRaw = String(fd.get("filtro_tags") || "").trim();
    const scheduledRaw = String(fd.get("scheduled_at") || "").trim();
    const body = {
      nome: String(fd.get("nome") || "").trim(),
      descricao: (String(fd.get("descricao") || "").trim() || null) as
        | string
        | null,
      mensagem: modo === "texto" ? String(fd.get("mensagem") || "").trim() : null,
      conexao_id: conexaoId ? Number(conexaoId) : null,
      intervalo_ms: intervaloMin,
      intervalo_min_ms: intervaloMin,
      intervalo_max_ms: intervaloMax,
      kill_switch_pct: killPct,
      pausa_a_cada: pausaCada,
      pausa_segundos: pausaSeg,
      max_destinatarios: Number(fd.get("max_destinatarios") || 1000),
      telefones,
      // Sub-fase B+ (padrão profissional) (mig 051)
      modelo_mensagem_id: modeloRaw ? Number(modeloRaw) : null,
      scheduled_at: scheduledRaw ? new Date(scheduledRaw).toISOString() : null,
      agendar: !!scheduledRaw,
      tipo: (String(fd.get("tipo") || "broadcast") as "broadcast" | "transactional" | "reativacao"),
      filtro_segmento: String(fd.get("filtro_segmento") || "").trim() || null,
      filtro_tags: tagsRaw
        ? tagsRaw.split(",").map((s) => s.trim()).filter(Boolean)
        : null,
      // Template HSM (mig 113)
      message_template_id: modo === "template" ? templateId : null,
      template_variaveis: modo === "template" ? templateVars : {},
      // Mídia (mig 123) — foto só no modo texto (Evolution); legenda = mensagem
      media_url: modo === "texto" ? mediaUrl : null,
      media_tipo: modo === "texto" && mediaUrl ? "image" : null,
    };

    startTransition(async () => {
      const r = await createCampanhaAction(body);
      if (!r.ok) {
        setError(r.error);
        return;
      }
      setCampanhas([r.data, ...campanhas]);
      setCreating(false);
      setSuccess(`Campanha criada com ${r.data.total_destinatarios} destinatário(s).`);
    });
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
            <Megaphone className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold">Campanhas</h1>
            <p className="mt-0.5 text-sm text-muted-foreground">
              Broadcast de mensagem pra lista de telefones via WhatsApp.
            </p>
          </div>
        </div>
        <Button
          onClick={() => setCreating(true)}
          disabled={creating || isPending}
        >
          <Plus className="size-4" />
          Nova campanha
        </Button>
      </div>

      {loadError && (
        <p className="rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
          {loadError}
        </p>
      )}
      {error && <p className="text-sm text-destructive">{error}</p>}
      {success && <p className="text-sm text-emerald-300">{success}</p>}

      {creating && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>Nova campanha</CardTitle>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => setCreating(false)}
              >
                <X className="size-4" />
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
                  Nome
                </label>
                <input
                  name="nome"
                  required
                  maxLength={120}
                  placeholder="Promoção Black Friday"
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
                  Descrição (opcional)
                </label>
                <input
                  name="descricao"
                  maxLength={500}
                  className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                />
              </div>
              <div>
                <div className="mb-2 flex gap-1 rounded-md border border-border/40 p-0.5 text-xs">
                  <button
                    type="button"
                    onClick={() => setModo("texto")}
                    className={`flex-1 rounded px-2 py-1 ${modo === "texto" ? "bg-primary/15 font-medium text-primary" : "text-muted-foreground"}`}
                  >
                    Texto livre
                  </button>
                  <button
                    type="button"
                    onClick={() => setModo("template")}
                    className={`flex-1 rounded px-2 py-1 ${modo === "template" ? "bg-primary/15 font-medium text-primary" : "text-muted-foreground"}`}
                  >
                    Template HSM
                  </button>
                </div>

                {modo === "texto" ? (
                  <>
                    <textarea
                      name="mensagem"
                      maxLength={4000}
                      rows={4}
                      placeholder="Olá! Promoção válida até..."
                      className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                    />
                    <p className="mt-1 text-[11px] text-muted-foreground">
                      Texto livre só entrega pra contatos com janela de 24h aberta.
                      Pra broadcast real (fora da janela), use Template HSM.
                    </p>
                    {/* Foto (mig 123) — vira a legenda quando há texto */}
                    <div className="mt-2 rounded-md border border-dashed border-border/60 p-2">
                      <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
                        📷 Foto (opcional)
                      </label>
                      {mediaUrl ? (
                        <div className="flex items-center gap-2">
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img
                            src={mediaUrl}
                            alt="prévia"
                            className="h-16 w-16 rounded object-cover"
                          />
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            onClick={() => setMediaUrl(null)}
                          >
                            Remover
                          </Button>
                        </div>
                      ) : (
                        <>
                          <input
                            ref={fileRef}
                            type="file"
                            accept="image/png,image/jpeg,image/webp,image/gif"
                            onChange={handleMediaUpload}
                            className="hidden"
                          />
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            disabled={mediaUploading}
                            onClick={() => fileRef.current?.click()}
                          >
                            {mediaUploading ? "Enviando…" : "📷 Escolher foto"}
                          </Button>
                        </>
                      )}
                      <p className="mt-1 text-[11px] text-muted-foreground">
                        {mediaUploading
                          ? "Enviando foto…"
                          : "A mensagem acima vira a legenda da foto. Envio de foto requer conexão Evolution."}
                      </p>
                    </div>
                  </>
                ) : (
                  <div className="space-y-2">
                    {!conexaoId ? (
                      <p className="text-xs text-muted-foreground">
                        Escolha a conexão abaixo pra listar os templates aprovados.
                      </p>
                    ) : templatesAtivos.length === 0 ? (
                      <p className="text-xs text-muted-foreground">
                        Nenhum template aprovado nesta conexão. Aprove em
                        Conexões → Templates.
                      </p>
                    ) : (
                      <>
                        <select
                          value={templateId ?? ""}
                          onChange={(e) => {
                            setTemplateId(e.target.value ? Number(e.target.value) : null);
                            setTemplateVars({});
                          }}
                          className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                        >
                          <option value="">Selecione um template…</option>
                          {templatesAtivos.map((t) => (
                            <option key={t.id} value={t.id}>
                              {t.nome} ({t.idioma})
                            </option>
                          ))}
                        </select>
                        {selTemplate && (
                          <p className="rounded-md bg-muted/40 p-2 text-xs text-muted-foreground whitespace-pre-wrap">
                            {_bodyText(selTemplate)}
                          </p>
                        )}
                        {templateKeys.map((k) => (
                          <div key={k}>
                            <label className="mb-0.5 block text-[11px] text-muted-foreground">
                              Variável {`{{${k}}}`}
                            </label>
                            <input
                              value={templateVars[k] ?? ""}
                              onChange={(e) =>
                                setTemplateVars((p) => ({ ...p, [k]: e.target.value }))
                              }
                              placeholder={k === "1" ? "ex: {{nome}} (usa o nome do cliente)" : ""}
                              className="flex h-9 w-full rounded-md border border-input bg-background px-2 py-1 text-sm"
                            />
                          </div>
                        ))}
                        <p className="text-[11px] text-muted-foreground">
                          Dica: use <code>{"{{nome}}"}</code> numa variável pra
                          inserir o primeiro nome de cada cliente.
                        </p>
                      </>
                    )}
                  </div>
                )}
              </div>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                <div>
                  <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
                    Conexão
                  </label>
                  <select
                    name="conexao_id"
                    value={conexaoId}
                    onChange={(e) => {
                      setConexaoId(e.target.value);
                      setTemplateId(null);
                      setTemplateVars({});
                    }}
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  >
                    <option value="">
                      {modo === "template" ? "Selecione a conexão…" : "Primeira ativa"}
                    </option>
                    {conexoes.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.from_number} ({c.provider})
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
                    Máx destinatários
                  </label>
                  <input
                    type="number"
                    name="max_destinatarios"
                    defaultValue={1000}
                    min={1}
                    max={10_000}
                    className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                  />
                </div>
              </div>
              <div>
                <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
                  Telefones (1 por linha, vírgula ou espaço)
                </label>
                <textarea
                  name="telefones"
                  required
                  rows={6}
                  value={telefonesText}
                  onChange={(e) => setTelefonesText(e.target.value)}
                  placeholder={"+5511999999999\n+5511988888888"}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs"
                />
                <p className="mt-1 text-[11px] text-muted-foreground">
                  Telefones inválidos (&lt;8 dígitos) são descartados.
                  Duplicados são ignorados.
                </p>
              </div>

              {/* Buscar do CRM (Slice A) — filtros que resolvem telefones */}
              <div className="rounded-md border border-blue-300/40 bg-blue-50/40 p-3 space-y-2 dark:bg-blue-950/10">
                <p className="text-xs font-semibold uppercase tracking-wide text-blue-700 dark:text-blue-400">
                  📇 Buscar do CRM
                </p>
                {tagsDisponiveis.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {tagsDisponiveis.map((t) => (
                      <button
                        key={t.id}
                        type="button"
                        onClick={() => toggleCrmTag(t.nome)}
                        className={`rounded-full border px-2 py-0.5 text-xs ${
                          crmTags.has(t.nome)
                            ? "border-primary bg-primary/15 font-medium text-primary"
                            : "border-input text-muted-foreground"
                        }`}
                      >
                        {t.nome}
                      </button>
                    ))}
                  </div>
                )}
                <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
                  <input
                    placeholder="Segmento"
                    value={crmSegmento}
                    onChange={(e) => setCrmSegmento(e.target.value)}
                    className="h-9 rounded-md border border-input bg-background px-2 text-xs"
                  />
                  <input
                    placeholder="Lifecycle (lead/cliente…)"
                    value={crmLifecycle}
                    onChange={(e) => setCrmLifecycle(e.target.value)}
                    className="h-9 rounded-md border border-input bg-background px-2 text-xs"
                  />
                  <input
                    placeholder="Buscar nome/telefone"
                    value={crmSearch}
                    onChange={(e) => setCrmSearch(e.target.value)}
                    className="h-9 rounded-md border border-input bg-background px-2 text-xs"
                  />
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={crmLoading}
                  onClick={adicionarDoCrm}
                >
                  {crmLoading ? "Buscando…" : "+ Adicionar contatos do CRM"}
                </Button>
                <p className="text-[11px] text-muted-foreground">
                  Sem filtro = todos os clientes com telefone. Os telefones são
                  somados à lista acima (sem duplicar).
                </p>
              </div>

              {/* Anti-ban: jitter aleatório + kill-switch (migs 120/121) */}
              <div className="rounded-md border border-amber-300/40 bg-amber-50/40 p-3 space-y-3 dark:bg-amber-950/10">
                <div className="flex items-center justify-between">
                  <p className="text-xs font-semibold uppercase tracking-wide text-amber-700 dark:text-amber-400">
                    🛡️ Anti-ban
                  </p>
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={aplicarModoSeguro}
                  >
                    Modo Seguro
                  </Button>
                </div>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                  <div>
                    <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
                      Intervalo mín (ms)
                    </label>
                    <input
                      type="number"
                      name="intervalo_min_ms"
                      value={intervaloMin}
                      onChange={(e) => setIntervaloMin(Number(e.target.value))}
                      min={0}
                      max={600_000}
                      className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
                      Intervalo máx (ms)
                    </label>
                    <input
                      type="number"
                      name="intervalo_max_ms"
                      value={intervaloMax}
                      onChange={(e) => setIntervaloMax(Number(e.target.value))}
                      min={0}
                      max={600_000}
                      className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
                      Kill-switch (% falha)
                    </label>
                    <input
                      type="number"
                      name="kill_switch_pct"
                      value={killPct}
                      onChange={(e) => setKillPct(Number(e.target.value))}
                      min={0}
                      max={100}
                      className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                    />
                  </div>
                </div>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div>
                    <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
                      Pausa a cada (envios)
                    </label>
                    <input
                      type="number"
                      name="pausa_a_cada"
                      value={pausaCada}
                      onChange={(e) => setPausaCada(Number(e.target.value))}
                      min={0}
                      max={100_000}
                      placeholder="0 = desligado"
                      className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                    />
                  </div>
                  <div>
                    <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
                      Duração da pausa (s)
                    </label>
                    <input
                      type="number"
                      name="pausa_segundos"
                      value={pausaSeg}
                      onChange={(e) => setPausaSeg(Number(e.target.value))}
                      min={0}
                      max={86_400}
                      className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                    />
                  </div>
                </div>
                <p className="text-[11px] text-muted-foreground">
                  Cada envio espera um tempo <strong>aleatório</strong> entre mín e
                  máx (cadência fixa = assinatura de bot). A campanha
                  <strong> aborta sozinha</strong> se a taxa de falha passar do
                  kill-switch. A <strong>pausa periódica</strong> dá um descanso
                  longo a cada N envios (0 = desligado). <strong>Mídia</strong> tem
                  piso de 8s entre envios mesmo com intervalo menor.
                  <strong> Modo Seguro</strong> = 5–15s + 25% + pausa 600s/50.
                </p>
              </div>

              {/* Configurações avançadas */}
              <div className="rounded-md border border-border/40 bg-muted/20 p-3 space-y-3">
                <p className="text-xs font-semibold uppercase tracking-wide">
                  Avançado
                </p>
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
                  <div>
                    <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
                      Tipo
                    </label>
                    <select
                      name="tipo"
                      defaultValue="broadcast"
                      className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                    >
                      <option value="broadcast">Broadcast (livre)</option>
                      <option value="transactional">Transacional</option>
                      <option value="reativacao">Reativação</option>
                    </select>
                  </div>
                  <div>
                    <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
                      Modelo interno (ID)
                    </label>
                    <input
                      type="number"
                      name="modelo_mensagem_id"
                      placeholder="ID em /modelos"
                      className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                    />
                    <p className="mt-1 text-[10px] text-muted-foreground">
                      Quick-reply interno (≠ template HSM — esse fica no toggle
                      acima).
                    </p>
                  </div>
                  <div>
                    <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
                      Agendar pra (datetime local)
                    </label>
                    <input
                      type="datetime-local"
                      name="scheduled_at"
                      className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                    />
                    <p className="mt-1 text-[10px] text-muted-foreground">
                      Vazio = inicia manualmente
                    </p>
                  </div>
                  <div>
                    <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
                      Filtro: segmento
                    </label>
                    <input
                      type="text"
                      name="filtro_segmento"
                      maxLength={120}
                      placeholder='Ex: "lead-quente"'
                      className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                    />
                  </div>
                  <div className="sm:col-span-2">
                    <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
                      Filtro: tags (separadas por vírgula)
                    </label>
                    <input
                      type="text"
                      name="filtro_tags"
                      placeholder="vip, eventos-2026"
                      className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                    />
                  </div>
                </div>
                <p className="text-[10px] text-muted-foreground">
                  Filtros são metadados — NÃO substituem a lista de telefones
                  (filtrar de fato fica pra dispatcher futuro).
                </p>
              </div>

              <div className="flex justify-end gap-2">
                <Button
                  type="button"
                  variant="ghost"
                  onClick={() => setCreating(false)}
                  disabled={isPending}
                >
                  Cancelar
                </Button>
                <Button type="submit" disabled={isPending}>
                  <Send className="size-3.5" />
                  Criar como rascunho
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {campanhas.length} campanha(s)
          </CardTitle>
        </CardHeader>
        <CardContent>
          {campanhas.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Nenhuma campanha ainda. Use &quot;Nova campanha&quot; pra criar.
            </p>
          ) : (
            <ul className="divide-y rounded-md border">
              {campanhas.map((c) => (
                <li key={c.id} className="p-3">
                  <Link
                    href={`/campanhas/${c.id}`}
                    className="flex items-start justify-between gap-3 hover:opacity-80"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <p className="font-medium">{c.nome}</p>
                        <Badge variant={STATUS_VARIANTS[c.status]}>
                          {STATUS_LABELS[c.status]}
                        </Badge>
                      </div>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {c.enviados}/{c.total_destinatarios} enviados ·
                        {" "}{c.falhas} falhas ·{" "}
                        {new Date(c.created_at).toLocaleString("pt-BR")}
                      </p>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
