import {
  Activity,
  Bot,
  Headphones,
  LayoutDashboard,
  ShieldCheck,
  Smartphone,
  type LucideIcon,
} from "lucide-react";

/**
 * Catálogo de navegação — módulo NEUTRO (sem "use client").
 *
 * Antes vivia dentro de `top-nav-tabs.tsx`, um Client Component, e a sidebar
 * importava de lá. Agora a árvore é uma coisa só: **grupo → itens**, e cada
 * grupo é uma seção colapsável da sidebar. Isso elimina a segunda camada de
 * navegação (a barra horizontal de até 11 abas, que cortava na direita sem
 * nenhuma affordance de rolagem).
 */

export interface NavItem {
  label: string;
  href: string;
  /** Permissão necessária. Undefined = sempre visível. */
  requires?: string | string[];
  /**
   * Subseção dentro do grupo. Serve pra grupos grandes, onde uma lista
   * corrida de 11 destinos não diz o que faz o quê — Governança junta
   * "quem é a empresa", "quem são as pessoas", "quem pode o quê" e "quando
   * a operação funciona" na mesma pilha.
   *
   * Itens sem seção aparecem antes das seções, soltos.
   */
  secao?: string;
}

export interface NavGroup {
  grupo: string;
  label: string;
  icon: LucideIcon;
  /** Rota de fallback quando nenhum item é permitido. */
  href: string;
  itens: NavItem[];
}

export const NAV_GROUPS: NavGroup[] = [
  {
    grupo: "visao",
    label: "Visão Geral",
    icon: LayoutDashboard,
    href: "/dashboard/atendimento",
    itens: [
      { label: "Atendimentos", href: "/dashboard/atendimento" },
      // A tela existia e não era alcançável por nada — nenhum link, menu ou
      // redirect apontava pra ela. Ver `app/page.tsx`.
      { label: "Primeiros passos", href: "/onboarding" },
    ],
  },
  {
    grupo: "operacao",
    label: "Operação",
    icon: Headphones,
    href: "/atendimento",
    itens: [
      { label: "Atendimentos", href: "/atendimento", requires: "atendimento.read" },
      { label: "Conversas", href: "/chats", requires: "atendimento.read" },
      { label: "Clientes", href: "/clientes", requires: "cliente.read" },
      { label: "Agendamentos", href: "/agendamentos", requires: "agendamento.read" },
      { label: "Campanhas", href: "/campanhas", requires: "disparador.disparar" },
      { label: "Contatos capturados", href: "/disparador/contatos", requires: "disparador.capturar" },
      { label: "Grupos capturados", href: "/disparador/grupos", requires: "disparador.capturar" },
      { label: "Chaves de API", href: "/disparador/api-keys", requires: "disparador.api_key.manage" },
      { label: "Tags", href: "/tags", requires: "tag.manage" },
    ],
  },
  {
    grupo: "ia",
    label: "IA & Conteúdo",
    icon: Bot,
    href: "/agents",
    itens: [
      { label: "Painel de IA", href: "/dashboard/ia", requires: "agente.config" },
      { label: "Agentes", href: "/agents", requires: "agente.config" },
      { label: "Menu chatbot", href: "/menus", requires: "menu_chatbot.read" },
      { label: "Workflows", href: "/workflows", requires: "menu_chatbot.read" },
      { label: "Catálogo de modelos", href: "/catalog/models", requires: "agente.config" },
      { label: "Servidores MCP", href: "/catalog/mcp", requires: "agente.config" },
      { label: "Respostas rápidas", href: "/modelos", requires: "modelo_mensagem.read" },
      { label: "Base de conhecimento", href: "/settings/pastas", requires: "base_conhecimento.read" },
      { label: "Variáveis", href: "/settings/variaveis", requires: "variavel.read" },
      { label: "Modelo por agente", href: "/models", requires: "agente.config" },
      { label: "Whitelist da IA", href: "/whitelist", requires: "whitelist.manage" },
    ],
  },
  {
    grupo: "conectividade",
    label: "Conectividade",
    icon: Smartphone,
    href: "/connections",
    itens: [
      { label: "Conexões", href: "/connections", requires: "conexao.read" },
      { label: "Integrações externas", href: "/settings/integracoes", requires: "conexao.write" },
      { label: "Webhooks", href: "/hooks", requires: "hook.read" },
    ],
  },
  {
    grupo: "governanca",
    label: "Governança",
    icon: ShieldCheck,
    href: "/companies",
    itens: [
      // Quem é a empresa e quanto ela custa
      { secao: "Empresa", label: "Cadastro", href: "/companies", requires: "empresa.update" },
      { secao: "Empresa", label: "Plano e cobrança", href: "/billing", requires: "empresa.update" },
      { secao: "Empresa", label: "Orçamento de IA", href: "/governanca/ia-budget", requires: "empresa.update" },
      // Quem trabalha nela
      { secao: "Pessoas", label: "Usuários", href: "/usuarios", requires: "empresa.member.add" },
      { secao: "Pessoas", label: "Atendentes", href: "/atendentes", requires: "empresa.member.add" },
      { secao: "Pessoas", label: "Departamentos", href: "/settings/departamentos", requires: "departamento.read" },
      // Quem pode o quê
      { secao: "Acesso", label: "Perfis de acesso", href: "/settings/perfis", requires: "perfil.read" },
      { secao: "Acesso", label: "Segurança", href: "/settings", requires: "security.audit.read" },
      // Quando a operação funciona
      { secao: "Regras", label: "Turnos e jornada", href: "/settings/turnos", requires: "departamento.read" },
      { secao: "Regras", label: "Horário de atendimento", href: "/settings/horarios", requires: "horario.write" },
      { secao: "Regras", label: "Regras de agendamento", href: "/settings/calendar-rules", requires: "agendamento.regras.write" },
    ],
  },
  {
    grupo: "observabilidade",
    label: "Observabilidade",
    icon: Activity,
    href: "/traces",
    itens: [
      { label: "Traces", href: "/traces", requires: "security.audit.read" },
      { label: "Fila", href: "/queue", requires: "security.audit.read" },
      { label: "Qualidade e NPS", href: "/dashboard/qualidade", requires: "atendimento.read" },
      { label: "Qualidade do RAG", href: "/dashboard/rag", requires: "agente.config" },
      { label: "Sandbox do RAG", href: "/dashboard/rag/sandbox", requires: "agente.config" },
      { label: "Relatórios E2E", href: "/relatorios/allure", requires: "agente.config" },
      { label: "Histórico de acesso", href: "/settings/security/login-history", requires: "security.audit.read" },
      { label: "Registro de auditoria", href: "/settings/security/audit", requires: "security.audit.read" },
      { label: "Governança de dados", href: "/settings/security/governanca", requires: "security.audit.read" },
      { label: "Feature flags", href: "/settings/feature-flags", requires: "empresa.update" },
    ],
  },
];

