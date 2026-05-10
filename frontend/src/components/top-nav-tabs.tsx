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

import { cn } from "@/lib/utils";

export interface NavTab {
  label: string;
  href: string;
}

/**
 * Catálogo de tabs por grupo. Chave = prefixo top-level que identifica o grupo
 * (a sidebar usa o mesmo prefixo pra detectar grupo ativo). Pra detectar
 * pertencimento usamos os prefixos dentro de cada grupo (ver GRUPO_PREFIXOS).
 */
export const NAV_TABS_BY_GROUP: Record<string, NavTab[]> = {
  visao: [{ label: "Dashboard IA", href: "/dashboard/ia" }],
  operacao: [
    { label: "Atendimentos", href: "/atendimento" },
    { label: "Conversas", href: "/chats" },
    { label: "Clientes", href: "/clientes" },
    { label: "Agendamentos", href: "/agendamentos" },
    { label: "Campanhas", href: "/campanhas" },
  ],
  ia: [
    { label: "Agentes", href: "/agents" },
    { label: "Menu chatbot", href: "/menus" },
    { label: "Catálogo Modelos", href: "/catalog/models" },
    { label: "MCP Servers", href: "/catalog/mcp" },
    { label: "Quick Replies", href: "/modelos" },
    { label: "Base de Conhecimento", href: "/settings/pastas" },
    { label: "Variáveis", href: "/settings/variaveis" },
    { label: "Modelo por agente", href: "/models" },
  ],
  conectividade: [
    { label: "Conexões", href: "/connections" },
    { label: "Integrações Externas", href: "/settings/integracoes" },
    { label: "Webhooks", href: "/hooks" },
  ],
  governanca: [
    { label: "Empresas", href: "/companies" },
    { label: "Atendentes", href: "/atendentes" },
    { label: "IA Budget", href: "/governanca/ia-budget" },
    { label: "Perfis (RBAC)", href: "/settings/perfis" },
    { label: "Departamentos", href: "/settings/departamentos" },
    { label: "Horário de Atendimento", href: "/settings/horarios" },
    { label: "Regras de Agendamento", href: "/settings/calendar-rules" },
    { label: "Segurança", href: "/settings" },
  ],
  observabilidade: [
    { label: "Traces", href: "/traces" },
    { label: "Fila", href: "/queue" },
    { label: "NPS / Qualidade", href: "/dashboard/qualidade" },
    { label: "Qualidade RAG", href: "/dashboard/rag" },
    { label: "RAG Sandbox", href: "/dashboard/rag/sandbox" },
    { label: "Relatórios E2E", href: "/relatorios/allure" },
    { label: "Histórico de Acesso", href: "/settings/security/login-history" },
    { label: "Audit log", href: "/settings/security/audit" },
    { label: "Feature flags", href: "/settings/feature-flags" },
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
    prefixos: ["/atendimento", "/chats", "/clientes", "/agendamentos", "/campanhas"],
  },
  {
    grupo: "ia",
    prefixos: [
      "/agents",
      "/menus",
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
  if (!pathname) return null;

  const grupo = resolveGroup(pathname);
  if (!grupo) return null;

  const tabs = NAV_TABS_BY_GROUP[grupo] ?? [];
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
