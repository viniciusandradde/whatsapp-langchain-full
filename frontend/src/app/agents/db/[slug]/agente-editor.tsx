"use client";

import * as React from "react";
import Link from "next/link";
import { useState, useTransition } from "react";
import {
  Bot,
  Cog,
  FileText,
  MessageSquareText,
  Save,
  Sparkles,
  Star,
  Trash2,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type {
  AgenteIA,
  AgenteIAUpdateInput,
  EstiloResposta,
  LimiteCustoAcao,
} from "@/lib/api";

import {
  deleteAgenteAction,
  setDefaultAgenteAction,
  updateAgenteAction,
} from "./actions";

import type {
  AgenteTemplate,
  Departamento,
  MenuChatbot,
  ModeloLLM,
} from "@/lib/api";

interface Props {
  initialAgente: AgenteIA;
  modelosChat?: ModeloLLM[];
  menusAtivos?: MenuChatbot[];
  templates?: AgenteTemplate[];
  departamentos?: Departamento[];
}

type TabId = "identidade" | "modelo" | "prompt" | "tools" | "kb_mcp";

const TABS: { id: TabId; label: string; icon: typeof Bot }[] = [
  { id: "identidade", label: "Identidade", icon: Bot },
  { id: "modelo", label: "Modelo & Estilo", icon: Sparkles },
  { id: "prompt", label: "Prompt", icon: MessageSquareText },
  { id: "tools", label: "Tools & Mídia", icon: Cog },
  { id: "kb_mcp", label: "KB / MCP / Custo", icon: FileText },
];

const ESTILO_OPTIONS: { v: EstiloResposta; l: string; hint: string }[] = [
  { v: "preciso", l: "Preciso", hint: "factual, sem variação (temp 0.1)" },
  { v: "equilibrado", l: "Equilibrado", hint: "default (temp 0.5)" },
  { v: "criativo", l: "Criativo", hint: "explicações + alternativas (temp 0.9)" },
  {
    v: "muito_criativo",
    l: "Muito criativo",
    hint: "máxima variedade (temp 1.3)",
  },
];

const LIMITE_OPTIONS: { v: LimiteCustoAcao; l: string }[] = [
  { v: "solicitar_humano", l: "Solicitar atendimento humano" },
  { v: "encerrar", l: "Encerrar atendimento" },
  { v: "continuar", l: "Continuar (consume crédito extra)" },
  { v: "bloquear", l: "Bloquear (não responde)" },
];

// 13 tools que ZigChat tem (mapeado em docs/agente/MAPEAMENTO.md).
// Alguns vão exigir implementação no loader/agente Python — flag `pending`
// indica isso pra UI mostrar warning.
const TOOLS_DISPONIVEIS: { slug: string; label: string; pending?: boolean }[] = [
  { slug: "solicitar_humano", label: "Solicitar atendimento humano" },
  { slug: "transferir_dep", label: "Transferir para departamento" },
  { slug: "transferir_atendente", label: "Transferir para atendente", pending: true },
  { slug: "transferir_agente", label: "Transferir para outro agente IA", pending: true },
  { slug: "encerrar_atendimento", label: "Encerrar atendimento" },
  { slug: "abrir_menu", label: "Abrir menu chatbot", pending: true },
  { slug: "enviar_link", label: "Enviar link" },
  { slug: "chamar_webhook", label: "Chamar webhook customizado", pending: true },
  { slug: "tag_cliente", label: "Adicionar tag ao cliente" },
  { slug: "tag_atendimento", label: "Adicionar tag ao atendimento" },
  { slug: "consultar_contexto", label: "Consultar contexto do atendimento" },
  { slug: "salvar_contexto", label: "Salvar contexto do atendimento" },
  { slug: "buscar_arquivos", label: "Buscar arquivos na galeria", pending: true },
  // Existentes do nosso Nexus
  { slug: "search_knowledge_base", label: "Buscar na base de conhecimento (RAG)" },
  { slug: "calendar.create", label: "Criar evento Google Calendar" },
  { slug: "calendar.list", label: "Listar eventos Google Calendar" },
  { slug: "cliente.read", label: "Ler ficha do cliente" },
  { slug: "cliente.write", label: "Atualizar ficha do cliente" },
  { slug: "cliente_anotacao.create", label: "Criar anotação no cliente" },
];

export function AgenteEditor({
  initialAgente,
  modelosChat = [],
  menusAtivos = [],
  templates = [],
  departamentos = [],
}: Props) {
  const [a, setA] = useState(initialAgente);
  const [tab, setTab] = useState<TabId>("identidade");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function clear() {
    setError(null);
    setSuccess(null);
  }

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    clear();
    const fd = new FormData(e.currentTarget);
    const patch: AgenteIAUpdateInput = {};

    function getStr(name: string): string | null {
      const v = fd.get(name);
      if (v === null) return null;
      const s = String(v).trim();
      return s === "" ? null : s;
    }
    function getNum(name: string): number | null {
      const v = getStr(name);
      if (v === null) return null;
      const n = Number(v);
      return Number.isFinite(n) ? n : null;
    }
    function getBool(name: string): boolean {
      return fd.get(name) === "on";
    }

    if (tab === "identidade") {
      patch.nome = getStr("nome") ?? undefined;
      patch.descricao = getStr("descricao");
      patch.template_catalog = getStr("template_catalog") ?? undefined;
      patch.ativo = getBool("ativo");
      patch.departamento_default_id = getNum("departamento_default_id");
    }
    if (tab === "modelo") {
      // Sprint 2 paridade ZigChat (mig 043): preferencialmente salva
      // modelo_provedor + modelo_nome (separados); modelo único legacy
      // permanece editável via fallback quando catálogo modelo_llm vazio.
      const provedor = getStr("modelo_provedor");
      const nome = getStr("modelo_nome");
      if (provedor !== null) patch.modelo_provedor = provedor;
      if (nome !== null) patch.modelo_nome = nome;
      // Mantém compat: input "modelo" único ainda atualizável quando dropdown ausente
      const modeloLegacy = getStr("modelo");
      if (modeloLegacy !== null && !provedor && !nome) {
        patch.modelo = modeloLegacy;
      }
      patch.estilo_resposta = (getStr("estilo_resposta") ?? "equilibrado") as EstiloResposta;
      patch.temperatura_override = getNum("temperatura_override");
      patch.top_p_override = getNum("top_p_override");
      patch.max_tokens = getNum("max_tokens");
      // Sprint 2 paridade ZigChat (mig 043) — campos de memória + governança
      patch.tipo_memoria = getStr("tipo_memoria") ?? undefined;
      patch.janela_memoria = getNum("janela_memoria");
      patch.timeout_minutos = getNum("timeout_minutos");
      patch.acao_limite_menu_id = getNum("acao_limite_menu_id");
    }
    if (tab === "prompt") {
      patch.prompt_override = getStr("prompt_override");
    }
    if (tab === "tools") {
      patch.tools_enabled = TOOLS_DISPONIVEIS.filter((t) =>
        fd.get(`tool_${t.slug}`) === "on"
      ).map((t) => t.slug);
      patch.aceita_imagem = getBool("aceita_imagem");
      patch.aceita_audio = getBool("aceita_audio");
      patch.aceita_documento = getBool("aceita_documento");
    }
    if (tab === "kb_mcp") {
      const kbStr = getStr("base_conhecimento_ids") ?? "";
      const varStr = getStr("variavel_ids") ?? "";
      const mcpStr = getStr("mcp_server_ids") ?? "";
      patch.base_conhecimento_ids = kbStr
        ? kbStr.split(",").map((s) => Number(s.trim())).filter(Number.isFinite)
        : [];
      patch.variavel_ids = varStr
        ? varStr.split(",").map((s) => Number(s.trim())).filter(Number.isFinite)
        : [];
      patch.mcp_server_ids = mcpStr
        ? mcpStr.split(",").map((s) => Number(s.trim())).filter(Number.isFinite)
        : [];
      patch.limite_custo_acao = (getStr("limite_custo_acao") ?? "solicitar_humano") as LimiteCustoAcao;
    }

    startTransition(async () => {
      const r = await updateAgenteAction(a.slug, patch);
      if (!r.ok) {
        setError(r.error);
        return;
      }
      setA(r.data);
      setSuccess("Salvo.");
    });
  }

  function handleSetDefault() {
    if (a.is_default) return;
    if (!confirm(`Promover "${a.nome}" a agente default da empresa?`)) return;
    clear();
    startTransition(async () => {
      const r = await setDefaultAgenteAction(a.slug);
      if (!r.ok) {
        setError(r.error);
        return;
      }
      setA({ ...a, is_default: true });
      setSuccess("Default atualizado.");
    });
  }

  function handleDelete() {
    if (
      !confirm(
        `Desativar "${a.nome}"? (soft delete — preserva atendimentos vinculados; agente fica inativo mas não é apagado).`
      )
    )
      return;
    clear();
    startTransition(async () => {
      const r = await deleteAgenteAction(a.slug);
      if (!r.ok) {
        setError(r.error);
        return;
      }
      setA({ ...a, ativo: false });
      setSuccess("Desativado.");
    });
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-start justify-between gap-3">
          <div>
            <CardTitle className="flex items-center gap-2 text-lg">
              <Bot className="size-5 text-brand-primary" />
              {a.nome}
              {a.is_default && (
                <Badge variant="default">
                  <Star className="size-3" /> Default
                </Badge>
              )}
              {!a.ativo && <Badge variant="outline">inativo</Badge>}
            </CardTitle>
            <p className="mt-1 font-mono text-[11px] text-muted-foreground">
              {a.slug} · template {a.template_catalog}
            </p>
          </div>
          <div className="flex gap-2">
            {!a.is_default && a.ativo && (
              <Button
                size="sm"
                variant="ghost"
                onClick={handleSetDefault}
                disabled={isPending}
              >
                <Star className="size-3.5" />
                Tornar default
              </Button>
            )}
            {a.ativo && (
              <Button
                size="sm"
                variant="ghost"
                onClick={handleDelete}
                disabled={isPending}
              >
                <Trash2 className="size-3.5" />
                Desativar
              </Button>
            )}
          </div>
        </div>

        <nav className="mt-3 flex flex-wrap gap-1 border-b border-white/[0.06]">
          {TABS.map((t) => {
            const Icon = t.icon;
            const active = tab === t.id;
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => {
                  setTab(t.id);
                  clear();
                }}
                className={`flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm transition-colors ${
                  active
                    ? "border-brand-primary text-brand-primary"
                    : "border-transparent text-muted-foreground hover:text-foreground"
                }`}
              >
                <Icon className="size-3.5" />
                {t.label}
              </button>
            );
          })}
        </nav>
      </CardHeader>

      <CardContent>
        {error && (
          <p className="mb-3 rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
            {error}
          </p>
        )}
        {success && <p className="mb-3 text-sm text-emerald-300">{success}</p>}

        <form onSubmit={handleSubmit} className="space-y-4">
          {tab === "identidade" && (
            <TabIdentidade
              a={a}
              templates={templates}
              departamentos={departamentos}
            />
          )}
          {tab === "modelo" && (
            <TabModelo
              a={a}
              modelosChat={modelosChat}
              menusAtivos={menusAtivos}
            />
          )}
          {tab === "prompt" && <TabPrompt a={a} />}
          {tab === "tools" && <TabTools a={a} />}
          {tab === "kb_mcp" && <TabKbMcp a={a} />}

          <div className="flex justify-end pt-3">
            <Button type="submit" disabled={isPending}>
              <Save className="size-3.5" />
              {isPending ? "Salvando…" : "Salvar"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

// ============= TABS =============

function TabIdentidade({
  a,
  templates,
  departamentos,
}: {
  a: AgenteIA;
  templates: AgenteTemplate[];
  departamentos: Departamento[];
}) {
  // Garante que o template atual aparece mesmo se não estiver no catálogo
  // (ex: template legacy renomeado). Nesse caso adiciona como opção
  // "{slug} (não-encontrado)" pra não perder a config.
  const allTemplates: AgenteTemplate[] =
    templates.length === 0
      ? [{ slug: a.template_catalog, label: a.template_catalog, descricao: "" }]
      : templates.some((t) => t.slug === a.template_catalog)
      ? templates
      : [
          ...templates,
          {
            slug: a.template_catalog,
            label: `${a.template_catalog} (não-encontrado)`,
            descricao: "Template legacy ou removido do catálogo",
          },
        ];

  const templateAtual = allTemplates.find((t) => t.slug === a.template_catalog);

  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
      <Field label="Nome" name="nome" defaultValue={a.nome} />
      <FieldSelect
        label="Template (catálogo)"
        name="template_catalog"
        defaultValue={a.template_catalog}
        options={allTemplates.map((t) => ({ v: t.slug, l: t.label }))}
      />
      {templateAtual?.descricao && (
        <p className="-mt-2 text-[11px] text-muted-foreground md:col-span-2">
          <code className="font-mono">{templateAtual.slug}</code>:{" "}
          {templateAtual.descricao}
        </p>
      )}
      <div className="md:col-span-2">
        <FieldTextarea
          label="Descrição"
          name="descricao"
          defaultValue={a.descricao}
        />
      </div>

      {/* Triagem omnichannel — departamento destino do transfer_to_human */}
      <div className="md:col-span-2 rounded-md border border-amber-200/60 bg-amber-50/40 p-3 dark:border-amber-700/40 dark:bg-amber-950/20">
        <label className="text-sm font-medium" htmlFor="departamento_default_id">
          Departamento padrão para transferência
        </label>
        {departamentos.length === 0 ? (
          <p className="mt-1 text-xs text-amber-900 dark:text-amber-200">
            Nenhum departamento cadastrado.{" "}
            <Link
              href="/settings/departamentos"
              className="font-medium underline"
            >
              Cadastrar departamento
            </Link>{" "}
            antes de configurar este campo.
          </p>
        ) : (
          <>
            <select
              id="departamento_default_id"
              name="departamento_default_id"
              defaultValue={a.departamento_default_id ?? ""}
              className="mt-1 flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus-visible:ring-1 focus-visible:ring-ring"
            >
              <option value="">— sem departamento —</option>
              {departamentos
                .filter((d) => d.ativo)
                .map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.nome}
                    {d.users_count != null ? ` (${d.users_count} membros)` : ""}
                  </option>
                ))}
            </select>
            <p className="mt-1 text-xs text-muted-foreground">
              Quando este agente chamar{" "}
              <code className="font-mono">transfer_to_human</code>, o atendimento
              vai pro departamento selecionado.{" "}
              {a.departamento_default_id == null && (
                <span className="text-amber-700 dark:text-amber-400">
                  Sem depto: a tool retorna erro instrutivo ao agente.
                </span>
              )}
            </p>
          </>
        )}
      </div>

      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          name="ativo"
          defaultChecked={a.ativo}
          className="size-4"
        />
        Ativo (worker resolve esse agente)
      </label>
    </div>
  );
}

