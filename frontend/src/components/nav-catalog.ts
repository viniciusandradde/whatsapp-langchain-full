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
   * Só para superadmin da PLATAFORMA.
   *
   * Existe porque `requires` não dá conta: não há permissão de superadmin no
   * catálogo, e criar uma seria pior — `shared/perfil.py` concede o catálogo
   * inteiro ao superadmin, então qualquer Admin de tenant também a teria. Até
   * aqui, "Relatórios de teste" ficava visível para quem tem `agente.config`,
   * e a página respondia "Acesso restrito".
   */
  requiresSuperadmin?: boolean;
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
      // Segunda tela órfã: existia, ninguém linkava. É a visão pessoal do
      // atendente (produção de hoje e dos últimos 30 dias), então mora aqui
      // e não em Governança/Pessoas, que é a visão de quem gerencia.
      { label: "Meu desempenho", href: "/atendentes/me/dashboard" },
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
      // O que CHEGA do cliente
      { secao: "Atendimento", label: "Fila de atendimento", href: "/atendimento", requires: "atendimento.read" },
      { secao: "Atendimento", label: "Histórico de conversas", href: "/chats", requires: "atendimento.read" },
      { secao: "Atendimento", label: "Agendamentos", href: "/agendamentos", requires: "agendamento.read" },
      // O que SAI por iniciativa da empresa
      { secao: "Prospecção", label: "Campanhas", href: "/campanhas", requires: "disparador.disparar" },
      { secao: "Prospecção", label: "Contatos", href: "/disparador/contatos", requires: "disparador.capturar" },
      { secao: "Prospecção", label: "Grupos", href: "/disparador/grupos", requires: "disparador.capturar" },
      { secao: "Prospecção", label: "Chaves da extensão", href: "/disparador/api-keys", requires: "disparador.api_key.manage" },
      // A base que os dois lados usam
      { secao: "Cadastros", label: "Clientes", href: "/clientes", requires: "cliente.read" },
      { secao: "Cadastros", label: "Tags", href: "/tags", requires: "tag.manage" },
    ],
  },
  {
    grupo: "ia",
    label: "IA & Conteúdo",
    icon: Bot,
    href: "/agents",
    itens: [
      // Visão do grupo, solta no topo
      { label: "Painel de IA", href: "/dashboard/ia", requires: "agente.config" },
      // O que responde sozinho — e quando NÃO responde
      { secao: "Automação", label: "Agentes", href: "/agents", requires: "agente.config" },
      { secao: "Automação", label: "Menu chatbot", href: "/menus", requires: "menu_chatbot.read" },
      { secao: "Automação", label: "Workflows", href: "/workflows", requires: "menu_chatbot.read" },
      { secao: "Automação", label: "Números sem IA", href: "/whitelist", requires: "whitelist.manage" },
      // O que a IA sabe
      { secao: "Conhecimento", label: "Base de conhecimento", href: "/settings/pastas", requires: "base_conhecimento.read" },
      { secao: "Conhecimento", label: "Respostas rápidas", href: "/modelos", requires: "modelo_mensagem.read" },
      { secao: "Conhecimento", label: "Variáveis", href: "/settings/variaveis", requires: "variavel.read" },
      // Com o que ela roda
      { secao: "Modelos e ferramentas", label: "Catálogo de modelos", href: "/catalog/models", requires: "agente.config" },
      { secao: "Modelos e ferramentas", label: "Modelo por agente", href: "/models", requires: "agente.config" },
      { secao: "Modelos e ferramentas", label: "Servidores MCP", href: "/catalog/mcp", requires: "agente.config" },
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
      // Veio de Observabilidade: ligar/desligar recurso é configuração, não
      // observação. Estava no grupo dos gráficos só por morar em /settings.
      { secao: "Regras", label: "Recursos ativados", href: "/settings/feature-flags", requires: "empresa.update" },
    ],
  },
  {
    grupo: "observabilidade",
    label: "Observabilidade",
    icon: Activity,
    href: "/traces",
    itens: [
      // A máquina está de pé?
      { secao: "Saúde do sistema", label: "Fila de mensagens", href: "/queue", requires: "security.audit.read" },
      { secao: "Saúde do sistema", label: "Traces", href: "/traces", requires: "security.audit.read" },
      // O atendimento está bom?
      { secao: "Qualidade", label: "Satisfação e NPS", href: "/dashboard/qualidade", requires: "atendimento.read" },
      { secao: "Qualidade", label: "Qualidade das respostas", href: "/dashboard/rag", requires: "agente.config" },
      { secao: "Qualidade", label: "Testar respostas", href: "/dashboard/rag/sandbox", requires: "agente.config" },
      { secao: "Qualidade", label: "Relatórios de teste", href: "/relatorios/allure", requiresSuperadmin: true },
      // Ferramenta de plataforma: mostra dados de todos os clientes e
      // envia mensagem em nome deles.
      { secao: "Plataforma", label: "Uso por cliente", href: "/relatorios/uso", requiresSuperadmin: true },
      { secao: "Plataforma", label: "Saúde da produção", href: "/relatorios/producao", requiresSuperadmin: true },
      // Quem fez o quê
      { secao: "Auditoria", label: "Histórico de acesso", href: "/settings/security/login-history", requires: "security.audit.read" },
      { secao: "Auditoria", label: "Registro de auditoria", href: "/settings/security/audit", requires: "security.audit.read" },
      { secao: "Auditoria", label: "Governança de dados", href: "/settings/security/governanca", requires: "security.audit.read" },
    ],
  },
];

/**
 * Mapa de prefixo → grupo, para resolver o grupo ativo a partir da URL.
 * A ordem não importa: vence o prefixo mais LONGO, e é isso que faz
 * `/settings/security/audit` cair em observabilidade e não em governança.
 */
const GRUPO_PREFIXOS: { grupo: string; prefixos: string[] }[] = [
  {
    grupo: "visao",
    // `/atendentes/me` precisa ser mais longo que o `/atendentes` de
    // governança, senão a visão pessoal cai no grupo de quem gerencia.
    prefixos: ["/dashboard", "/onboarding", "/atendentes/me"],
  },
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
      "/settings/feature-flags",
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

/**
 * Item ativo: match exato, ou prefixo de sub-rota quando NENHUM outro item do
 * catálogo casa melhor.
 *
 * Sem a segunda parte, `/settings/perfis` acendia dois itens ao mesmo tempo:
 * "Perfis de acesso" (match exato) e "Segurança", cujo href é `/settings` e
 * portanto é prefixo de metade das rotas de configuração.
 */
export function isItemActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  if (pathname === href) return true;
  if (!pathname.startsWith(href + "/")) return false;

  // Existe item mais específico casando com esta URL? Então este não é o ativo.
  const maisEspecifico = NAV_GROUPS.some((g) =>
    g.itens.some(
      (i) =>
        i.href.length > href.length &&
        (pathname === i.href || pathname.startsWith(i.href + "/"))
    )
  );
  return !maisEspecifico;
}
