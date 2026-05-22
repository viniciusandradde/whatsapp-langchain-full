"use client";

/**
 * Tabs horizontais por grupo — renderizadas abaixo do header em todas as
 * páginas que pertencem a um grupo da sidebar.
 *
 * Refator 2026-05-07: sidebar reduziu pra 6 entradas top-level; cada grupo
 * abre uma rota default e mostra aqui as sub-páginas relacionadas como tabs
 * navegáveis lado-a-lado.
 *
 * Active state: tab cuja href é prefix do pathname atual.
 * Em rotas fora de grupos (ex /login, /), retorna null.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";

import { usePermissionsContext } from "@/components/permissions-context";
import { cn } from "@/lib/utils";

export interface NavTab {
  label: string;
  href: string;
  /** Permissão necessária pra ver essa tab. Undefined = sempre visível. */
  requires?: string | string[];
}

/**
 * Catálogo de tabs por grupo. Chave = prefixo top-level que identifica o grupo
 * (a sidebar usa o mesmo prefixo pra detectar grupo ativo). Pra detectar
 * pertencimento usamos os prefixos dentro de cada grupo (ver GRUPO_PREFIXOS).
 */
export const NAV_TABS_BY_GROUP: Record<string, NavTab[]> = {
  visao: [{ label: "Atendimentos", href: "/dashboard/atendimento" }],
  operacao: [
    { label: "Atendimentos", href: "/atendimento", requires: "atendimento.read" },
    { label: "Conversas", href: "/chats", requires: "atendimento.read" },
    { label: "Clientes", href: "/clientes", requires: "cliente.read" },
    { label: "Agendamentos", href: "/agendamentos", requires: "agendamento.read" },
    { label: "Campanhas", href: "/campanhas", requires: "agendamento.read" },
    { label: "Tags", href: "/tags", requires: "tag.manage" },
  ],
  ia: [
    { label: "Dashboard IA", href: "/dashboard/ia", requires: "agente.config" },
    { label: "Agentes", href: "/agents", requires: "agente.config" },
    { label: "Menu chatbot", href: "/menus", requires: "menu_chatbot.read" },
    { label: "Workflows", href: "/workflows", requires: "menu_chatbot.read" },
    { label: "Catálogo Modelos", href: "/catalog/models", requires: "agente.config" },
    { label: "MCP Servers", href: "/catalog/mcp", requires: "agente.config" },
    { label: "Quick Replies", href: "/modelos", requires: "modelo_mensagem.read" },
    { label: "Base de Conhecimento", href: "/settings/pastas", requires: "base_conhecimento.read" },
    { label: "Variáveis", href: "/settings/variaveis", requires: "variavel.read" },
    { label: "Modelo por agente", href: "/models", requires: "agente.config" },
  ],
  conectividade: [
    { label: "Conexões", href: "/connections", requires: "conexao.read" },
    { label: "Integrações Externas", href: "/settings/integracoes", requires: "conexao.write" },
    { label: "Webhooks", href: "/hooks", requires: "hook.read" },
  ],
  governanca: [
    { label: "Empresas", href: "/companies", requires: "empresa.update" },
    { label: "Atendentes", href: "/atendentes", requires: "empresa.member.add" },
    { label: "Plano & Cobrança", href: "/billing", requires: "empresa.update" },
    { label: "IA Budget", href: "/governanca/ia-budget", requires: "empresa.update" },
    { label: "Perfis (RBAC)", href: "/settings/perfis", requires: "perfil.read" },
    { label: "Departamentos", href: "/settings/departamentos", requires: "departamento.read" },
    { label: "Horário de Atendimento", href: "/settings/horarios", requires: "horario.write" },
    { label: "Regras de Agendamento", href: "/settings/calendar-rules", requires: "agendamento.regras.write" },
    { label: "Segurança", href: "/settings", requires: "security.audit.read" },
  ],
  observabilidade: [
    { label: "Traces", href: "/traces", requires: "security.audit.read" },
    { label: "Fila", href: "/queue", requires: "security.audit.read" },
    { label: "NPS / Qualidade", href: "/dashboard/qualidade", requires: "atendimento.read" },
    { label: "Qualidade RAG", href: "/dashboard/rag", requires: "agente.config" },
    { label: "RAG Sandbox", href: "/dashboard/rag/sandbox", requires: "agente.config" },
    { label: "Relatórios E2E", href: "/relatorios/allure", requires: "agente.config" },
    { label: "Histórico de Acesso", href: "/settings/security/login-history", requires: "security.audit.read" },
    { label: "Audit log", href: "/settings/security/audit", requires: "security.audit.read" },
    { label: "Governança", href: "/settings/security/governanca", requires: "security.audit.read" },
    { label: "Feature flags", href: "/settings/feature-flags", requires: "empresa.update" },
  ],
};