function TabModelo({
  a,
  modelosChat,
  menusAtivos,
}: {
  a: AgenteIA;
  modelosChat: ModeloLLM[];
  menusAtivos: MenuChatbot[];
}) {
  // Provedor inicial: prefere modelo_provedor da mig 043; cai pro split do
  // modelo único legacy.
  const provedorInicial =
    a.modelo_provedor ||
    (a.modelo && a.modelo.includes("/") ? a.modelo.split("/")[0] : "") ||
    "";
  const nomeInicial =
    a.modelo_nome ||
    (a.modelo && a.modelo.includes("/") ? a.modelo.split("/").slice(1).join("/") : a.modelo || "") ||
    "";

  const [provedor, setProvedor] = useState(provedorInicial);
  const [nome, setNome] = useState(nomeInicial);

  // Provedores únicos disponíveis no catálogo
  const provedoresDisponiveis = Array.from(
    new Set(modelosChat.map((m) => m.provedor))
  ).sort();

  // Modelos do provedor selecionado
  const modelosDoProvedor = modelosChat
    .filter((m) => m.provedor === provedor)
    .sort((x, y) => x.nome.localeCompare(y.nome));

  // Modelo selecionado (pra mostrar custos)
  const modeloSelecionado = modelosChat.find(
    (m) => m.provedor === provedor && m.nome === nome
  );

  const semCatalogo = modelosChat.length === 0;

  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
      {semCatalogo ? (
        // Fallback: catálogo modelo_llm vazio → input livre legacy
        <Field
          label="Modelo (slug livre — catálogo vazio)"
          name="modelo"
          defaultValue={a.modelo}
          placeholder="google/gemini-2.5-flash"
        />
      ) : (
        <>
          <FieldSelect
            label="Provedor"
            name="modelo_provedor"
            defaultValue={provedor}
            onChange={(v: string) => {
              setProvedor(v);
              setNome("");  // limpa modelo quando muda provedor
            }}
            options={[
              { v: "", l: "— selecione —" },
              ...provedoresDisponiveis.map((p) => ({ v: p, l: p })),
            ]}
          />
          <FieldSelect
            label="Modelo"
            name="modelo_nome"
            defaultValue={nome}
            onChange={(v: string) => setNome(v)}
            options={[
              { v: "", l: provedor ? "— selecione —" : "(escolha o provedor)" },
              ...modelosDoProvedor.map((m) => ({
                v: m.nome,
                l: m.descricao ? `${m.nome} — ${m.descricao}` : m.nome,
              })),
            ]}
            disabled={!provedor}
          />
        </>
      )}
      <FieldSelect
        label="Estilo de respostas"
        name="estilo_resposta"
        defaultValue={a.estilo_resposta}
        options={ESTILO_OPTIONS.map((o) => ({
          v: o.v,
          l: `${o.l} — ${o.hint}`,
        }))}
      />
      <Field
        label="Temperatura (override fino opcional)"
        name="temperatura_override"
        defaultValue={a.temperatura_override?.toString() ?? null}
        type="number"
        placeholder={`auto: ${a.temperatura_efetiva.toFixed(2)}`}
      />
      <Field
        label="Top-p (override fino opcional)"
        name="top_p_override"
        defaultValue={a.top_p_override?.toString() ?? null}
        type="number"
        placeholder={`auto: ${a.top_p_efetivo.toFixed(2)}`}
      />
      <Field
        label="Max tokens (limite de saída)"
        name="max_tokens"
        defaultValue={a.max_tokens?.toString() ?? null}
        type="number"
      />

      {/* Sub-fase B+ paridade ZigChat (mig 043) — memória + governança */}
      <FieldSelect
        label="Tipo de memória"
        name="tipo_memoria"
        defaultValue={a.tipo_memoria ?? "window"}
        options={[
          { v: "window", l: "Window — últimas N msgs (default)" },
          { v: "buffer", l: "Buffer — todo histórico do thread" },
          { v: "summary", l: "Summary — resumo + janela curta" },
          { v: "none", l: "Sem memória — cada msg é isolada" },
        ]}
      />
      <Field
        label="Janela de memória (msgs)"
        name="janela_memoria"
        defaultValue={a.janela_memoria?.toString() ?? null}
        type="number"
        placeholder="ex: 20 (só se tipo=window)"
      />
      <Field
        label="Timeout conversa (min)"
        name="timeout_minutos"
        defaultValue={a.timeout_minutos?.toString() ?? null}
        type="number"
        placeholder="ex: 30 — vazio = sem timeout"
      />
      <FieldSelect
        label="Limite custo → menu"
        name="acao_limite_menu_id"
        defaultValue={a.acao_limite_menu_id?.toString() ?? ""}
        options={[
          { v: "", l: "— nenhum (usa limite_custo_acao) —" },
          ...menusAtivos.map((m) => ({
            v: String(m.id),
            l: `Menu #${m.id} — ${m.nome}`,
          })),
        ]}
      />

      <div className="rounded-md border border-white/[0.06] bg-white/[0.02] p-3 text-xs">
        <p className="font-medium">Valores efetivos:</p>
        <p>
          Temperatura: <code>{a.temperatura_efetiva.toFixed(2)}</code>
        </p>
        <p>
          Top-p: <code>{a.top_p_efetivo.toFixed(2)}</code>
        </p>
        {modeloSelecionado && (
          <>
            <p className="mt-2 font-medium">Custo {modeloSelecionado.nome}:</p>
            <p>
              Input: <code>${modeloSelecionado.custo_input_mtok ?? "?"}/M tok</code>
            </p>
            <p>
              Output: <code>${modeloSelecionado.custo_output_mtok ?? "?"}/M tok</code>
            </p>
            {modeloSelecionado.janela_contexto && (
              <p>
                Contexto:{" "}
                <code>
                  {modeloSelecionado.janela_contexto.toLocaleString("pt-BR")} tok
                </code>
              </p>
            )}
          </>
        )}
        <p className="mt-2 text-muted-foreground">
          Override fino sobrescreve o preset do estilo.
        </p>
      </div>
    </div>
  );
}

