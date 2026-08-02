"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useTheme } from "next-themes";
import {
  LogOut,
  Moon,
  Plus,
  Search,
  Sun,
  type LucideIcon,
} from "lucide-react";

import { NAV_GROUPS, type NavItem } from "@/components/nav-catalog";
import { usePermissionsContext } from "@/components/permissions-context";
import { Button } from "@/components/ui/button";
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
  CommandShortcut,
} from "@/components/ui/command";
import { signOut } from "@/lib/auth-client";

/**
 * Paleta de comandos — ⌘K / Ctrl+K.
 *
 * A navegação tem 6 grupos, 15 subseções e ~40 destinos. Isso é bom pra quem
 * está procurando e ruim pra quem já sabe onde quer chegar: são três cliques
 * (abrir grupo → achar a seção → clicar) para uma tela que a pessoa visita
 * dez vezes por dia.
 *
 * A fonte é o mesmo `NAV_GROUPS` da sidebar, com o mesmo filtro de permissão —
 * a paleta nunca oferece um destino que devolveria 403. Rotas de criação
 * (`/agents/new` e afins) não estão na sidebar de propósito e entram aqui como
 * ação, que é o que elas são.
 */

/**
 * O gatilho e o diálogo conversam por evento de DOM, não por contexto.
 *
 * Um provider só pra isso obrigaria o `AppShell` a envolver a árvore inteira
 * num terceiro contexto, e o único estado compartilhado é um booleano.
 */
const EVENTO_ABRIR = "chatnexus:abrir-paleta";

interface Criacao {
  label: string;
  href: string;
  requires?: string;
}

const CRIAR: Criacao[] = [
  { label: "Novo agente", href: "/agents/new", requires: "agente.config" },
  { label: "Novo usuário", href: "/usuarios", requires: "empresa.member.add" },
  { label: "Novo menu", href: "/menus/new", requires: "menu_chatbot.read" },
  { label: "Nova campanha", href: "/campanhas", requires: "disparador.disparar" },
  { label: "Nova conexão", href: "/connections", requires: "conexao.write" },
  {
    label: "Novo modelo",
    href: "/catalog/models/new",
    requires: "agente.config",
  },
  {
    label: "Novo servidor MCP",
    href: "/catalog/mcp/new",
    requires: "agente.config",
  },
];

/** Destinos que existem mas não cabem na sidebar — relatório e tela pessoal. */
const EXTRAS: (NavItem & { grupoLabel: string })[] = [
  {
    grupoLabel: "Operação",
    label: "Relatórios de conversa",
    href: "/chats/relatorios",
    requires: "atendimento.read",
  },
];