/**
 * Mapa de prefixos de URL → grupo. A ordem importa: prefixos mais específicos
 * vêm antes dos mais genéricos (ex: /catalog antes de /).
 *
 * Compartilhado com sidebar.tsx via `resolveGroup(pathname)` pra manter
 * consistência: tab grupo X ativo ↔ sidebar destacando grupo X.
 */
export const GRUPO_PREFIXOS: { grupo: string; prefixos: string[] }[] = [
  { grupo: "visao", prefixos: ["/dashboard"] },
  {
    grupo: "operacao",
    prefixos: [
      "/atendimento",
      "/chats",
      "/clientes",
      "/agendamentos",
      "/campanhas",
      "/tags",
    ],
  },
  {
    grupo: "ia",
    prefixos: [
      "/agents",
      "/menus",
      "/workflows",
      "/catalog",
      "/models",
      "/modelos",
      "/settings/pastas",
      "/settings/variaveis",
    ],
  },
  {
    grupo: "conectividade",
    prefixos: ["/connections", "/settings/integracoes", "/hooks"],
  },
  {
    grupo: "governanca",
    prefixos: [
      "/companies",
      "/atendentes",
      "/billing",
      "/governanca",
      "/settings/perfis",
      "/settings/departamentos",
      "/settings/horarios",
      "/settings/calendar-rules",
      "/settings",  // /settings root = "Segurança" (vem por último — fallback)
    ],
  },
  {
    grupo: "observabilidade",
    prefixos: [
      "/traces",
      "/queue",
      "/relatorios",
      "/settings/security",
      "/settings/feature-flags",
    ],
  },
];

/**
 * Resolve o grupo correspondente à URL atual. Retorna null se não bate com
 * nenhum (ex /login, /).
 *
 * Usa "best match": prefixo mais longo (mais específico) ganha. Isso
 * garante que `/settings/security/login-history` cai em "observabilidade"
 * e não em "governanca" (que tem `/settings` mais curto).
 */
export function resolveGroup(pathname: string): string | null {
  let bestGrupo: string | null = null;
  let bestLen = -1;
  for (const { grupo, prefixos } of GRUPO_PREFIXOS) {
    for (const p of prefixos) {
      if ((pathname === p || pathname.startsWith(p + "/")) && p.length > bestLen) {
        bestGrupo = grupo;
        bestLen = p.length;
      }
    }
  }
  return bestGrupo;
}

function isTabActive(pathname: string, tabHref: string): boolean {
  if (tabHref === "/") return pathname === "/";
  return pathname === tabHref || pathname.startsWith(tabHref + "/");
}

export function TopNavTabs() {
  const pathname = usePathname();
  const { hasPerm } = usePermissionsContext();
  if (!pathname) return null;

  const grupo = resolveGroup(pathname);
  if (!grupo) return null;

  const allTabs = NAV_TABS_BY_GROUP[grupo] ?? [];
  // Filtra tabs que o user não tem permissão (Sprint Governança RBAC)
  const tabs = allTabs.filter((t) => !t.requires || hasPerm(t.requires));
  if (tabs.length === 0) return null;

  // Pra grupos com 1 tab só (Visão Geral hoje), não vale a pena renderizar
  // a barra — é redundante com o sidebar.
  if (tabs.length === 1) return null;

  return (
    <nav className="sticky top-0 z-10 -mx-6 -mt-6 mb-4 border-b border-border/40 bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="flex gap-0.5 overflow-x-auto px-6 py-2 scrollbar-thin">
        {tabs.map((tab) => {
          const active = isTabActive(pathname, tab.href);
          return (
            <Link
              key={tab.href}
              href={tab.href}
              className={cn(
                "shrink-0 rounded-md px-3 py-1.5 text-sm transition-colors",
                active
                  ? "bg-primary/10 font-medium text-foreground"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              )}
            >
              {tab.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