function TabPrompt({ a }: { a: AgenteIA }) {
  return (
    <div>
      <FieldTextarea
        label="System prompt (override do template — Markdown OK)"
        name="prompt_override"
        defaultValue={a.prompt_override}
        rows={20}
      />
      <p className="mt-1 text-[11px] text-muted-foreground">
        Quando vazio, usa o SYSTEM_PROMPT do <code>{a.template_catalog}</code>.
        Suporta variáveis <code>{`{{$NOME_VAR}}`}</code> definidas em /settings/variaveis.
      </p>
    </div>
  );
}

function TabTools({ a }: { a: AgenteIA }) {
  const enabledSet = new Set(a.tools_enabled);
  return (
    <div className="space-y-4">
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Ferramentas ({enabledSet.size}/{TOOLS_DISPONIVEIS.length})
        </p>
        <ul className="grid grid-cols-1 gap-1 md:grid-cols-2">
          {TOOLS_DISPONIVEIS.map((t) => (
            <li key={t.slug}>
              <label className="flex items-start gap-2 rounded-md border border-white/[0.04] bg-white/[0.02] p-2 text-xs">
                <input
                  type="checkbox"
                  name={`tool_${t.slug}`}
                  defaultChecked={enabledSet.has(t.slug)}
                  className="mt-0.5 size-3.5"
                />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1">
                    <span className="font-mono text-[10px]">{t.slug}</span>
                    {t.pending && (
                      <Badge variant="outline" className="text-[9px]">
                        backlog
                      </Badge>
                    )}
                  </div>
                  <p className="text-muted-foreground">{t.label}</p>
                </div>
              </label>
            </li>
          ))}
        </ul>
        <p className="mt-2 text-[11px] text-muted-foreground">
          <strong>backlog</strong> = tool prevista no roadmap (loader Python
          ainda não tem); ativá-la não quebra mas não tem efeito.
        </p>
      </div>

      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Tipos de mídia aceita
        </p>
        <ul className="grid grid-cols-3 gap-2">
          <li>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                name="aceita_imagem"
                defaultChecked={a.aceita_imagem}
                className="size-4"
              />
              Imagens
            </label>
          </li>
          <li>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                name="aceita_audio"
                defaultChecked={a.aceita_audio}
                className="size-4"
              />
              Áudios
            </label>
          </li>
          <li>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                name="aceita_documento"
                defaultChecked={a.aceita_documento}
                className="size-4"
              />
              Documentos
            </label>
          </li>
        </ul>
      </div>
    </div>
  );
}

