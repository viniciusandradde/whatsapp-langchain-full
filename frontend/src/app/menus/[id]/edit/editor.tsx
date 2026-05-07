"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState, useTransition } from "react";
import {
  ArrowDown,
  ArrowLeft,
  ArrowUp,
  ChevronDown,
  ChevronRight,
  Eye,
  ListTree,
  Loader2,
  Plus,
  Save,
  Settings,
  Trash2,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type {
  AgenteIA,
  Departamento,
  Hook,
  MenuChatbot,
  MenuItem,
  MenuItemAcaoTipo,
} from "@/lib/api";

import {
  createItemAction,
  deleteItemAction,
  deleteMenuAction,
  reorderAction,
  seedFromAgentesAction,
  updateItemAction,
  updateMenuAction,
} from "./actions";

const inputCls =
  "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus-visible:ring-1 focus-visible:ring-ring";
const textareaCls =
  "flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm focus:outline-none focus-visible:ring-1 focus-visible:ring-ring";
const labelCls = "text-sm font-medium";
const helpCls = "text-xs text-muted-foreground";

const ACAO_LABELS: Record<MenuItemAcaoTipo, { label: string; descricao: string }> = {
  submenu: { label: "Submenu", descricao: "Apresenta novo nível de opções" },
  transferir_dep: {
    label: "Transferir departamento",
    descricao: "Atribui ao departamento e sai do menu",
  },
  chamar_agente: {
    label: "Chamar agente IA",
    descricao: "Atribui agente IA específico e sai do menu",
  },
  enviar_msg: {
    label: "Enviar mensagem",
    descricao: "Envia texto livre, opcional volta ao menu",
  },
  fechar: { label: "Fechar atendimento", descricao: "Encerra como resolvido" },
  transferir_atendente: {
    label: "Transferir atendente",
    descricao: "Atribui a operador específico (Better Auth user ID)",
  },
  enviar_template: {
    label: "Enviar template",
    descricao: "Dispara template de modelo_mensagem cadastrado",
  },
  chamar_webhook: {
    label: "Chamar webhook",
    descricao: "POST async pra URL externa, msg confirmação ao cliente",
  },
  enviar_link: {
    label: "Enviar link",
    descricao: "Envia URL/link com texto opcional",
  },
  pesquisa_csat: {
    label: "Pesquisa CSAT",
    descricao: "Envia pergunta + escala de notas",
  },
  mudar_manual: {
    label: "Mudar pra manual",
    descricao: "Sai do menu, libera pra atendentes humanos",
  },
  setar_nome: {
    label: "Pedir nome",
    descricao: "Pergunta nome do cliente (captura via agente IA)",
  },
};

// =====================================================================
// Tree builder
// =====================================================================

interface ItemNode {
  item: MenuItem;
  children: ItemNode[];
}

function buildTree(items: MenuItem[]): ItemNode[] {
  const byParent = new Map<number | null, MenuItem[]>();
  for (const it of items) {
    const k = it.parent_id ?? null;
    if (!byParent.has(k)) byParent.set(k, []);
    byParent.get(k)!.push(it);
  }
  for (const arr of byParent.values()) arr.sort((a, b) => a.ordem - b.ordem);

  function buildLevel(parentId: number | null): ItemNode[] {
    return (byParent.get(parentId) || []).map((it) => ({
      item: it,
      children: buildLevel(it.id),
    }));
  }
  return buildLevel(null);
}

// =====================================================================
// Editor principal
// =====================================================================

export function MenuEditor({
  menu: initialMenu,
  items: initialItems,
  agentes,
  departamentos,
  hooks,
}: {
  menu: MenuChatbot;
  items: MenuItem[];
  agentes: AgenteIA[];
  departamentos: Departamento[];
  hooks: Hook[];
}) {
  const router = useRouter();
  const [tab, setTab] = useState<"identidade" | "arvore" | "preview" | "config">(
    "arvore"
  );
  const [menu, setMenu] = useState(initialMenu);
  const [items, setItems] = useState(initialItems);
  const [selectedItemId, setSelectedItemId] = useState<number | null>(null);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [_, startTransition] = useTransition();
  const [savingMenu, setSavingMenu] = useState(false);
  const [savingItem, setSavingItem] = useState(false);

  // Sincroniza state local quando server-side revalida e props mudam
  // (initialMenu/initialItems vêm como nova referência após router.refresh()).
  useEffect(() => {
    setMenu(initialMenu);
  }, [initialMenu]);
  useEffect(() => {
    setItems(initialItems);
  }, [initialItems]);

  const tree = useMemo(() => buildTree(items), [items]);
  const selectedItem = items.find((i) => i.id === selectedItemId) || null;

  const refreshFromServer = () => {
    router.refresh();
  };

  // Remove item local imediatamente (UX) — server revalida em paralelo.
  // Sem isso o item só sumia depois do refresh completar a viagem ao servidor.
  const removeItemOptimistic = (itemId: number) => {
    const collectDescendants = (id: number, all: MenuItem[]): number[] => {
      const direct = all.filter((i) => i.parent_id === id);
      const result = [id];
      for (const c of direct) {
        result.push(...collectDescendants(c.id, all));
      }
      return result;
    };
    setItems((prev) => {
      const toRemove = new Set(collectDescendants(itemId, prev));
      return prev.filter((i) => !toRemove.has(i.id));
    });
    if (selectedItemId === itemId) setSelectedItemId(null);
  };

  return (
    <div className="space-y-6">
      <Link
        href="/menus"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" />
        Voltar
      </Link>

      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10">
            <ListTree className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold">{menu.nome}</h1>
            <p className="mt-0.5 text-sm text-muted-foreground">
              Menu chatbot árvore — {items.length} item
              {items.length === 1 ? "" : "s"}
              {menu.menu_moderno && " · modo moderno"}
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <Badge variant={menu.ativo ? "outline" : "secondary"}>
            {menu.ativo ? "ativo" : "inativo"}
          </Badge>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b">
        <nav className="flex gap-1">
          {(
            [
              { id: "arvore", label: "Árvore", icon: ListTree },
              { id: "identidade", label: "Identidade", icon: Settings },
              { id: "config", label: "Avançado (B+)", icon: Settings },
              { id: "preview", label: "Preview", icon: Eye },
            ] as const
          ).map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`inline-flex items-center gap-1.5 rounded-t-md border-b-2 px-3 py-2 text-sm transition-colors ${
                tab === t.id
                  ? "border-primary text-foreground"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              <t.icon className="size-3.5" />
              {t.label}
            </button>
          ))}
        </nav>
      </div>

      {/* Identidade */}
      {tab === "identidade" && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">Identidade do menu</CardTitle>
          </CardHeader>
          <CardContent>
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                setSavingMenu(true);
                const fd = new FormData(e.currentTarget);
                const res = await updateMenuAction(menu.id, {
                  nome: String(fd.get("nome") || ""),
                  mensagem_boas_vindas: String(fd.get("mensagem_boas_vindas") || ""),
                  mensagem_opcao_invalida: String(fd.get("mensagem_opcao_invalida") || ""),
                  trigger_keywords: String(fd.get("trigger_keywords") || "")
                    .split(",")
                    .map((s) => s.trim().toLowerCase())
                    .filter(Boolean),
                  ativo: fd.get("ativo") === "on",
                });
                setSavingMenu(false);
                if (res.ok) {
                  setMenu((m) => ({ ...m, nome: String(fd.get("nome") || m.nome) }));
                  refreshFromServer();
                } else {
                  alert(res.error);
                }
              }}
              className="space-y-4"
            >
              <div className="space-y-2">
                <label className={labelCls}>Nome interno</label>
                <input
                  name="nome"
                  defaultValue={menu.nome}
                  required
                  maxLength={120}
                  className={inputCls}
                />
              </div>
              <div className="space-y-2">
                <label className={labelCls}>Boas-vindas</label>
                <textarea
                  name="mensagem_boas_vindas"
                  defaultValue={menu.mensagem_boas_vindas}
                  required
                  maxLength={4000}
                  rows={4}
                  className={textareaCls}
                />
              </div>
              <div className="space-y-2">
                <label className={labelCls}>Mensagem de opção inválida</label>
                <textarea
                  name="mensagem_opcao_invalida"
                  defaultValue={menu.mensagem_opcao_invalida}
                  maxLength={2000}
                  rows={2}
                  className={textareaCls}
                />
              </div>
              <div className="space-y-2">
                <label className={labelCls}>Palavras-chave de retorno</label>
                <input
                  name="trigger_keywords"
                  defaultValue={menu.trigger_keywords.join(", ")}
                  className={inputCls}
                />
                <p className={helpCls}>Separadas por vírgula.</p>
              </div>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  name="ativo"
                  defaultChecked={menu.ativo}
                  className="size-4"
                />
                Menu ativo (worker usa esse menu)
              </label>
              <div className="flex justify-end gap-2">
                <Button
                  type="button"
                  variant="destructive"
                  onClick={() => {
                    if (confirm(`Deletar o menu "${menu.nome}"?`)) {
                      deleteMenuAction(menu.id);
                    }
                  }}
                >
                  <Trash2 className="size-4" />
                  Deletar menu
                </Button>
                <Button type="submit" disabled={savingMenu}>
                  {savingMenu ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
                  Salvar
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {/* Config B+ (paridade ZigChat) */}
      {tab === "config" && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">
              Avançado — Sub-fase B+ (paridade ZigChat)
            </CardTitle>
          </CardHeader>
          <CardContent>
            <form
              onSubmit={async (e) => {
                e.preventDefault();
                setSavingMenu(true);
                const fd = new FormData(e.currentTarget);
                const res = await updateMenuAction(menu.id, {
                  atalho: String(fd.get("atalho") || "") || null,
                  solicitar_nome: fd.get("solicitar_nome") === "on",
                  menu_moderno: fd.get("menu_moderno") === "on",
                  resposta_confidencial: fd.get("resposta_confidencial") === "on",
                  arquivo_url: String(fd.get("arquivo_url") || "") || null,
                  mensagem_coleta: String(fd.get("mensagem_coleta") || "") || null,
                  mensagem_confirmar_coleta:
                    String(fd.get("mensagem_confirmar_coleta") || "") || null,
                  mensagem_final_coleta:
                    String(fd.get("mensagem_final_coleta") || "") || null,
                });
                setSavingMenu(false);
                if (res.ok) refreshFromServer();
                else alert(res.error);
              }}
              className="space-y-4"
            >
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <label className={labelCls}>Atalho (alternativa singular)</label>
                  <input
                    name="atalho"
                    defaultValue={menu.atalho || ""}
                    placeholder="Ex: /start"
                    className={inputCls}
                  />
                </div>
                <div className="space-y-2">
                  <label className={labelCls}>URL do arquivo (anexo boas-vindas)</label>
                  <input
                    name="arquivo_url"
                    defaultValue={menu.arquivo_url || ""}
                    placeholder="https://..."
                    className={inputCls}
                  />
                </div>
              </div>

              <div className="grid gap-3 sm:grid-cols-3">
                <label className="flex items-start gap-2 text-sm">
                  <input
                    type="checkbox"
                    name="solicitar_nome"
                    defaultChecked={menu.solicitar_nome}
                    className="mt-0.5 size-4"
                  />
                  <span>
                    <span className="font-medium">Solicitar nome</span>
                    <span className={`block ${helpCls}`}>
                      Pergunta o nome do cliente antes do menu
                    </span>
                  </span>
                </label>
                <label className="flex items-start gap-2 text-sm">
                  <input
                    type="checkbox"
                    name="menu_moderno"
                    defaultChecked={menu.menu_moderno}
                    className="mt-0.5 size-4"
                  />
                  <span>
                    <span className="font-medium">Menu moderno</span>
                    <span className={`block ${helpCls}`}>
                      Botões nativos WhatsApp (vs &quot;1, 2, 3&quot;)
                    </span>
                  </span>
                </label>
                <label className="flex items-start gap-2 text-sm">
                  <input
                    type="checkbox"
                    name="resposta_confidencial"
                    defaultChecked={menu.resposta_confidencial}
                    className="mt-0.5 size-4"
                  />
                  <span>
                    <span className="font-medium">Confidencial</span>
                    <span className={`block ${helpCls}`}>
                      Mascarar conteúdo em logs
                    </span>
                  </span>
                </label>
              </div>

              <div className="space-y-3 rounded-md border bg-muted/20 p-3">
                <p className="text-xs font-semibold uppercase tracking-wide">
                  Wizard de coleta (3 passos)
                </p>
                <p className={helpCls}>
                  Quando ativo via &ldquo;Solicitar nome&rdquo; ou ação{" "}
                  <code>setar_nome</code>, esses textos guiam o cliente.
                </p>
                <div className="space-y-2">
                  <label className={labelCls}>1. Pergunta de coleta</label>
                  <textarea
                    name="mensagem_coleta"
                    defaultValue={menu.mensagem_coleta || ""}
                    rows={2}
                    placeholder="Ex: Pra começar, qual seu nome?"
                    className={textareaCls}
                  />
                </div>
                <div className="space-y-2">
                  <label className={labelCls}>2. Confirmação</label>
                  <textarea
                    name="mensagem_confirmar_coleta"
                    defaultValue={menu.mensagem_confirmar_coleta || ""}
                    rows={2}
                    placeholder="Ex: Confirma seu nome como {nome}?"
                    className={textareaCls}
                  />
                </div>
                <div className="space-y-2">
                  <label className={labelCls}>3. Mensagem final</label>
                  <textarea
                    name="mensagem_final_coleta"
                    defaultValue={menu.mensagem_final_coleta || ""}
                    rows={2}
                    placeholder="Ex: Obrigado, {nome}! Vamos começar."
                    className={textareaCls}
                  />
                </div>
              </div>

              <div className="flex justify-end">
                <Button type="submit" disabled={savingMenu}>
                  {savingMenu ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
                  Salvar avançado
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {/* Árvore */}
      {tab === "arvore" && (
        <div className="grid gap-4 lg:grid-cols-[1fr,1.2fr]">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between gap-2">
              <CardTitle className="text-base">Estrutura</CardTitle>
              <Button
                size="sm"
                variant="outline"
                onClick={async () => {
                  const res = await createItemAction(menu.id, {
                    label: "Nova opção",
                    acao_tipo: "enviar_msg",
                    acao_payload: { texto: "Resposta padrão", voltar_menu: true },
                    parent_id: null,
                  });
                  if (res.ok && res.id) {
                    setSelectedItemId(res.id);
                    refreshFromServer();
                  } else {
                    alert(res.error);
                  }
                }}
              >
                <Plus className="size-4" />
                Adicionar raiz
              </Button>
            </CardHeader>
            <CardContent>
              {tree.length === 0 ? (
                <SeedFromAgentesEmptyState
                  menuId={menu.id}
                  agentes={agentes}
                  onSeeded={refreshFromServer}
                />
              ) : (
                <ul className="space-y-1">
                  {tree.map((node, idx) => (
                    <TreeNode
                      key={node.item.id}
                      node={node}
                      level={0}
                      siblings={tree}
                      siblingIdx={idx}
                      menuId={menu.id}
                      selectedId={selectedItemId}
                      onSelect={setSelectedItemId}
                      expanded={expanded}
                      setExpanded={setExpanded}
                      onChange={refreshFromServer}
                      onLocalDelete={removeItemOptimistic}
                    />
                  ))}
                </ul>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">
                {selectedItem ? `Editar: ${selectedItem.label}` : "Selecione um item"}
              </CardTitle>
            </CardHeader>
            <CardContent>
              {selectedItem ? (
                <ItemForm
                  key={selectedItem.id}
                  item={selectedItem}
                  menuId={menu.id}
                  agentes={agentes}
                  departamentos={departamentos}
                  hooks={hooks}
                  saving={savingItem}
                  setSaving={setSavingItem}
                  onChange={refreshFromServer}
                  onSelect={setSelectedItemId}
                />
              ) : (
                <p className="py-8 text-center text-sm text-muted-foreground">
                  Clique em um item da árvore pra editar suas propriedades.
                </p>
              )}
            </CardContent>
          </Card>
        </div>
      )}

      {/* Preview */}
      {tab === "preview" && <PreviewWhatsApp menu={menu} items={items} />}
    </div>
  );
}

// =====================================================================
// Tree node recursivo
// =====================================================================

function TreeNode({
  node,
  level,
  siblings,
  siblingIdx,
  menuId,
  selectedId,
  onSelect,
  expanded,
  setExpanded,
  onChange,
  onLocalDelete,
}: {
  node: ItemNode;
  level: number;
  siblings: ItemNode[];
  siblingIdx: number;
  menuId: number;
  selectedId: number | null;
  onSelect: (id: number) => void;
  expanded: Set<number>;
  setExpanded: (s: Set<number>) => void;
  onChange: () => void;
  onLocalDelete: (id: number) => void;
}) {
  const isSelected = selectedId === node.item.id;
  const isExpanded = expanded.has(node.item.id);
  const hasChildren = node.children.length > 0;
  const acaoMeta = ACAO_LABELS[node.item.acao_tipo];

  return (
    <li>
      <div
        className={`flex items-center gap-1 rounded px-2 py-1.5 text-sm transition-colors ${
          isSelected ? "bg-primary/10" : "hover:bg-muted/50"
        }`}
        style={{ paddingLeft: `${level * 16 + 8}px` }}
      >
        <button
          type="button"
          onClick={() => {
            if (!hasChildren) return;
            const next = new Set(expanded);
            if (isExpanded) next.delete(node.item.id);
            else next.add(node.item.id);
            setExpanded(next);
          }}
          className={`flex size-5 items-center justify-center rounded hover:bg-muted ${
            !hasChildren ? "invisible" : ""
          }`}
        >
          {isExpanded ? <ChevronDown className="size-3" /> : <ChevronRight className="size-3" />}
        </button>
        <button
          type="button"
          onClick={() => onSelect(node.item.id)}
          className="flex flex-1 items-center gap-2 truncate text-left"
        >
          <span className="text-xs text-muted-foreground">{node.item.ordem}.</span>
          <span className={!node.item.ativo ? "text-muted-foreground line-through" : ""}>
            {node.item.label}
          </span>
          <Badge variant="outline" className="ml-auto text-[10px]">
            {acaoMeta?.label || node.item.acao_tipo}
          </Badge>
        </button>
        <div className="flex shrink-0 gap-0.5">
          <button
            type="button"
            disabled={siblingIdx === 0}
            onClick={async () => {
              const ids = siblings.map((s) => s.item.id);
              [ids[siblingIdx - 1], ids[siblingIdx]] = [ids[siblingIdx], ids[siblingIdx - 1]];
              const res = await reorderAction(menuId, node.item.parent_id, ids);
              if (res.ok) onChange();
              else alert(res.error);
            }}
            className="rounded p-0.5 hover:bg-muted disabled:opacity-30"
            title="Mover pra cima"
          >
            <ArrowUp className="size-3" />
          </button>
          <button
            type="button"
            disabled={siblingIdx === siblings.length - 1}
            onClick={async () => {
              const ids = siblings.map((s) => s.item.id);
              [ids[siblingIdx + 1], ids[siblingIdx]] = [ids[siblingIdx], ids[siblingIdx + 1]];
              const res = await reorderAction(menuId, node.item.parent_id, ids);
              if (res.ok) onChange();
              else alert(res.error);
            }}
            className="rounded p-0.5 hover:bg-muted disabled:opacity-30"
            title="Mover pra baixo"
          >
            <ArrowDown className="size-3" />
          </button>
          <button
            type="button"
            onClick={async () => {
              const res = await createItemAction(menuId, {
                label: "Nova opção",
                acao_tipo: "enviar_msg",
                acao_payload: { texto: "Resposta padrão", voltar_menu: true },
                parent_id: node.item.id,
              });
              if (res.ok && res.id) {
                const next = new Set(expanded);
                next.add(node.item.id);
                setExpanded(next);
                onSelect(res.id);
                onChange();
              } else {
                alert(res.error);
              }
            }}
            className="rounded p-0.5 hover:bg-muted"
            title="Adicionar filho"
          >
            <Plus className="size-3" />
          </button>
          <button
            type="button"
            onClick={async () => {
              if (!confirm(`Deletar "${node.item.label}" e todos os filhos?`)) return;
              const res = await deleteItemAction(menuId, node.item.id);
              if (res.ok) {
                onLocalDelete(node.item.id);
                onChange();
              } else {
                alert(res.error);
              }
            }}
            className="rounded p-0.5 text-destructive hover:bg-destructive/10"
            title="Deletar"
          >
            <Trash2 className="size-3" />
          </button>
        </div>
      </div>
      {hasChildren && isExpanded && (
        <ul className="space-y-1">
          {node.children.map((child, idx) => (
            <TreeNode
              key={child.item.id}
              node={child}
              level={level + 1}
              siblings={node.children}
              siblingIdx={idx}
              menuId={menuId}
              selectedId={selectedId}
              onSelect={onSelect}
              expanded={expanded}
              setExpanded={setExpanded}
              onChange={onChange}
              onLocalDelete={onLocalDelete}
            />
          ))}
        </ul>
      )}
    </li>
  );
}

// =====================================================================
// Item form (contextual por acao_tipo)
// =====================================================================

function ItemForm({
  item,
  menuId,
  agentes,
  departamentos,
  hooks,
  saving,
  setSaving,
  onChange,
  onSelect,
}: {
  item: MenuItem;
  menuId: number;
  agentes: AgenteIA[];
  departamentos: Departamento[];
  hooks: Hook[];
  saving: boolean;
  setSaving: (b: boolean) => void;
  onChange: () => void;
  onSelect: (id: number | null) => void;
}) {
  const [acao, setAcao] = useState<MenuItemAcaoTipo>(item.acao_tipo);
  const [payload, setPayload] = useState<Record<string, unknown>>(
    item.acao_payload || {}
  );

  return (
    <form
      onSubmit={async (e) => {
        e.preventDefault();
        setSaving(true);
        const fd = new FormData(e.currentTarget);
        const body: Parameters<typeof updateItemAction>[2] = {
          label: String(fd.get("label") || ""),
          acao_tipo: acao,
          acao_payload: payload,
          ativo: fd.get("ativo") === "on",
          comando: String(fd.get("comando") || "") || null,
          grupo: String(fd.get("grupo") || "") || null,
        };
        // Campos diretos (não-payload) usados quando aplicável
        if (acao === "transferir_atendente") {
          body.acao_atendente_id = String(fd.get("acao_atendente_id") || "") || null;
        }
        if (acao === "enviar_template") {
          const v = String(fd.get("acao_modelo_mensagem_id") || "");
          body.acao_modelo_mensagem_id = v ? Number(v) : null;
        }
        if (acao === "chamar_webhook") {
          body.webhook_url = String(fd.get("webhook_url") || "") || null;
          const hid = String(fd.get("hook_id") || "");
          body.hook_id = hid ? Number(hid) : null;
        }
        if (acao === "enviar_link") {
          body.link_url = String(fd.get("link_url") || "") || null;
        }
        if (acao === "pesquisa_csat") {
          const min = String(fd.get("nota_min") || "");
          const max = String(fd.get("nota_max") || "");
          body.nota_min = min ? Number(min) : null;
          body.nota_max = max ? Number(max) : null;
          body.nota_pergunta = String(fd.get("nota_pergunta") || "") || null;
        }
        const res = await updateItemAction(menuId, item.id, body);
        setSaving(false);
        if (res.ok) onChange();
        else alert(res.error);
      }}
      className="space-y-4"
    >
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="space-y-2 sm:col-span-2">
          <label className={labelCls}>Texto da opção *</label>
          <input
            name="label"
            defaultValue={item.label}
            required
            maxLength={200}
            className={inputCls}
          />
          <p className={helpCls}>
            Aparece pro cliente como &ldquo;{item.ordem}. {item.label}&rdquo;
          </p>
        </div>

        <div className="space-y-2">
          <label className={labelCls}>Tipo de ação *</label>
          <select
            value={acao}
            onChange={(e) => setAcao(e.target.value as MenuItemAcaoTipo)}
            className={inputCls}
          >
            {(Object.keys(ACAO_LABELS) as MenuItemAcaoTipo[]).map((a) => (
              <option key={a} value={a}>
                {ACAO_LABELS[a].label}
              </option>
            ))}
          </select>
          <p className={helpCls}>{ACAO_LABELS[acao]?.descricao}</p>
        </div>

        <div className="space-y-2">
          <label className={labelCls}>Comando (alias texto)</label>
          <input
            name="comando"
            defaultValue={item.comando || ""}
            placeholder='Ex: "vendas"'
            className={inputCls}
          />
          <p className={helpCls}>
            Cliente pode digitar isso em vez do número
          </p>
        </div>

        <div className="space-y-2 sm:col-span-2">
          <label className={labelCls}>Grupo (organização visual)</label>
          <input
            name="grupo"
            defaultValue={item.grupo || ""}
            placeholder='Ex: "Comercial"'
            className={inputCls}
          />
        </div>
      </div>

      {/* ---- Forms contextuais por acao_tipo ---- */}
      <div className="rounded-md border bg-muted/20 p-3 space-y-3">
        <p className="text-xs font-semibold uppercase tracking-wide">
          Configuração da ação
        </p>

        {acao === "submenu" && (
          <p className={helpCls}>
            Sem campos extras. Adicione filhos a esse item via árvore.
          </p>
        )}

        {acao === "transferir_dep" && (
          <DepartamentoSelect
            payload={payload}
            setPayload={setPayload}
            departamentos={departamentos}
          />
        )}

        {acao === "chamar_agente" && (
          <>
            <AgenteSelect
              payload={payload}
              setPayload={setPayload}
              agentes={agentes}
            />
            <PayloadField
              payload={payload}
              setPayload={setPayload}
              field="mensagem_pre"
              label="Mensagem antes (opcional)"
              type="textarea"
              help='Ex: "Vou te conectar com o time de vendas..."'
            />
          </>
        )}

        {acao === "enviar_msg" && (
          <>
            <PayloadField
              payload={payload}
              setPayload={setPayload}
              field="texto"
              label="Texto da resposta *"
              type="textarea"
              required
            />
            <PayloadCheckbox
              payload={payload}
              setPayload={setPayload}
              field="voltar_menu"
              label="Voltar pro menu raiz após enviar"
              defaultValue={true}
            />
          </>
        )}

        {acao === "fechar" && (
          <>
            <PayloadField
              payload={payload}
              setPayload={setPayload}
              field="mensagem_final"
              label="Mensagem final"
              type="textarea"
              help='Default: "Atendimento finalizado. Volte sempre!"'
            />
            <PayloadField
              payload={payload}
              setPayload={setPayload}
              field="motivo"
              label="Motivo (interno)"
              help="Para auditoria"
            />
          </>
        )}

        {acao === "transferir_atendente" && (
          <>
            <div className="space-y-1">
              <label className={labelCls}>User ID do atendente *</label>
              <input
                name="acao_atendente_id"
                defaultValue={item.acao_atendente_id || ""}
                placeholder="Better Auth user ID"
                className={inputCls}
              />
              <p className={helpCls}>
                ID do usuário no Better Auth (visível em /companies/[id]/members)
              </p>
            </div>
            <PayloadField
              payload={payload}
              setPayload={setPayload}
              field="mensagem_pre"
              label="Mensagem antes (opcional)"
              type="textarea"
            />
          </>
        )}

        {acao === "enviar_template" && (
          <>
            <div className="space-y-1">
              <label className={labelCls}>ID do modelo de mensagem *</label>
              <input
                name="acao_modelo_mensagem_id"
                type="number"
                defaultValue={item.acao_modelo_mensagem_id || ""}
                className={inputCls}
              />
              <p className={helpCls}>
                ID em /modelos. Conteúdo do template é enviado ao cliente.
              </p>
            </div>
            <PayloadCheckbox
              payload={payload}
              setPayload={setPayload}
              field="voltar_menu"
              label="Voltar pro menu raiz após enviar"
              defaultValue={true}
            />
          </>
        )}

        {acao === "chamar_webhook" && (
          <>
            <HookSelect item={item} hooks={hooks} />
            <div className="space-y-1">
              <label className={labelCls}>
                Ou URL livre (sem retry/DLQ)
              </label>
              <input
                name="webhook_url"
                type="url"
                defaultValue={item.webhook_url || ""}
                placeholder="https://api.exemplo.com/hook"
                className={inputCls}
              />
              <p className={helpCls}>
                Use só quando precisar de URL ad-hoc. Pra produção prefira hook
                cadastrado acima (ganha retry exponencial + DLQ).
              </p>
            </div>
            <PayloadField
              payload={payload}
              setPayload={setPayload}
              field="mensagem_pre"
              label="Mensagem ao cliente"
              help='Ex: "Ok, processando seu pedido..."'
            />
            <PayloadCheckbox
              payload={payload}
              setPayload={setPayload}
              field="voltar_menu"
              label="Voltar pro menu raiz após enviar"
              defaultValue={true}
            />
          </>
        )}

        {acao === "enviar_link" && (
          <>
            <div className="space-y-1">
              <label className={labelCls}>URL *</label>
              <input
                name="link_url"
                type="url"
                defaultValue={item.link_url || ""}
                placeholder="https://..."
                className={inputCls}
              />
            </div>
            <PayloadField
              payload={payload}
              setPayload={setPayload}
              field="texto_pre"
              label="Texto antes do link"
              help='Default: "Aqui está o link:"'
            />
            <PayloadCheckbox
              payload={payload}
              setPayload={setPayload}
              field="voltar_menu"
              label="Voltar pro menu raiz após enviar"
              defaultValue={true}
            />
          </>
        )}

        {acao === "pesquisa_csat" && (
          <>
            <div className="space-y-1">
              <label className={labelCls}>Pergunta *</label>
              <input
                name="nota_pergunta"
                defaultValue={item.nota_pergunta || ""}
                placeholder="Ex: Como você avalia o atendimento?"
                className={inputCls}
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <label className={labelCls}>Nota mínima</label>
                <input
                  name="nota_min"
                  type="number"
                  min={0}
                  max={10}
                  defaultValue={item.nota_min ?? 1}
                  className={inputCls}
                />
              </div>
              <div className="space-y-1">
                <label className={labelCls}>Nota máxima</label>
                <input
                  name="nota_max"
                  type="number"
                  min={1}
                  max={10}
                  defaultValue={item.nota_max ?? 5}
                  className={inputCls}
                />
              </div>
            </div>
            <p className={helpCls}>
              Cliente recebe pergunta + escala (ex: &ldquo;1, 2, 3, 4, 5&rdquo;).
              Captura da resposta vai pro agente IA (ou aguarda mig 045 pra
              captura estruturada).
            </p>
          </>
        )}

        {acao === "mudar_manual" && (
          <PayloadField
            payload={payload}
            setPayload={setPayload}
            field="mensagem_pre"
            label="Mensagem ao cliente"
            type="textarea"
            help='Default: "Estou te transferindo para um atendente..."'
          />
        )}

        {acao === "setar_nome" && (
          <PayloadField
            payload={payload}
            setPayload={setPayload}
            field="pergunta"
            label="Pergunta"
            help='Default: "Qual é o seu nome?"'
          />
        )}
      </div>

      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" name="ativo" defaultChecked={item.ativo} className="size-4" />
        Item ativo
      </label>

      <div className="flex justify-between gap-2 pt-2">
        <Button
          type="button"
          variant="outline"
          onClick={() => onSelect(null)}
        >
          Fechar
        </Button>
        <Button type="submit" disabled={saving}>
          {saving ? <Loader2 className="size-4 animate-spin" /> : <Save className="size-4" />}
          Salvar item
        </Button>
      </div>
    </form>
  );
}

// Helper pra editar campo dentro do JSONB acao_payload
function PayloadField({
  payload,
  setPayload,
  field,
  label,
  type = "text",
  help,
  required,
}: {
  payload: Record<string, unknown>;
  setPayload: (p: Record<string, unknown>) => void;
  field: string;
  label: string;
  type?: "text" | "textarea" | "number";
  help?: string;
  required?: boolean;
}) {
  const value = payload[field];
  const stringValue = value == null ? "" : String(value);
  return (
    <div className="space-y-1">
      <label className={labelCls}>{label}</label>
      {type === "textarea" ? (
        <textarea
          value={stringValue}
          required={required}
          rows={2}
          onChange={(e) => setPayload({ ...payload, [field]: e.target.value })}
          className={textareaCls}
        />
      ) : (
        <input
          type={type}
          value={stringValue}
          required={required}
          onChange={(e) =>
            setPayload({
              ...payload,
              [field]:
                type === "number" && e.target.value
                  ? Number(e.target.value)
                  : e.target.value,
            })
          }
          className={inputCls}
        />
      )}
      {help && <p className={helpCls}>{help}</p>}
    </div>
  );
}

function PayloadCheckbox({
  payload,
  setPayload,
  field,
  label,
  defaultValue = false,
}: {
  payload: Record<string, unknown>;
  setPayload: (p: Record<string, unknown>) => void;
  field: string;
  label: string;
  defaultValue?: boolean;
}) {
  const raw = payload[field];
  const checked = raw === undefined ? defaultValue : Boolean(raw);
  return (
    <label className="flex items-center gap-2 text-sm">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => setPayload({ ...payload, [field]: e.target.checked })}
        className="size-4"
      />
      {label}
    </label>
  );
}

// Dropdown que lista departamentos cadastrados — substitui input livre pra
// ação transferir_dep. Sem dropdown user precisaria saber decorar o ID.
function DepartamentoSelect({
  payload,
  setPayload,
  departamentos,
}: {
  payload: Record<string, unknown>;
  setPayload: (p: Record<string, unknown>) => void;
  departamentos: Departamento[];
}) {
  const current = payload["departamento_id"];
  const currentStr =
    current === undefined || current === null ? "" : String(current);
  if (departamentos.length === 0) {
    return (
      <div className="space-y-1">
        <label className={labelCls}>Departamento *</label>
        <p className="rounded-md border border-amber-300 bg-amber-50 p-2 text-xs text-amber-900 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-200">
          Nenhum departamento cadastrado.{" "}
          <Link href="/departamentos" className="font-medium underline">
            Cadastrar departamento
          </Link>
        </p>
      </div>
    );
  }
  return (
    <div className="space-y-1">
      <label className={labelCls}>Departamento *</label>
      <select
        value={currentStr}
        required
        onChange={(e) =>
          setPayload({
            ...payload,
            departamento_id: e.target.value ? Number(e.target.value) : null,
          })
        }
        className={inputCls}
      >
        <option value="">— selecione —</option>
        {departamentos
          .filter((d) => d.ativo)
          .map((d) => (
            <option key={d.id} value={d.id}>
              {d.nome}
              {d.users_count != null ? ` (${d.users_count} membros)` : ""}
            </option>
          ))}
      </select>
      <p className={helpCls}>
        Cliente é atribuído ao departamento selecionado e sai do menu.
      </p>
    </div>
  );
}

// Dropdown opcional de hook cadastrado — quando selecionado preenche
// hook_id (frontend) e o backend usa retry+DLQ. Selecionar "—" deixa o
// admin usar URL livre no campo abaixo.
function HookSelect({ item, hooks }: { item: MenuItem; hooks: Hook[] }) {
  const [hookId, setHookId] = useState<string>(
    item.hook_id ? String(item.hook_id) : ""
  );
  return (
    <div className="space-y-1">
      <label className={labelCls}>Hook cadastrado (recomendado)</label>
      <select
        name="hook_id"
        value={hookId}
        onChange={(e) => setHookId(e.target.value)}
        className={inputCls}
      >
        <option value="">— sem hook (usar URL livre abaixo) —</option>
        {hooks
          .filter((h) => h.ativo)
          .map((h) => (
            <option key={h.id} value={h.id}>
              {h.nome} — {h.evento}
            </option>
          ))}
      </select>
      <p className={helpCls}>
        Hooks têm retry exponencial (1s/5s/25s) + DLQ.{" "}
        <Link href="/integracoes/hooks" className="underline">
          Gerenciar hooks
        </Link>
      </p>
    </div>
  );
}

// Empty state que mostra botão "Gerar a partir dos agentes" quando árvore vazia.
// Cria 1 menu_item por agente_ia ativo (chamar_agente). One-shot — admin
// edita depois. Botão fica desabilitado se não há agentes ativos.
function SeedFromAgentesEmptyState({
  menuId,
  agentes,
  onSeeded,
}: {
  menuId: number;
  agentes: AgenteIA[];
  onSeeded: () => void;
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const handleSeed = async () => {
    setLoading(true);
    setError(null);
    const res = await seedFromAgentesAction(menuId);
    setLoading(false);
    if (res.ok) {
      onSeeded();
    } else {
      setError(res.error || "Erro ao gerar menu.");
    }
  };
  if (agentes.length === 0) {
    return (
      <div className="space-y-3 py-8 text-center">
        <p className="text-sm text-muted-foreground">
          Sem opções ainda. Cadastre agentes IA primeiro pra gerar o menu
          automaticamente.
        </p>
        <Link
          href="/agents/new"
          className="inline-flex items-center gap-1 text-sm font-medium text-primary underline"
        >
          <Plus className="size-3.5" /> Cadastrar agente
        </Link>
      </div>
    );
  }
  return (
    <div className="space-y-3 py-6 text-center">
      <p className="text-sm text-muted-foreground">
        Sem opções ainda. Adicione manualmente ou gere uma opção por agente IA
        ativo da empresa.
      </p>
      <Button size="sm" onClick={handleSeed} disabled={loading}>
        {loading ? (
          <Loader2 className="size-4 animate-spin" />
        ) : (
          <Plus className="size-4" />
        )}
        Gerar {agentes.length} opção(ões) a partir dos agentes
      </Button>
      {error && (
        <p className="text-xs text-destructive">{error}</p>
      )}
      <p className="text-xs text-muted-foreground">
        Você pode editar/reordenar/excluir depois.
      </p>
    </div>
  );
}

// Dropdown que lista agente_ia ativos da empresa pra ação chamar_agente.
// Substitui input livre — admin não digita slug inválido. Mostra aviso
// se não há agente cadastrado, com link pra criar.
function AgenteSelect({
  payload,
  setPayload,
  agentes,
}: {
  payload: Record<string, unknown>;
  setPayload: (p: Record<string, unknown>) => void;
  agentes: AgenteIA[];
}) {
  const current = String(payload["agente_slug"] || "");
  if (agentes.length === 0) {
    return (
      <div className="space-y-1">
        <label className={labelCls}>Agente IA *</label>
        <p className="rounded-md border border-amber-300 bg-amber-50 p-2 text-xs text-amber-900 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-200">
          Nenhum agente IA ativo cadastrado.{" "}
          <Link href="/agents/new" className="font-medium underline">
            Cadastrar agente
          </Link>
        </p>
      </div>
    );
  }
  return (
    <div className="space-y-1">
      <label className={labelCls}>Agente IA *</label>
      <select
        value={current}
        required
        onChange={(e) =>
          setPayload({ ...payload, agente_slug: e.target.value })
        }
        className={inputCls}
      >
        <option value="">— selecione —</option>
        {agentes.map((a) => (
          <option key={a.id} value={a.slug}>
            {a.nome}
            {a.is_default ? " (padrão)" : ""} — {a.slug}
          </option>
        ))}
      </select>
      <p className={helpCls}>
        Cliente cai nesse agente após escolher essa opção. Edite agentes em{" "}
        <Link href="/agents" className="underline">
          /agents
        </Link>
        .
      </p>
    </div>
  );
}

// =====================================================================
// Preview WhatsApp-like
// =====================================================================

function PreviewWhatsApp({
  menu,
  items,
}: {
  menu: MenuChatbot;
  items: MenuItem[];
}) {
  const roots = items
    .filter((i) => i.parent_id === null && i.ativo)
    .sort((a, b) => a.ordem - b.ordem);
  const formatList = (list: MenuItem[]) =>
    list.map((i) => `${i.ordem}. ${i.label}`).join("\n");
  const welcomeText = `${menu.mensagem_boas_vindas.trim()}${
    roots.length
      ? "\n\n" + formatList(roots) + "\n\nDigite o número da opção desejada."
      : ""
  }`;

  const autoTarget = menu.auto_navegar_para_item_id
    ? items.find((i) => i.id === menu.auto_navegar_para_item_id)
    : null;

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {menu.solicitar_nome
              ? "Fluxo da primeira mensagem"
              : "Boas-vindas (primeira mensagem)"}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {autoTarget ? (
            <div className="rounded-md border border-blue-300 bg-blue-50 p-3 text-xs text-blue-900 dark:border-blue-700 dark:bg-blue-950/30 dark:text-blue-200">
              <strong>Auto-navegar ativo:</strong> menu não é exibido. Cliente
              cai direto na ação{" "}
              <code className="font-mono">{autoTarget.acao_tipo}</code> do item{" "}
              <strong>“{autoTarget.label}”</strong>.
            </div>
          ) : (
            <>
              {menu.solicitar_nome && (
                <>
                  <div>
                    <p className="mb-1 text-xs font-semibold">
                      1. Cliente envia primeira mensagem
                    </p>
                    <div className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-950 dark:bg-emerald-900/20 dark:text-emerald-100">
                      <pre className="whitespace-pre-wrap font-sans">
                        {(
                          menu.mensagem_coleta ||
                          "Olá! Antes de começarmos, qual seu nome?"
                        ).trim()}
                      </pre>
                    </div>
                  </div>
                  <div>
                    <p className="mb-1 text-xs font-semibold">
                      2. Cliente responde com nome (ex: “João”)
                    </p>
                    <div className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-950 dark:bg-emerald-900/20 dark:text-emerald-100">
                      <pre className="whitespace-pre-wrap font-sans">
                        {(
                          menu.mensagem_confirmar_coleta || "Obrigado, {nome}! 🙂"
                        )
                          .replace(/\{nome\}/g, "João")
                          .trim()}
                        {menu.mensagem_final_coleta?.trim()
                          ? "\n\n" + menu.mensagem_final_coleta.trim()
                          : ""}
                        {"\n\n"}
                        {welcomeText}
                      </pre>
                    </div>
                  </div>
                </>
              )}
              {!menu.solicitar_nome && (
                <div className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-950 dark:bg-emerald-900/20 dark:text-emerald-100">
                  {menu.arquivo_url && (
                    <p className="mb-2 text-xs font-mono text-emerald-700 dark:text-emerald-300">
                      📎 {menu.arquivo_url}
                    </p>
                  )}
                  <pre className="whitespace-pre-wrap font-sans">
                    {welcomeText}
                  </pre>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Cenários de resposta</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div>
            <p className="mb-1 font-semibold">
              Cliente digita opção válida (ex: &quot;1&quot;)
            </p>
            <p className={helpCls}>
              Worker executa a ação do item. Comportamento varia: submenu mostra
              filhos; transferir_dep atribui departamento; chamar_agente atribui
              agente IA + sai do menu; etc.
            </p>
          </div>
          <div>
            <p className="mb-1 font-semibold">
              Cliente digita opção inválida (ex: &quot;x&quot;)
            </p>
            <div className="rounded-lg bg-emerald-50 p-3 text-emerald-950 dark:bg-emerald-900/20 dark:text-emerald-100">
              <pre className="whitespace-pre-wrap font-sans">
                {menu.mensagem_opcao_invalida}
                {"\n\n"}
                {formatList(roots)}
              </pre>
            </div>
          </div>
          <div>
            <p className="mb-1 font-semibold">
              Cliente digita keyword (ex:{" "}
              {menu.trigger_keywords.map((k) => `"${k}"`).join(", ")})
            </p>
            <p className={helpCls}>
              Reset pra raiz, reenvia mensagem de boas-vindas.
            </p>
          </div>
          {menu.menu_moderno && (
            <div className="rounded-md border border-amber-300 bg-amber-50 p-2 text-xs text-amber-900 dark:border-amber-700 dark:bg-amber-950/30 dark:text-amber-200">
              <strong>Menu moderno ON:</strong> em conexões com suporte
              (Twilio/Evolution), as opções viram botões interativos do WhatsApp
              em vez de lista numerada. Fallback: lista quando &gt;10 opções ou
              provider não suporta.
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
