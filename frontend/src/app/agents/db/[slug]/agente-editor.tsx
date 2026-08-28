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
  FlaskConical,
  RotateCcw,
  Send,
  Loader2,
  FileDown,
  Plus,
  X,
  Paperclip,
} from "lucide-react";

import { AjudaCampo } from "@/components/ajuda-campo";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
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
import { PromptHistorico } from "./prompt-historico";

/** Um tipo de mídia que o agente lê, com o que ele faz com ela. */
function MidiaAceita({
  name,
  defaultChecked,
  label,
  ajuda,
}: {
  name: string;
  defaultChecked: boolean;
  label: string;
  ajuda: string;
}) {
  return (
    <li className="flex items-start gap-2 rounded-md border border-foreground/[0.06] bg-foreground/[0.02] p-2.5">
      <Checkbox id={name} name={name} defaultChecked={defaultChecked} className="mt-0.5" />
      <div className="min-w-0">
        <Label htmlFor={name} className="text-sm font-medium">
          {label}
        </Label>
        <p className="text-[11px] leading-snug text-muted-foreground">{ajuda}</p>
      </div>
    </li>
  );
}

import type {
  AgenteTemplate,
  Departamento,
  MenuChatbot,
  ModeloLLM,
  Pasta,
} from "@/lib/api";

interface Props {
  initialAgente: AgenteIA;
  modelosChat?: ModeloLLM[];
  menusAtivos?: MenuChatbot[];
  templates?: AgenteTemplate[];
  departamentos?: Departamento[];
  pastas?: Pasta[];
}

type TabId = "identidade" | "modelo" | "prompt" | "tools" | "kb_mcp" | "testar";