function TabKbMcp({ a }: { a: AgenteIA }) {
  return (
    <div className="space-y-4">
      <div>
        <Field
          label="Bases de Conhecimento (IDs separados por vírgula; vazio = todas)"
          name="base_conhecimento_ids"
          defaultValue={a.base_conhecimento_ids.join(",")}
          placeholder="1,3,7"
        />
        <p className="mt-1 text-[11px] text-muted-foreground">
          Limita quais documentos o agente vê. Sem isso, busca em todos os docs ativos da empresa.
        </p>
      </div>
      <Field
        label="Variáveis ambiente (IDs separados por vírgula)"
        name="variavel_ids"
        defaultValue={a.variavel_ids.join(",")}
      />
      <Field
        label="MCP Servers (IDs — backlog Fase 2)"
        name="mcp_server_ids"
        defaultValue={a.mcp_server_ids.join(",")}
        placeholder="(MCP ainda não implementado)"
      />

      <div className="border-t border-white/[0.06] pt-3">
        <FieldSelect
          label="Limite de custo: ação ao atingir limite mensal da empresa"
          name="limite_custo_acao"
          defaultValue={a.limite_custo_acao}
          options={LIMITE_OPTIONS.map((o) => ({ v: o.v, l: o.l }))}
        />
      </div>
    </div>
  );
}