export function CommandPalette() {
  const [aberto, setAberto] = useState(false);
  const router = useRouter();
  const { hasPerm } = usePermissionsContext();
  const { resolvedTheme, setTheme } = useTheme();

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key.toLowerCase() !== "k") return;
      if (!e.metaKey && !e.ctrlKey) return;
      // Não sequestra ⌘K de dentro de um campo de texto: em `/atendimento` o
      // operador está digitando resposta pro cliente.
      const alvo = e.target as HTMLElement | null;
      if (
        alvo?.isContentEditable ||
        ["INPUT", "TEXTAREA", "SELECT"].includes(alvo?.tagName ?? "")
      ) {
        return;
      }
      e.preventDefault();
      setAberto((v) => !v);
    }
    function onAbrir() {
      setAberto(true);
    }
    document.addEventListener("keydown", onKey);
    document.addEventListener(EVENTO_ABRIR, onAbrir);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener(EVENTO_ABRIR, onAbrir);
    };
  }, []);

  const podeVer = (i: { requires?: string | string[] }) =>
    !i.requires || hasPerm(i.requires);

  function ir(href: string) {
    setAberto(false);
    router.push(href);
  }

  const grupos = NAV_GROUPS.map((g) => ({
    label: g.label,
    itens: g.itens.filter(podeVer),
  })).filter((g) => g.itens.length > 0);

  const criar = CRIAR.filter(podeVer);
  const extras = EXTRAS.filter(podeVer);
  const escuro = resolvedTheme === "dark";

  return (
    <CommandDialog
      open={aberto}
      onOpenChange={setAberto}
      title="Buscar no painel"
      description="Digite para encontrar uma tela ou executar uma ação."
      // O `DialogContent` nasce `max-w-sm`, que serve pra confirmação e
      // aperta uma lista com nome do destino de um lado e a seção do outro.
      className="sm:max-w-xl"
    >
      {/* O `CommandDialog` daqui só monta o Dialog — não embrulha os filhos
          no Root do cmdk. Sem este `<Command>`, o Input sobe sem store e
          quebra em runtime ("Cannot read properties of undefined"). */}
      <Command>
        <CommandInput
          placeholder="Buscar tela ou ação…"
          onKeyDown={confirmarComEnter}
        />
        <CommandList>
          <CommandEmpty>Nada encontrado.</CommandEmpty>

          {criar.length > 0 && (
            <CommandGroup heading="Criar">
              {criar.map((c) => (
                <CommandItem
                  key={c.href + c.label}
                  value={`criar ${c.label}`}
                  onSelect={() => ir(c.href)}
                >
                  <Plus />
                  {c.label}
                </CommandItem>
              ))}
            </CommandGroup>
          )}

          {grupos.map((g) => (
            <CommandGroup key={g.label} heading={g.label}>
              {g.itens.map((i) => (
                <CommandItem
                  key={i.href}
                  // A seção entra no `value` pra busca casar por ela também:
                  // digitar "prospecção" acha Campanhas, Contatos e Grupos.
                  value={`${g.label} ${i.secao ?? ""} ${i.label}`}
                  onSelect={() => ir(i.href)}
                >
                  {i.label}
                  {i.secao && (
                    <CommandShortcut className="tracking-normal">
                      {i.secao}
                    </CommandShortcut>
                  )}
                </CommandItem>
              ))}
            </CommandGroup>
          ))}

          {extras.length > 0 && (
            <CommandGroup heading="Outros">
              {extras.map((e) => (
                <CommandItem
                  key={e.href}
                  value={`${e.grupoLabel} ${e.label}`}
                  onSelect={() => ir(e.href)}
                >
                  {e.label}
                </CommandItem>
              ))}
            </CommandGroup>
          )}

          <CommandSeparator />
          <CommandGroup heading="Ações">
            <AcaoItem
              icon={escuro ? Sun : Moon}
              label={escuro ? "Mudar para tema claro" : "Mudar para tema escuro"}
              onSelect={() => {
                setTheme(escuro ? "light" : "dark");
                setAberto(false);
              }}
            />
            <AcaoItem
              icon={LogOut}
              label="Sair da conta"
              onSelect={() => {
                setAberto(false);
                signOut().finally(() => router.push("/login"));
              }}
            />
          </CommandGroup>
        </CommandList>
      </Command>
    </CommandDialog>
  );
}

/**
 * Confirma o item destacado com Enter.
 *
 * Deveria ser o cmdk fazendo isso — ele tem um `case "Enter"` que dispara o
 * evento de seleção no item com `aria-selected="true"`. Só que dentro do
 * Dialog do Base UI ele não dispara: seta pra cima e pra baixo movem o
 * destaque, clique funciona, e o Enter não faz nada. Conferido em runtime —
 * o item está no DOM com `cmdk-item`, `aria-selected="true"` e dentro do
 * `CommandList`, que é exatamente o que o seletor do cmdk procura.
 *
 * O handler fica no INPUT, não na raiz: assim ele roda antes do cmdk e o
 * `stopPropagation` garante que, se o cmdk voltar a funcionar numa versão
 * futura, a ação não dispare duas vezes.
 */
function confirmarComEnter(e: React.KeyboardEvent<HTMLInputElement>) {
  if (e.key !== "Enter" || e.nativeEvent.isComposing) return;
  const item = document
    .querySelector("[data-slot=command-list]")
    ?.querySelector<HTMLElement>('[cmdk-item=""][aria-selected="true"]');
  if (!item) return;
  e.preventDefault();
  e.stopPropagation();
  item.click();
}

/**
 * Botão no topo que abre a paleta.
 *
 * O atalho sozinho não basta: quem não sabe que ⌘K existe nunca descobre. O
 * botão mostra o atalho, então serve de descoberta e de lembrete.
 */
export function CommandPaletteTrigger() {
  return (
    <Button
      variant="ghost"
      size="sm"
      className="gap-2 text-muted-foreground"
      onClick={() => document.dispatchEvent(new CustomEvent(EVENTO_ABRIR))}
    >
      <Search className="size-4" />
      <span className="hidden sm:inline">Buscar</span>
      <kbd className="hidden rounded border bg-muted px-1.5 py-0.5 font-mono text-[10px] sm:inline">
        ⌘K
      </kbd>
    </Button>
  );
}

function AcaoItem({
  icon: Icone,
  label,
  onSelect,
}: {
  icon: LucideIcon;
  label: string;
  onSelect: () => void;
}) {
  return (
    <CommandItem value={label} onSelect={onSelect}>
      <Icone />
      {label}
    </CommandItem>
  );
}