const TABS: { id: TabId; label: string; icon: typeof Bot }[] = [
  { id: "identidade", label: "Identidade", icon: Bot },
  { id: "modelo", label: "Modelo & Estilo", icon: Sparkles },
  { id: "prompt", label: "Prompt", icon: MessageSquareText },
  { id: "tools", label: "Tools & Mídia", icon: Cog },
  { id: "kb_mcp", label: "KB / MCP / Custo", icon: FileText },
  { id: "testar", label: "Testar", icon: FlaskConical },
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

// 13 tools de referência (mapeadas em docs/agente/MAPEAMENTO.md).
// Alguns vão exigir implementação no loader/agente Python — flag `pending`
// indica isso pra UI mostrar warning.
const TOOLS_DISPONIVEIS: { slug: string; label: string; pending?: boolean }[] = [
  { slug: "solicitar_humano", label: "Solicitar atendimento humano" },
  { slug: "transferir_dep", label: "Transferir para departamento" },
  { slug: "transferir_atendente", label: "Transferir para atendente", pending: true },
  { slug: "transferir_agente", label: "Transferir para outro agente IA", pending: true },
  { slug: "encerrar_atendimento", label: "Encerrar atendimento" },
  { slug: "abrir_menu", label: "Abrir menu chatbot", pending: true },
  // `pending`: nunca teve tool. O agente manda link no corpo da mensagem,
  // não por ferramenta — aparecia como disponível e não fazia nada.
  { slug: "enviar_link", label: "Enviar link", pending: true },
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
  // Reanálise sob demanda. O worker já descreve a imagem e transcreve o áudio
  // antes do agente rodar; estas deixam ele voltar ao arquivo com uma pergunta
  // dirigida. Só valem se o agente aceitar aquela mídia (aba Mídia).
  { slug: "midia.imagem", label: "Reanalisar imagem recebida" },
  { slug: "midia.audio", label: "Retranscrever áudio recebido" },
  { slug: "midia.documento", label: "Extrair e resumir documento" },
];

export function AgenteEditor({
  initialAgente,
  modelosChat = [],
  menusAtivos = [],
  templates = [],
  departamentos = [],
  pastas = [],
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
      // "on" é o que o checkbox nativo submete; "true" cobre o primitivo do
      // Base UI. Aceitar os dois evita que trocar o componente desligue a
      // opção em silêncio — que é o tipo de falha que não dá erro nenhum.
      const v = fd.get(name);
      return v === "on" || v === "true";
    }

    if (tab === "identidade") {
      patch.nome = getStr("nome") ?? undefined;
      patch.descricao = getStr("descricao");
      patch.template_catalog = getStr("template_catalog") ?? undefined;
      patch.ativo = getBool("ativo");
      patch.departamento_default_id = getNum("departamento_default_id");
    }
    if (tab === "modelo") {
      // Sprint 2 padrão profissional (mig 043): preferencialmente salva
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
      // Sprint 2 padrão profissional (mig 043) — campos de memória + governança
      patch.tipo_memoria = getStr("tipo_memoria") ?? undefined;
      patch.janela_memoria = getNum("janela_memoria");
      patch.timeout_minutos = getNum("timeout_minutos");
      patch.acao_limite_menu_id = getNum("acao_limite_menu_id");
    }
    if (tab === "prompt") {
      patch.prompt_override = getStr("prompt_override");
      // `nota` só faz sentido junto do prompt — o backend a usa como
      // "mensagem de commit" da versão e a ignora quando o texto não muda.
      const nota = getStr("nota");
      if (nota) patch.nota = nota;
    }
    if (tab === "tools") {
      patch.tools_enabled = TOOLS_DISPONIVEIS.filter((t) =>
        fd.get(`tool_${t.slug}`) === "on"
      ).map((t) => t.slug);
      patch.aceita_imagem = getBool("aceita_imagem");
      patch.aceita_audio = getBool("aceita_audio");
      patch.aceita_documento = getBool("aceita_documento");
      patch.anuncia_transferencia = getBool("anuncia_transferencia");
      patch.fewshot_enabled = getBool("fewshot_enabled");
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

        <nav className="mt-3 flex flex-wrap gap-1 border-b border-foreground/[0.06]">
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

        {/* Tab Testar vive FORA do <form> de config: chat interativo não
            pode disputar Enter/submit com o botão Salvar. */}
        {tab === "testar" && (
          <TabTestar
            slug={a.slug}
            modeloAtual={a.modelo ?? a.modelo_nome ?? null}
            modelos={modelosChat}
          />
        )}

        {tab !== "testar" && (
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
          {tab === "prompt" && (
            <TabPrompt
              a={a}
              onRestaurado={(agente) => {
                setA(agente);
                setSuccess("Versão restaurada.");
              }}
            />
          )}
          {tab === "tools" && <TabTools a={a} />}
          {tab === "kb_mcp" && <TabKbMcp a={a} pastas={pastas} />}

          <div className="flex justify-end pt-3">
            <Button type="submit" disabled={isPending}>
              <Save className="size-3.5" />
              {isPending ? "Salvando…" : "Salvar"}
            </Button>
          </div>
        </form>
        )}
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
            ajuda={
              <>
                <p>Quem fabrica o modelo de IA (Google, OpenAI, DeepSeek…). Escolha primeiro o provedor; a lista de modelos ao lado é filtrada por ele.</p>
                <p><b>Como decidir:</b> os modelos curados aqui já foram validados pela plataforma. Trocar de provedor muda preço, velocidade e o jeito de responder — modelo de chat novo passa pelo teste do golden antes de atender cliente (aba Testar).</p>
              </>
            }
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
            ajuda={
              <>
                <p>O cérebro do agente: é este modelo que lê a conversa e escreve as respostas de texto. Mídia (foto, áudio, documento) é processada por um modelo próprio, configurado pela plataforma.</p>
                <p><b>Custo:</b> cobrado por tokens de entrada e saída — os valores /Mtok aparecem abaixo ao selecionar. <b>Não troque no escuro:</b> valide na aba Testar (compare até 4 modelos com casos reais) antes de salvar em agente que atende cliente.</p>
              </>
            }
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
        ajuda={
          <>
            <p>Predefinição de temperatura pronta: <b>Preciso</b> (0.1) responde sempre igual, ideal pra informação factual (preços, horários, regras); <b>Equilibrado</b> varia um pouco e soa mais natural; <b>Criativo</b> improvisa mais — bom pra venda, arriscado pra suporte.</p>
            <p>É o jeito simples de calibrar. Só use o override de temperatura abaixo se souber exatamente por quê.</p>
          </>
        }
        defaultValue={a.estilo_resposta}
        options={ESTILO_OPTIONS.map((o) => ({
          v: o.v,
          l: `${o.l} — ${o.hint}`,
        }))}
      />
      <Field
        label="Temperatura (override fino opcional)"
        name="temperatura_override"
        ajuda={
          <>
            <p>Controle fino da aleatoriedade, de 0 a 2. <b>Baixa (0–0.3)</b>: respostas consistentes e repetíveis. <b>Alta (0.8+)</b>: mais variedade e criatividade, mais chance de fugir do roteiro.</p>
            <p><b>Vazio = usa o Estilo acima</b> (o placeholder mostra o valor efetivo). Preencher aqui VENCE o estilo — deixe vazio a menos que um caso concreto peça um número específico.</p>
          </>
        }
        defaultValue={a.temperatura_override?.toString() ?? null}
        type="number"
        placeholder={`auto: ${a.temperatura_efetiva.toFixed(2)}`}
      />
      <Field
        label="Top-p (override fino opcional)"
        name="top_p_override"
        ajuda={
          <>
            <p>Limita o vocabulário do modelo às palavras mais prováveis (0 a 1). <b>0.6</b>: conservador, vocabulário enxuto. <b>0.95+</b>: solta o vocabulário inteiro.</p>
            <p>Ajuste temperatura OU top-p, não os dois ao mesmo tempo — mexer nos dois torna o comportamento imprevisível. <b>Vazio = automático</b>, que serve pra quase todo caso.</p>
          </>
        }
        defaultValue={a.top_p_override?.toString() ?? null}
        type="number"
        placeholder={`auto: ${a.top_p_efetivo.toFixed(2)}`}
      />
      <Field
        label="Max tokens (limite de saída)"
        name="max_tokens"
        ajuda={
          <>
            <p>Teto de tamanho de cada resposta (≈ 1 token = ¾ de palavra). <b>350</b> ≈ um parágrafo bom de WhatsApp — segura custo e evita textão.</p>
            <p><b>Cuidado com valor baixo demais:</b> a resposta é CORTADA no meio ao bater o teto, não resumida. Se o agente precisa listar itens longos (tabela de preços, passo a passo), suba pra 600–800. Vazio = sem limite (o modelo decide).</p>
          </>
        }
        defaultValue={a.max_tokens?.toString() ?? null}
        type="number"
      />

      {/* Sub-fase B+ (padrão profissional) (mig 043) — memória + governança */}
      <FieldSelect
        label="Tipo de memória"
        name="tipo_memoria"
        ajuda={
          <>
            <p>O que o agente lembra DENTRO da conversa: <b>Window</b> (default) relê só as últimas N mensagens — barato e suficiente pra atendimento. <b>Buffer</b> relê a conversa inteira — memória perfeita, custo cresce a cada turno. <b>Summary</b> resume o passado e mantém janela curta — conversas muito longas. <b>Sem memória</b> trata cada mensagem isolada — só pra FAQ pura.</p>
            <p>Cada mensagem relida é cobrada de novo como entrada — memória maior = custo maior por turno.</p>
          </>
        }
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
        ajuda={
          <>
            <p>Quantas mensagens recentes o agente relê a cada resposta. <b>Só vale com Tipo = Window.</b></p>
            <p><b>20</b> (≈10 idas e voltas) atende a maioria. Menos que 10: o agente “esquece” o que o cliente disse há pouco e repete perguntas. Mais que 40: custo sobe sem ganho perceptível.</p>
          </>
        }
        defaultValue={a.janela_memoria?.toString() ?? null}
        type="number"
        placeholder="ex: 20 (só se tipo=window)"
      />
      <Field
        label="Timeout conversa (min)"
        name="timeout_minutos"
        ajuda={
          <>
            <p>Minutos de silêncio do cliente até a conversa ser considerada encerrada. Quando ele voltar depois disso, o agente começa contexto novo (sem carregar o assunto antigo).</p>
            <p><b>30</b> funciona bem para atendimento. <b>Vazio = nunca expira</b> — o agente carrega o histórico pra sempre, o que pode misturar assuntos de dias diferentes.</p>
          </>
        }
        defaultValue={a.timeout_minutos?.toString() ?? null}
        type="number"
        placeholder="ex: 30 — vazio = sem timeout"
      />
      <FieldSelect
        label="Limite custo → menu"
        name="acao_limite_menu_id"
        ajuda={
          <>
            <p>Rede de segurança de gasto: quando a empresa estoura o teto de custo de IA do mês (Governança → Budget IA), o agente para de gastar e este menu do chatbot assume o atendimento no lugar dele.</p>
            <p><b>Nenhum</b> = usa a ação padrão configurada no budget (avisar ou bloquear). Escolher um menu aqui mantém o cliente atendido — por botões, sem IA — mesmo com o budget estourado.</p>
          </>
        }
        defaultValue={a.acao_limite_menu_id?.toString() ?? ""}
        options={[
          { v: "", l: "— nenhum (usa limite_custo_acao) —" },
          ...menusAtivos.map((m) => ({
            v: String(m.id),
            l: `Menu #${m.id} — ${m.nome}`,
          })),
        ]}
      />

      <div className="rounded-md border border-foreground/[0.06] bg-foreground/[0.02] p-3 text-xs">
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

function AssistenteRedacao({
  slug,
  onAplicar,
  onFechar,
}: {
  slug: string;
  onAplicar: (prompt: string) => void;
  onFechar: () => void;
}) {
  const [descricao, setDescricao] = useState("");
  const [gerando, startGerar] = useTransition();
  const [erro, setErro] = useState<string | null>(null);
  const [gerado, setGerado] = useState<{
    prompt: string;
    avisos: string[];
  } | null>(null);

  function handleGerar() {
    setErro(null);
    startGerar(async () => {
      const { redigirPromptAction } = await import("./actions");
      const r = await redigirPromptAction(slug, descricao);
      if (r.ok) setGerado(r.data);
      else setErro(r.error);
    });
  }

  return (
    <div className="space-y-3 rounded-md border bg-muted/30 p-3">
      <p className="text-xs text-muted-foreground">
        Descreva o agente em duas linhas. O texto é redigido no padrão da casa
        e usa <strong>só</strong> as ferramentas marcadas na aba Ferramentas e
        as variáveis cadastradas — é o que impede o prompt de prometer o que o
        agente não faz.
      </p>
      <FieldTextarea
        label="O que este agente deve fazer"
        name="__descricao_assistente"
        defaultValue=""
        rows={3}
        placeholder="assistente de matrículas da faculdade, atende aluno no WhatsApp, transfere pra secretaria quando for financeiro"
        onChange={setDescricao}
      />
      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          size="sm"
          onClick={handleGerar}
          disabled={gerando || descricao.trim().length < 10}
        >
          {gerando && <Loader2 className="mr-2 size-4 animate-spin" />}
          Gerar
        </Button>
        <Button type="button" variant="ghost" size="sm" onClick={onFechar}>
          Fechar
        </Button>
      </div>

      {erro && <p className="text-sm text-destructive">{erro}</p>}

      {gerado && (
        <div className="space-y-2">
          {gerado.avisos.length > 0 && (
            <ul className="space-y-1 rounded-md border border-warning/40 bg-warning/10 p-2 text-xs text-warning-foreground">
              {gerado.avisos.map((av) => (
                <li key={av}>{av}</li>
              ))}
            </ul>
          )}
          {/* Painel de leitura: o campo só é sobrescrito quando o usuário
              manda. Prompt de produção passa de 15 mil caracteres — trocar
              às cegas é caro, e o histórico só protege o que já foi salvo. */}
          <pre className="max-h-80 overflow-auto rounded-md border bg-background p-3 font-mono text-xs whitespace-pre-wrap">
            {gerado.prompt}
          </pre>
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              size="sm"
              onClick={() => {
                onAplicar(gerado.prompt);
                setGerado(null);
                onFechar();
              }}
            >
              Usar este
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => setGerado(null)}
            >
              Descartar
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function TabPrompt({
  a,
  onRestaurado,
}: {
  a: AgenteIA;
  onRestaurado: (agente: AgenteIA) => void;
}) {
  // Texto vindo do assistente, ainda NÃO salvo. Entra no `key` junto com o
  // `updated_at` pelo mesmo motivo que a restauração: o textarea é não
  // controlado, então só remontando o conteúdo novo aparece em tela.
  const [gerado, setGerado] = useState<string | null>(null);
  // O `aberto` mora aqui, não no assistente: o painel ocupa a largura toda e
  // precisa ficar ABAIXO do cabeçalho. Dentro da linha do flex ele empurrava o
  // botão de histórico pro lado do campo de descrição.
  const [assistenteAberto, setAssistenteAberto] = useState(false);

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-medium">Instruções do agente</p>
        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setAssistenteAberto((v) => !v)}
          >
            <Sparkles className="mr-2 size-4" />
            Assistente de redação
          </Button>
          <PromptHistorico
            slug={a.slug}
            atual={a.prompt_override ?? ""}
            onRestaurado={(ag) => {
              setGerado(null);
              onRestaurado(ag);
            }}
          />
        </div>
      </div>
      {assistenteAberto && (
        <AssistenteRedacao
          slug={a.slug}
          onAplicar={setGerado}
          onFechar={() => setAssistenteAberto(false)}
        />
      )}
      {gerado !== null && (
        <p className="text-xs text-muted-foreground">
          Texto do assistente aplicado no campo — <strong>ainda não salvo</strong>.
          Revise e salve; a versão anterior fica no histórico.
        </p>
      )}
      {/* `key` amarra o textarea à versão em uso: sem ela, restaurar troca o
          defaultValue mas o React mantém o texto antigo em tela, e o usuário
          acha que a restauração não funcionou. O mesmo vale pro texto gerado. */}
      <FieldTextarea
        key={`${a.updated_at ?? a.slug}:${gerado ? gerado.length : 0}`}
        label=""
        name="prompt_override"
        defaultValue={gerado ?? a.prompt_override}
        rows={28}
      />
      <Field
        label="Nota desta alteração (opcional)"
        name="nota"
        defaultValue={null}
        placeholder="o que mudou — aparece no histórico"
        maxLength={200}
      />
      <div className="space-y-1 text-[11px] text-muted-foreground">
        <p>
          É o que define como o agente responde. Aceita Markdown e é o campo
          mais importante desta tela — modelo e temperatura mudam o tom, isto
          muda o comportamento.
        </p>
        {/* A sintaxe correta é `{{namespace.chave}}` (`render_template` em
            shared/variavel.py). O texto anterior ensinava `{{$NOME_VAR}}`, que
            não casa com o regex — e chave que não resolve fica LITERAL na
            resposta ao cliente, então o erro ia parar na conversa. */}
        <p>
          Variáveis: <code>{`{{empresa.nome}}`}</code>,{" "}
          <code>{`{{data.hoje}}`}</code>, e as suas em{" "}
          <code>{`{{var.NOME}}`}</code> — cadastradas em Variáveis. O que não
          existir fica escrito como está na resposta.
        </p>
      </div>
    </div>
  );
}

function TabTools({ a }: { a: AgenteIA }) {
  const enabledSet = new Set(a.tools_enabled);
  // Conta só o que existe de verdade. O denominador antigo incluía as de
  // backlog, e o numerador podia contar slug de backlog que ficou marcado
  // (o agente 80 tinha `buscar_arquivos`) — dava "11/19" sem significado.
  const toolsReais = TOOLS_DISPONIVEIS.filter((t) => !t.pending);
  const ativasReais = toolsReais.filter((t) => enabledSet.has(t.slug)).length;
  return (
    <div className="space-y-4">
      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Ferramentas ({ativasReais}/{toolsReais.length})
        </p>
        <ul className="grid grid-cols-1 gap-1 md:grid-cols-2">
          {TOOLS_DISPONIVEIS.map((t) => (
            <li key={t.slug}>
              <label
                className={`flex items-start gap-2 rounded-md border border-foreground/[0.04] bg-foreground/[0.02] p-2 text-xs ${
                  // Backlog: visível pra mostrar roadmap, mas não marcável —
                  // marcar não ligava nada e o backend ignora.
                  t.pending ? "cursor-not-allowed opacity-50" : ""
                }`}
                title={
                  t.pending
                    ? "Ainda não implementada — marcar não tem efeito."
                    : undefined
                }
              >
                <input
                  type="checkbox"
                  name={`tool_${t.slug}`}
                  defaultChecked={!t.pending && enabledSet.has(t.slug)}
                  disabled={t.pending}
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
        <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          O que este agente lê
        </p>
        <p className="mb-3 text-[11px] text-muted-foreground">
          Desmarcado, o arquivo continua chegando e aparecendo no painel — o
          agente só confirma o recebimento pelo nome, sem ler o conteúdo.
        </p>
        <ul className="grid gap-3 sm:grid-cols-3">
          <MidiaAceita
            name="aceita_imagem"
            defaultChecked={a.aceita_imagem}
            label="Imagens"
            ajuda="Descrição da foto por modelo de visão"
          />
          <MidiaAceita
            name="aceita_audio"
            defaultChecked={a.aceita_audio}
            label="Áudios"
            ajuda="Transcrição da nota de voz"
          />
          <MidiaAceita
            name="aceita_documento"
            defaultChecked={a.aceita_documento}
            label="Documentos"
            ajuda="Lê PDF, DOCX, XLSX e DOC"
          />
        </ul>
      </div>

      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Transferência
        </p>
        <label className="flex items-start gap-2 rounded-md border border-foreground/[0.04] bg-foreground/[0.02] p-2 text-sm">
          <input
            type="checkbox"
            name="anuncia_transferencia"
            defaultChecked={a.anuncia_transferencia}
            className="mt-0.5 size-4"
          />
          <span className="min-w-0 flex-1">
            Avisar o cliente sobre o departamento
            <span className="mt-0.5 block text-xs text-muted-foreground">
              Envia a mensagem oficial ao transferir: &quot;Seu atendimento foi
              transferido para o departamento de X. Protocolo: …&quot;. Desligue
              em assistente pessoal, onde vocabulário de departamento soa
              corporativo — a transferência acontece igual, o cliente lê só a
              frase do próprio agente.
            </span>
          </span>
        </label>
      </div>

      <div>
        <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          Aprendizado com exemplos
        </p>
        <label className="flex items-start gap-2 rounded-md border border-foreground/[0.04] bg-foreground/[0.02] p-2 text-sm">
          <Checkbox
            name="fewshot_enabled"
            defaultChecked={a.fewshot_enabled}
            className="mt-0.5"
          />
          <span className="min-w-0 flex-1">
            Usar exemplos bem avaliados nas respostas
            <span className="mt-0.5 block text-xs text-muted-foreground">
              A cada mensagem, busca os atendimentos parecidos que os clientes
              melhor avaliaram (Dataset &amp; Eval) e os mostra ao agente como
              referência — ele passa a imitar o padrão dos melhores
              atendimentos. Custa um pouco mais por mensagem (busca + tokens
              extras); ligue, acompanhe alguns dias e decida.
            </span>
          </span>
        </label>
      </div>
    </div>
  );
}

function TabKbMcp({ a, pastas }: { a: AgenteIA; pastas: Pasta[] }) {
  const [selectedKbs, setSelectedKbs] = useState<number[]>(
    a.base_conhecimento_ids
  );
  const toggleKb = (id: number) =>
    setSelectedKbs((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  const selectedSet = new Set(selectedKbs);
  return (
    <div className="space-y-4">
      <div>
        <label className="text-sm font-medium">Bases de Conhecimento</label>
        <p className="mt-1 text-[11px] text-muted-foreground">
          Selecione uma ou mais pastas. Sem nenhuma seleção, o agente busca em
          toda a base da empresa.
        </p>
        {/* Hidden input que o handleSubmit (kbStr split) consome */}
        <input
          type="hidden"
          name="base_conhecimento_ids"
          value={selectedKbs.join(",")}
        />
        {pastas.length === 0 ? (
          <div className="mt-2 rounded-md border border-amber-300 bg-amber-50 p-3 text-xs text-amber-900 dark:border-amber-700 dark:bg-amber-950/30 dark:text-amber-200">
            Nenhuma pasta cadastrada.{" "}
            <Link
              href="/settings/pastas"
              className="font-medium underline hover:text-amber-700"
            >
              Criar pasta
            </Link>
          </div>
        ) : (
          <div className="mt-2 max-h-64 overflow-y-auto rounded-md border bg-background">
            {pastas.map((p) => {
              const isSelected = selectedSet.has(p.id);
              return (
                <label
                  key={p.id}
                  className={`flex cursor-pointer items-center gap-2 border-b px-3 py-2 text-sm last:border-0 hover:bg-accent ${
                    isSelected ? "bg-accent/30" : ""
                  }`}
                >
                  <input
                    type="checkbox"
                    checked={isSelected}
                    onChange={() => toggleKb(p.id)}
                    className="size-4 rounded border-input accent-primary"
                  />
                  <span className="flex-1 truncate">{p.nome}</span>
                  {p.docs_count !== null && p.docs_count !== undefined && (
                    <Badge variant="outline" className="text-[10px]">
                      {p.docs_count} docs
                    </Badge>
                  )}
                </label>
              );
            })}
          </div>
        )}
        {selectedKbs.length > 0 && (
          <p className="mt-2 text-[11px] text-muted-foreground">
            {selectedKbs.length} pasta(s) selecionada(s).
          </p>
        )}
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

      <div className="border-t border-foreground/[0.06] pt-3">
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
  maxLength,
  ajuda,
}: {
  label: string;
  name: string;
  defaultValue: string | null;
  type?: string;
  placeholder?: string;
  maxLength?: number;
  ajuda?: React.ReactNode;
}) {
  return (
    <div>
      <div className="mb-1 flex items-center gap-1.5">
        <label
          htmlFor={name}
          className="block text-xs uppercase tracking-wide text-muted-foreground"
        >
          {label}
        </label>
        {ajuda ? <AjudaCampo titulo={label}>{ajuda}</AjudaCampo> : null}
      </div>
      <input
        id={name}
        name={name}
        type={type}
        defaultValue={defaultValue ?? ""}
        placeholder={placeholder}
        maxLength={maxLength}
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
  placeholder,
  // O campo segue NÃO controlado (o form lê pelo `name`); `onChange` existe só
  // pra quem precisa do texto antes do submit — caso do assistente de redação,
  // que manda a descrição pra API. Controlar o valor aqui quebraria o truque
  // do `key` que faz restaurar versão aparecer em tela.
  onChange,
}: {
  label: string;
  name: string;
  defaultValue: string | null;
  rows?: number;
  placeholder?: string;
  onChange?: (valor: string) => void;
}) {
  return (
    <div>
      {/* label vazio = o título já está fora do componente (aba Prompt, que
          põe o botão de histórico na mesma linha). Renderizar mesmo assim
          deixaria uma faixa em branco acima do campo. */}
      {label ? (
        <label
          htmlFor={name}
          className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground"
        >
          {label}
        </label>
      ) : null}
      <textarea
        id={name}
        name={name}
        defaultValue={defaultValue ?? ""}
        rows={rows}
        placeholder={placeholder}
        onChange={onChange ? (e) => onChange(e.target.value) : undefined}
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
  ajuda,
}: {
  label: string;
  name: string;
  defaultValue: string;
  options: { v: string; l: string }[];
  onChange?: (v: string) => void;
  disabled?: boolean;
  ajuda?: React.ReactNode;
}) {
  // Quando onChange é passado, vira controlled (necessário pra dropdowns
  // dependentes como provedor → modelo).
  const isControlled = onChange !== undefined;
  return (
    <div>
      <div className="mb-1 flex items-center gap-1.5">
        <label
          htmlFor={name}
          className="block text-xs uppercase tracking-wide text-muted-foreground"
        >
          {label}
        </label>
        {ajuda ? <AjudaCampo titulo={label}>{ajuda}</AjudaCampo> : null}
      </div>
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


// ---- Tab Testar — chat com o agente real, sem WhatsApp (+ A/B de modelo) ----
//
// Conversa com o pipeline real (prompt + variáveis + memória + KB) numa
// thread isolada de teste no servidor. Nada é enviado ao WhatsApp e nenhum
// cliente/atendimento é tocado. Modo A/B compara dois modelos lado a lado.

import type {
  TestarAgenteResult,
  BateriaPlacar,
  TestarBateriaResult,
} from "@/lib/api";

type Resposta = TestarAgenteResult | { erro: string };
// Anexo do chat de teste (áudio/documento/imagem) — base64 puro + MIME.
type MidiaTeste = { base64: string; tipo: string; nome: string };
type MsgTeste =
  | { role: "user"; texto: string; midia?: { nome: string; tipo: string } }
  | {
      role: "agente";
      // 1 entrada (modo simples) ou N (modo comparação, até 4), alinhadas
      // posicionalmente com `modelos` (null = modelo próprio do agente).
      respostas: (Resposta | undefined)[];
      modelos: (string | null)[];
    };

// Rótulo curto do tipo de mídia pra UI (chip do anexo).
function tipoMidiaLabel(mime: string): string {
  const m = (mime || "").toLowerCase();
  if (m.startsWith("audio/")) return "Áudio";
  if (m.startsWith("image/")) return "Imagem";
  if (m.includes("pdf")) return "PDF";
  if (m.includes("word") || m.includes("msword") || m.endsWith("document"))
    return "Documento";
  if (m.startsWith("text/")) return "Texto";
  return "Arquivo";
}

// Lê um File como base64 puro (sem o prefixo data:...;base64,).
function lerArquivoBase64(f: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const r = String(reader.result || "");
      resolve(r.includes(",") ? r.slice(r.indexOf(",") + 1) : r);
    };
    reader.onerror = () => reject(new Error("Falha ao ler o arquivo."));
    reader.readAsDataURL(f);
  });
}

// Export PDF sem dependência: monta HTML estruturado numa janela nova e
// dispara o "Salvar como PDF" nativo do navegador. Zero lib no bundle/CI.
function esc(s: string): string {
  return String(s ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function abrirPdf(titulo: string, corpoHtml: string) {
  const dataHora = new Date().toLocaleString("pt-BR");
  const w = window.open("", "_blank", "width=900,height=1000");
  if (!w) {
    alert("Permita pop-ups para exportar o PDF.");
    return;
  }
  w.document.write(`<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<title>${esc(titulo)}</title>
<style>
  * { box-sizing: border-box; }
  body { font-family: -apple-system, Segoe UI, Roboto, sans-serif; color: #111; margin: 32px; font-size: 12px; }
  h1 { font-size: 18px; margin: 0 0 4px; }
  .meta { color: #666; font-size: 11px; margin-bottom: 16px; }
  table { width: 100%; border-collapse: collapse; margin: 8px 0 20px; }
  th, td { border: 1px solid #ddd; padding: 6px 8px; text-align: left; font-size: 11px; }
  th { background: #f4f4f5; }
  td.num { text-align: right; font-variant-numeric: tabular-nums; }
  .win { background: #ecfdf5; }
  .cenario { border: 1px solid #e5e7eb; border-radius: 6px; padding: 8px 10px; margin: 6px 0; page-break-inside: avoid; }
  .pergunta { color: #444; font-weight: 600; margin-bottom: 4px; }
  .resposta { white-space: pre-wrap; background: #f8f8f8; padding: 6px 8px; border-radius: 4px; }
  .ind { color: #666; font-size: 10px; margin-top: 4px; }
  .erro { color: #b91c1c; background: #fef2f2; padding: 6px 8px; border-radius: 4px; }
  .badge { display: inline-block; background: #eef; border: 1px solid #ccd; border-radius: 4px; padding: 0 4px; font-size: 10px; margin-right: 3px; }
  .vaz { background: #fee; border-color: #fcc; color: #b91c1c; }
  h2 { font-size: 13px; margin: 18px 0 6px; border-bottom: 1px solid #eee; padding-bottom: 3px; }
  .u { text-align: right; margin: 8px 0 2px; }
  .u span { background: #eef2ff; border-radius: 8px; padding: 3px 8px; font-size: 11px; }
  @media print { body { margin: 12mm; } }
</style></head><body>
<h1>${esc(titulo)}</h1>
<div class="meta">Chat Nexus · Módulo de Teste de Agente · gerado em ${esc(dataHora)}</div>
${corpoHtml}
<script>window.onload = function(){ setTimeout(function(){ window.print(); }, 150); };</script>
</body></html>`);
  w.document.close();
}

function indHtml(r: TestarAgenteResult): string {
  const tools = (r.tools_chamadas || []).map((t) => `<span class="badge">${esc(t)}</span>`).join("");
  const vaz = r.raciocinio_vazado ? `<span class="badge vaz">vazou raciocínio</span>` : "";
  return `<div class="ind">${tools}${vaz} ${esc(fmtMetricas(r))}</div>`;
}

function fmtCusto(u: number | null | undefined): string {
  if (u == null) return "—";
  if (u === 0) return "$0";
  return u < 0.01 ? `$${u.toFixed(5)}` : `$${u.toFixed(4)}`;
}

// Linha de métricas da resposta — texto limpo, sem ícones. Usada no chat,
// no detalhe da bateria e na exportação em PDF (mesma string nos 3).
function fmtMetricas(r: TestarAgenteResult): string {
  const tempo =
    r.duracao_ms >= 1000
      ? `${(r.duracao_ms / 1000).toFixed(1)} s`
      : `${r.duracao_ms} ms`;
  const tok = (r.tokens_in || 0) + (r.tokens_out || 0);
  const linhas = `${r.linhas} ${r.linhas === 1 ? "linha" : "linhas"}`;
  return `${tempo} · ${tok} tok · ${linhas} · ${fmtCusto(r.custo_usd)}`;
}

function IndicadoresResposta({ r }: { r: TestarAgenteResult }) {
  return (
    <div className="mt-1 flex flex-wrap items-center gap-1">
      {r.tools_chamadas.map((t) => (
        <Badge key={t} variant="outline" className="text-[10px]">
          {t}
        </Badge>
      ))}
      {r.raciocinio_vazado && (
        <Badge variant="outline" className="text-[10px] text-destructive border-destructive/50">
          vazou raciocínio
        </Badge>
      )}
      <span className="font-mono text-[10px] text-muted-foreground">
        {fmtMetricas(r)}
      </span>
    </div>
  );
}

function DetalheBateria({
  linhas,
}: {
  linhas: (TestarAgenteResult & { modelo: string; cenario: string })[];
}) {
  return (
    <div className="space-y-2">
      <p className="text-xs font-medium text-muted-foreground">
        {linhas.length} cenários testados — pergunta → resposta do agente:
      </p>
      {linhas.map((l, i) => {
        const falhou = "erro" in l && (l as unknown as { erro?: string }).erro;
        return (
          <div key={i} className="rounded-md border bg-background/60 p-2 text-sm">
            <p className="mb-1 text-xs font-medium text-muted-foreground">
              {i + 1}. Cliente: <span className="text-foreground">{l.cenario}</span>
            </p>
            {falhou ? (
              <p className="rounded bg-destructive/10 px-2 py-1 text-xs text-destructive">
                {(l as unknown as { erro: string }).erro}
              </p>
            ) : (
              <>
                <p className="whitespace-pre-wrap rounded bg-secondary px-2 py-1">
                  {l.resposta || "(vazio)"}
                </p>
                <div className="mt-1 flex flex-wrap items-center gap-1">
                  {l.tools_chamadas?.map((t) => (
                    <Badge key={t} variant="outline" className="text-[10px]">
                      {t}
                    </Badge>
                  ))}
                  {l.raciocinio_vazado && (
                    <Badge
                      variant="outline"
                      className="text-[10px] text-destructive border-destructive/50"
                    >
                      vazou raciocínio
                    </Badge>
                  )}
                  <span className="font-mono text-[10px] text-muted-foreground">
                    {fmtMetricas(l)}
                  </span>
                </div>
              </>
            )}
          </div>
        );
      })}
    </div>
  );
}

function BolhaAgente({ res }: { res?: TestarAgenteResult | { erro: string } }) {
  if (!res) return null;
  if ("erro" in res) {
    return <div className="rounded-2xl bg-destructive/10 px-3 py-2 text-sm text-destructive">{res.erro}</div>;
  }
  return (
    <div className="rounded-2xl bg-secondary px-3 py-2 text-sm whitespace-pre-wrap">
      {res.resposta || "(vazio)"}
      <IndicadoresResposta r={res} />
    </div>
  );
}

function TabTestar({
  slug,
  modeloAtual,
  modelos,
}: {
  slug: string;
  modeloAtual: string | null;
  modelos: ModeloLLM[];
}) {
  const primeiro = modelos[0] ? `${modelos[0].provedor}/${modelos[0].nome}` : "";
  const segundo = modelos[1] ? `${modelos[1].provedor}/${modelos[1].nome}` : "";
  const [comparar, setComparar] = React.useState(false);
  // Modelos selecionados p/ comparação (2 a 4). Alinhado com LETTERS (A/B/C/D).
  const [modelosSel, setModelosSel] = React.useState<string[]>(
    [modeloAtual ?? primeiro, segundo].filter(Boolean)
  );
  const [msgs, setMsgs] = React.useState<MsgTeste[]>([]);
  const [texto, setTexto] = React.useState("");
  const [enviando, setEnviando] = React.useState(false);
  const [erro, setErro] = React.useState<string | null>(null);
  const [placar, setPlacar] = React.useState<BateriaPlacar[] | null>(null);
  // Versão do prompt em que o placar ficou gravado (mig 159). null depois de
  // uma bateria = a gravação falhou; o placar vale, só não ficou registrado.
  const [versaoGravada, setVersaoGravada] = React.useState<number | null>(null);
  const [resultadosBat, setResultadosBat] =
    React.useState<TestarBateriaResult["resultados"] | null>(null);
  const [detalheModelo, setDetalheModelo] = React.useState<string | null>(null);
  const [rodandoBateria, setRodandoBateria] = React.useState(false);
  const [midia, setMidia] = React.useState<MidiaTeste | null>(null);
  const fimRef = React.useRef<HTMLDivElement | null>(null);
  const fileRef = React.useRef<HTMLInputElement | null>(null);

  async function onArquivo(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    e.target.value = ""; // permite re-selecionar o mesmo arquivo
    if (!f) return;
    const MAX = 8 * 1024 * 1024; // 8 MB
    if (f.size > MAX) {
      setErro("Arquivo muito grande (máximo 8 MB).");
      return;
    }
    setErro(null);
    try {
      const base64 = await lerArquivoBase64(f);
      setMidia({
        base64,
        tipo: f.type || "application/octet-stream",
        nome: f.name,
      });
    } catch (err) {
      setErro(err instanceof Error ? err.message : "Falha ao ler o arquivo.");
    }
  }

  React.useEffect(() => {
    fimRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [msgs, enviando]);

  const opcoes = modelos.map((m) => ({ v: `${m.provedor}/${m.nome}`, l: `${m.nome}` }));
  const LETTERS = ["A", "B", "C", "D"];

  const rotuloModelo = (modelo: string | null, idx: number) =>
    modelo ? `${LETTERS[idx] ?? idx + 1} · ${modelo.split("/").pop()}` : "Assistente";

  function proximoLivre(atual: string[]): string {
    const usados = new Set(atual);
    return opcoes.find((o) => !usados.has(o.v))?.v ?? "";
  }
  function addSlot() {
    setModelosSel((s) => {
      if (s.length >= 4) return s;
      const novo = proximoLivre(s);
      return novo ? [...s, novo] : s;
    });
  }
  function removeSlot(i: number) {
    setModelosSel((s) => (s.length > 2 ? s.filter((_, idx) => idx !== i) : s));
  }
  function setSlot(i: number, v: string) {
    setModelosSel((s) => s.map((x, idx) => (idx === i ? v : x)));
  }
  // Valida a seleção de comparação: 2 a 4 modelos, todos distintos.
  function validarSelecao(): string | null {
    const ativos = modelosSel.filter(Boolean);
    if (ativos.length < 2) return "Selecione pelo menos 2 modelos para comparar.";
    if (new Set(ativos).size !== ativos.length)
      return "Há modelos repetidos — escolha modelos diferentes.";
    return null;
  }

  function exportarConversa() {
    if (msgs.length === 0) return;
    const corpo = msgs
      .map((m) => {
        if (m.role === "user") {
          const anexo = m.midia
            ? ` <span style="opacity:.7">[anexo: ${esc(m.midia.nome)} · ${esc(tipoMidiaLabel(m.midia.tipo))}]</span>`
            : "";
          return `<div class="u"><span>Cliente: ${esc(m.texto || "(mídia)")}${anexo}</span></div>`;
        }
        const bolha = (res: Resposta | undefined, rot: string) => {
          if (!res) return "";
          if ("erro" in res)
            return `<div class="cenario"><div class="pergunta">${esc(rot)}</div><div class="erro">${esc(res.erro)}</div></div>`;
          return `<div class="cenario"><div class="pergunta">${esc(rot)}</div><div class="resposta">${esc(res.resposta || "(vazio)")}</div>${indHtml(res)}</div>`;
        };
        if (m.respostas.length > 1) {
          const cols = m.respostas
            .map(
              (res, idx) =>
                `<div style="flex:1">${bolha(res, rotuloModelo(m.modelos[idx] ?? null, idx))}</div>`
            )
            .join("");
          return `<div style="display:flex;gap:8px">${cols}</div>`;
        }
        return bolha(m.respostas[0], "Assistente");
      })
      .join("");
    const nomes = comparar
      ? modelosSel.map((x) => x.split("/").pop()).join(" vs ")
      : null;
    const titulo = nomes
      ? `Teste comparativo — ${slug} (${nomes})`
      : `Teste do agente — ${slug}`;
    abrirPdf(titulo, corpo);
  }

  function exportarBateria() {
    if (!placar || !resultadosBat) return;
    const tabela = `<h2>Placar comparativo</h2><table>
      <tr><th>Modelo</th><th>Erros</th><th>Vazamentos</th><th>Linhas (méd)</th><th>Escalou</th><th>Tempo (méd)</th><th>Custo total</th></tr>
      ${placar
        .map(
          (p) => `<tr class="${p.modelo === melhor ? "win" : ""}">
        <td>${esc(p.modelo.split("/").pop() || "")}${p.modelo === melhor ? " ★" : ""}</td>
        <td class="num">${p.erros}</td><td class="num">${p.vazamentos}</td>
        <td class="num">${p.linhas_media}</td><td class="num">${p.turnos_com_tools}</td>
        <td class="num">${(p.tempo_medio_ms / 1000).toFixed(1)}s</td>
        <td class="num">${fmtCusto(p.custo_total_usd)}</td></tr>`
        )
        .join("")}
    </table>`;
    const detalhes = placar
      .map((p) => {
        const linhas = resultadosBat.filter((r) => r.modelo === p.modelo);
        const cen = linhas
          .map((l, i) => {
            const falhou = "erro" in l && (l as unknown as { erro?: string }).erro;
            const corpo = falhou
              ? `<div class="erro">${esc((l as unknown as { erro: string }).erro)}</div>`
              : `<div class="resposta">${esc(l.resposta || "(vazio)")}</div>${indHtml(l as TestarAgenteResult)}`;
            return `<div class="cenario"><div class="pergunta">${i + 1}. Cliente: ${esc(l.cenario)}</div>${corpo}</div>`;
          })
          .join("");
        return `<h2>${esc(p.modelo.split("/").pop() || "")} — ${linhas.length} cenários</h2>${cen}`;
      })
      .join("");
    abrirPdf(`Bateria de teste — ${slug}`, tabela + detalhes);
  }

  async function enviar() {
    const t = texto.trim();
    if ((!t && !midia) || enviando) return;
    if (comparar) {
      const v = validarSelecao();
      if (v) { setErro(v); return; }
    }
    setErro(null);
    const midiaAtual = midia;
    setTexto("");
    setMidia(null);
    setMsgs((m) => [...m, {
      role: "user",
      texto: t,
      midia: midiaAtual ? { nome: midiaAtual.nome, tipo: midiaAtual.tipo } : undefined,
    }]);
    setEnviando(true);
    const { testarAgenteAction } = await import("./actions");
    if (comparar) {
      const usados = [...modelosSel];
      const rs = await Promise.all(
        usados.map((mm) => testarAgenteAction(slug, t, mm || null, midiaAtual))
      );
      setMsgs((m) => [...m, {
        role: "agente",
        respostas: rs.map((r) => (r.ok ? r.data : { erro: r.error })),
        modelos: usados,
      }]);
    } else {
      const r = await testarAgenteAction(slug, t, null, midiaAtual);
      setMsgs((m) => [...m, {
        role: "agente",
        respostas: [r.ok ? r.data : { erro: r.error }],
        modelos: [null],
      }]);
    }
    setEnviando(false);
  }

  async function reiniciar() {
    if (msgs.length && !confirm("Reiniciar a conversa de teste? A memória desta sessão será apagada.")) return;
    setMidia(null);
    const { resetarTesteAgenteAction } = await import("./actions");
    if (comparar) {
      await Promise.all(
        modelosSel.map((mm) => resetarTesteAgenteAction(slug, mm || null))
      );
    } else {
      await resetarTesteAgenteAction(slug, null);
    }
    setMsgs([]);
    setErro(null);
    setPlacar(null);
  }

  async function rodarBateria() {
    const v = validarSelecao();
    if (v) { setErro(v); return; }
    setErro(null);
    setRodandoBateria(true);
    setPlacar(null);
    const { testarBateriaAction } = await import("./actions");
    const r = await testarBateriaAction(slug, modelosSel);
    setRodandoBateria(false);
    if (r.ok) {
      setPlacar(r.data.placar);
      setResultadosBat(r.data.resultados);
      setDetalheModelo(null);
      setVersaoGravada(r.data.versao_prompt);
    } else setErro(r.error);
  }

  const melhor = placar
    ? [...placar].filter((p) => p.erros < p.turnos).sort(
        (x, y) =>
          x.erros - y.erros ||
          x.vazamentos - y.vazamentos ||
          x.linhas_media - y.linhas_media
      )[0]?.modelo
    : null;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">
          Ambiente de teste — nada é enviado ao WhatsApp nem toca clientes
          reais. Salve as alterações do agente antes de testar.
        </p>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1 text-xs">
            <input type="checkbox" checked={comparar} onChange={(e) => { setComparar(e.target.checked); setMsgs([]); setPlacar(null); }} />
            Comparar modelos (até 4)
          </label>
          {msgs.length > 0 && (
            <Button type="button" variant="outline" size="sm" onClick={exportarConversa}>
              <FileDown className="size-3.5" />
              Exportar PDF
            </Button>
          )}
          <Button type="button" variant="outline" size="sm" onClick={reiniciar}>
            <RotateCcw className="size-3.5" />
            Reiniciar
          </Button>
        </div>
      </div>

      {comparar && (
        <div className="space-y-3 rounded-lg border bg-muted/20 p-3">
          <div className="flex flex-wrap items-end gap-3">
            {modelosSel.map((mv, idx) => (
              <div key={idx} className="flex flex-col gap-1">
                <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
                  Modelo {LETTERS[idx] ?? idx + 1}
                </span>
                <div className="flex items-center gap-1">
                  <select
                    value={mv}
                    onChange={(e) => setSlot(idx, e.target.value)}
                    className="h-8 rounded-md border border-border/40 bg-background px-2 text-sm"
                  >
                    {opcoes.map((o) => <option key={o.v} value={o.v}>{o.l}</option>)}
                  </select>
                  {modelosSel.length > 2 && (
                    <button
                      type="button"
                      onClick={() => removeSlot(idx)}
                      title="Remover modelo"
                      className="flex size-7 items-center justify-center rounded-md text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                    >
                      <X className="size-3.5" />
                    </button>
                  )}
                </div>
              </div>
            ))}
            {modelosSel.length < 4 && opcoes.length > modelosSel.length && (
              <Button type="button" variant="outline" size="sm" onClick={addSlot}>
                <Plus className="size-3.5" />
                Modelo
              </Button>
            )}
          </div>
          <Button type="button" variant="outline" size="sm" onClick={rodarBateria} disabled={rodandoBateria}>
            {rodandoBateria ? <Loader2 className="size-3.5 animate-spin" /> : <FlaskConical className="size-3.5" />}
            {rodandoBateria
              ? "Rodando bateria…"
              : `Rodar bateria (${modelosSel.length} modelos × 12 cenários)`}
          </Button>
        </div>
      )}

      {placar && (
        <p className="text-[11px] text-muted-foreground">
          {versaoGravada
            ? `Resultado gravado na versão v${versaoGravada} do prompt — aparece no Histórico da aba Prompt.`
            : "O resultado não pôde ser gravado no histórico do prompt. O placar abaixo vale mesmo assim."}
        </p>
      )}

      {placar && (
        <div className="overflow-hidden rounded-lg border">
          <table className="w-full text-sm">
            <thead className="bg-muted/40 text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="px-3 py-2 text-left">Modelo</th>
                <th className="px-3 py-2 text-right">Erros</th>
                <th className="px-3 py-2 text-right">Vazamentos</th>
                <th className="px-3 py-2 text-right">Linhas (méd)</th>
                <th className="px-3 py-2 text-right">Escalou</th>
                <th className="px-3 py-2 text-right">Tempo (méd)</th>
                <th className="px-3 py-2 text-right">Custo total</th>
              </tr>
            </thead>
            <tbody>
              {placar.map((p) => (
                <React.Fragment key={p.modelo}>
                <tr
                  className={
                    "cursor-pointer border-t hover:bg-muted/30 " +
                    (p.modelo === melhor ? "bg-emerald-500/10" : "")
                  }
                  onClick={() => setDetalheModelo(detalheModelo === p.modelo ? null : p.modelo)}
                  title="Clique para ver os 12 cenários deste modelo"
                >
                  <td className="px-3 py-2 font-medium">
                    <span className="mr-1 text-muted-foreground">{detalheModelo === p.modelo ? "▾" : "▸"}</span>
                    {p.modelo.split("/").pop()}
                    {p.modelo === melhor && <span className="ml-1 text-emerald-500">★ recomendado</span>}
                  </td>
                  <td className={"px-3 py-2 text-right " + (p.erros > 0 ? "text-destructive" : "")}>{p.erros}</td>
                  <td className={"px-3 py-2 text-right " + (p.vazamentos > 0 ? "text-destructive" : "")}>{p.vazamentos}</td>
                  <td className="px-3 py-2 text-right">{p.linhas_media}</td>
                  <td className="px-3 py-2 text-right">{p.turnos_com_tools}</td>
                  <td className="px-3 py-2 text-right font-mono text-xs">{(p.tempo_medio_ms / 1000).toFixed(1)}s</td>
                  <td className="px-3 py-2 text-right font-mono text-xs">{fmtCusto(p.custo_total_usd)}</td>
                </tr>
                {detalheModelo === p.modelo && resultadosBat && (
                  <tr>
                    <td colSpan={7} className="bg-muted/20 px-3 py-3">
                      <DetalheBateria
                        linhas={resultadosBat.filter((r) => r.modelo === p.modelo)}
                      />
                    </td>
                  </tr>
                )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
          <p className="border-t bg-muted/20 px-3 py-2 text-[11px] text-muted-foreground">
            Vencedor por menor vazamento de raciocínio, depois objetividade. Custo é dos {placar[0]?.turnos} cenários — no volume real, centavos/mês.
          </p>
          <div className="flex justify-end border-t bg-muted/10 px-3 py-2">
            <Button type="button" variant="outline" size="sm" onClick={exportarBateria}>
              <FileDown className="size-3.5" />
              Exportar bateria em PDF
            </Button>
          </div>
        </div>
      )}

      <div className="h-[380px] overflow-y-auto rounded-lg border bg-background/50 p-3 space-y-2">
        {msgs.length === 0 && !enviando && (
          <p className="py-10 text-center text-sm text-muted-foreground">
            Envie uma mensagem como se você fosse o cliente no WhatsApp — dá pra
            anexar áudio, documento (PDF/DOCX/TXT) ou imagem no clipe.
            {comparar && " No modo comparação, cada mensagem gera a resposta de todos os modelos lado a lado."}
          </p>
        )}
        {msgs.map((m, i) =>
          m.role === "user" ? (
            <div key={i} className="flex flex-col items-end gap-1">
              {m.midia && (
                <div className="flex items-center gap-1 rounded-full bg-primary/10 px-2 py-1 text-[11px] text-muted-foreground">
                  <Paperclip className="size-3" />
                  <span className="max-w-[220px] truncate">{m.midia.nome}</span>
                  <span className="opacity-70">· {tipoMidiaLabel(m.midia.tipo)}</span>
                </div>
              )}
              {m.texto && (
                <div className="max-w-[80%] rounded-2xl bg-primary/15 px-3 py-2 text-sm whitespace-pre-wrap">{m.texto}</div>
              )}
            </div>
          ) : m.respostas.length > 1 ? (
            <div
              key={i}
              className="grid gap-2"
              style={{ gridTemplateColumns: `repeat(${m.respostas.length}, minmax(0, 1fr))` }}
            >
              {m.respostas.map((res, idx) => (
                <div key={idx}>
                  <p className="mb-1 text-[10px] font-medium uppercase text-muted-foreground">
                    {rotuloModelo(m.modelos[idx] ?? null, idx)}
                  </p>
                  <BolhaAgente res={res} />
                </div>
              ))}
            </div>
          ) : (
            <div key={i} className="flex justify-start">
              <div className="max-w-[80%]"><BolhaAgente res={m.respostas[0]} /></div>
            </div>
          )
        )}
        {enviando && (
          <div className="flex justify-start">
            <div className="rounded-2xl bg-secondary px-3 py-2 text-sm text-muted-foreground">
              <Loader2 className="inline size-3.5 animate-spin" /> digitando…
            </div>
          </div>
        )}
        <div ref={fimRef} />
      </div>

      {erro && <p className="text-sm text-destructive">{erro}</p>}

      {midia && (
        <div className="flex items-center gap-2 rounded-md border bg-muted/30 px-2.5 py-1.5 text-xs">
          <Paperclip className="size-3.5 text-muted-foreground" />
          <span className="flex-1 truncate">{midia.nome}</span>
          <span className="shrink-0 rounded bg-muted px-1.5 py-0.5 text-[10px] text-muted-foreground">
            {tipoMidiaLabel(midia.tipo)}
          </span>
          <button
            type="button"
            onClick={() => setMidia(null)}
            title="Remover anexo"
            className="flex size-6 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
          >
            <X className="size-3.5" />
          </button>
        </div>
      )}

      <div className="flex gap-2">
        <input
          ref={fileRef}
          type="file"
          accept="audio/*,application/pdf,image/*,.doc,.docx,.txt,.md"
          className="hidden"
          onChange={(e) => void onArquivo(e)}
        />
        <Button
          type="button"
          variant="outline"
          size="icon"
          onClick={() => fileRef.current?.click()}
          disabled={enviando}
          title="Anexar áudio, documento ou imagem"
        >
          <Paperclip className="size-3.5" />
        </Button>
        <textarea
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void enviar(); }
          }}
          rows={2}
          placeholder="Digite como se fosse o cliente… (Enter envia, Shift+Enter quebra linha)"
          className="flex-1 resize-none rounded-md border border-foreground/10 bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-primary/30"
        />
        <Button type="button" onClick={() => void enviar()} disabled={enviando || (!texto.trim() && !midia)}>
          <Send className="size-3.5" />
          Enviar
        </Button>
      </div>
    </div>
  );
}