// ============= helpers =============

function Field({
  label,
  name,
  defaultValue,
  type = "text",
  placeholder,
}: {
  label: string;
  name: string;
  defaultValue: string | null;
  type?: string;
  placeholder?: string;
}) {
  return (
    <div>
      <label
        htmlFor={name}
        className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground"
      >
        {label}
      </label>
      <input
        id={name}
        name={name}
        type={type}
        defaultValue={defaultValue ?? ""}
        placeholder={placeholder}
        className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
      />
    </div>
  );
}

function FieldTextarea({
  label,
  name,
  defaultValue,
  rows = 4,
}: {
  label: string;
  name: string;
  defaultValue: string | null;
  rows?: number;
}) {
  return (
    <div>
      <label
        htmlFor={name}
        className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground"
      >
        {label}
      </label>
      <textarea
        id={name}
        name={name}
        defaultValue={defaultValue ?? ""}
        rows={rows}
        className="w-full rounded-md border border-input bg-background px-3 py-2 font-mono text-xs focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
      />
    </div>
  );
}

function FieldSelect({
  label,
  name,
  defaultValue,
  options,
  onChange,
  disabled,
}: {
  label: string;
  name: string;
  defaultValue: string;
  options: { v: string; l: string }[];
  onChange?: (v: string) => void;
  disabled?: boolean;
}) {
  // Quando onChange é passado, vira controlled (necessário pra dropdowns
  // dependentes como provedor → modelo).
  const isControlled = onChange !== undefined;
  return (
    <div>
      <label
        htmlFor={name}
        className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground"
      >
        {label}
      </label>
      <select
        id={name}
        name={name}
        {...(isControlled
          ? {
              value: defaultValue,
              onChange: (e: React.ChangeEvent<HTMLSelectElement>) =>
                onChange?.(e.target.value),
            }
          : { defaultValue })}
        disabled={disabled}
        className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm disabled:opacity-50"
      >
        {options.map((o) => (
          <option key={o.v} value={o.v}>
            {o.l}
          </option>
        ))}
      </select>
    </div>
  );
}