/**
 * Mapa de prefixo → grupo, para resolver o grupo ativo a partir da URL.
 * A ordem não importa: vence o prefixo mais LONGO, e é isso que faz
 * `/settings/security/audit` cair em observabilidade e não em governança.
 */
const GRUPO_PREFIXOS: { grupo: string; prefixos: string[] }[] = [
  { grupo: "visao", prefixos: ["/dashboard", "/onboarding"] },
  {
    grupo: "operacao",
    prefixos: [
      "/atendimento",
      "/chats",
      "/clientes",
      "/agendamentos",
      "/campanhas",
      "/disparador",
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
      "/whitelist",
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
      "/usuarios",
      "/atendentes",
      "/billing",
      "/governanca",
      "/settings/perfis",
      "/settings/departamentos",
      "/settings/turnos",
      "/settings/horarios",
      "/settings/calendar-rules",
      "/settings", // raiz = "Segurança"; vem por último como fallback
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
      "/dashboard/qualidade",
      "/dashboard/rag",
    ],
  },
];

/** Grupo correspondente à URL, ou null fora da navegação (ex. /login). */
export function resolveGroup(pathname: string): string | null {
  let melhor: string | null = null;
  let maior = -1;
  for (const { grupo, prefixos } of GRUPO_PREFIXOS) {
    for (const p of prefixos) {
      if (
        (pathname === p || pathname.startsWith(p + "/")) &&
        p.length > maior
      ) {
        melhor = grupo;
        maior = p.length;
      }
    }
  }
  return melhor;
}

/** Item ativo: match exato ou prefixo de sub-rota (`/agents/x/edit`). */
export function isItemActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(href + "/");
}
