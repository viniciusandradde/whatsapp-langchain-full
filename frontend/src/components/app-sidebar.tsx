"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Fragment, useState } from "react";
import { ChevronRight, LogOut } from "lucide-react";

import { MyStatusToggle } from "@/components/my-status-toggle";
import {
  NAV_GROUPS,
  isItemActive,
  resolveGroup,
  type NavGroup,
  type NavItem,
} from "@/components/nav-catalog";
import { usePermissionsContext } from "@/components/permissions-context";
import { ThemeSwitcher } from "@/components/theme-switcher";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
  SidebarRail,
  SidebarSeparator,
  useSidebar,
} from "@/components/ui/sidebar";
import { signOut } from "@/lib/auth-client";
import { cn } from "@/lib/utils";

/**
 * Navegação do painel — uma camada, não três.
 *
 * Antes: sidebar com 6 grupos → barra horizontal com até 11 abas → e, em
 * `/atendimento`, uma terceira sidebar interna. A barra de abas cortava na
 * direita sem indicar que havia mais ("Modelo por ag…"), e duas rotas não
 * apareciam em lugar nenhum.
 *
 * Agora cada grupo é uma seção colapsável com seus destinos dentro. O grupo da
 * rota atual abre sozinho; os outros ficam fechados. Nada mais corta.
 */
export function AppSidebar({
  empresaSwitcher,
  brand,
}: {
  empresaSwitcher?: React.ReactNode;
  brand?: { nome: string; logo_path: string | null } | null;
}) {
  const pathname = usePathname() ?? "";
  const router = useRouter();
  const { hasPerm, isSuperadmin } = usePermissionsContext();
  const [saindo, setSaindo] = useState(false);

  const grupoAtivo = resolveGroup(pathname);
  const podeVer = (i: NavItem) =>
    (!i.requires || hasPerm(i.requires)) &&
    (!i.requiresSuperadmin || isSuperadmin);

  // Grupo aparece se o usuário puder ver QUALQUER item dele. A regra anterior
  // usava uma permissão "representante" por grupo, e quem tinha (por exemplo)
  // `whitelist.manage` sem `agente.config` perdia o grupo de IA inteiro.
  const grupos = NAV_GROUPS.map((g) => ({
    ...g,
    itens: g.itens.filter(podeVer),
  })).filter((g) => g.itens.length > 0);

  async function handleSignOut() {
    setSaindo(true);
    try {
      await signOut();
    } finally {
      router.push("/login");
      router.refresh();
      setSaindo(false);
    }
  }

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <div className="flex items-center gap-2 px-1 py-1.5">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={brand?.logo_path ?? "/vsa-logo.png"}
            alt=""
            width={28}
            height={28}
            className="size-7 shrink-0 rounded object-contain"
          />
          <div className="grid flex-1 text-left leading-tight group-data-[collapsible=icon]:hidden">
            <span className="truncate text-sm font-semibold">
              {brand?.nome ?? "Chat Nexus"}
            </span>
            <span className="truncate text-[10px] uppercase tracking-[0.15em] text-sidebar-foreground/50">
              operations
            </span>
          </div>
        </div>
        {empresaSwitcher ? (
          <div className="group-data-[collapsible=icon]:hidden">
            {empresaSwitcher}
          </div>
        ) : null}
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarMenu>
            {grupos.map((g) => (
              <GrupoDeNavegacao
                key={g.grupo}
                grupo={g}
                pathname={pathname}
                abertoPorPadrao={grupoAtivo === g.grupo}
              />
            ))}
          </SidebarMenu>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <SidebarSeparator />
        <div className="group-data-[collapsible=icon]:hidden">
          <MyStatusToggle />
          <ThemeSwitcher />
        </div>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              onClick={handleSignOut}
              disabled={saindo}
              tooltip="Sair"
            >
              <LogOut />
              <span>{saindo ? "Saindo…" : "Sair"}</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>

      <SidebarRail />
    </Sidebar>
  );
}

/**
 * Agrupa preservando a ordem de declaração. Itens sem `secao` saem primeiro,
 * num bloco sem rótulo — grupo pequeno não ganha cabeçalho à toa.
 */
function agruparPorSecao(itens: NavItem[]): [string | undefined, NavItem[]][] {
  const ordem: (string | undefined)[] = [];
  const mapa = new Map<string | undefined, NavItem[]>();
  for (const item of itens) {
    if (!mapa.has(item.secao)) {
      mapa.set(item.secao, []);
      ordem.push(item.secao);
    }
    mapa.get(item.secao)!.push(item);
  }
  return ordem.map((s) => [s, mapa.get(s)!]);
}

function GrupoDeNavegacao({
  grupo,
  pathname,
  abertoPorPadrao,
}: {
  grupo: NavGroup;
  pathname: string;
  abertoPorPadrao: boolean;
}) {
  const Icone = grupo.icon;
  const { state, isMobile } = useSidebar();

  // Aberto é estado controlado, não `defaultOpen`.
  //
  // Com `defaultOpen`, navegar de um grupo pro outro mudava o padrão de um
  // componente já montado, e o Base UI avisava no console ("changing the
  // default open state of an uncontrolled Collapsible"). Pior: o valor novo
  // era ignorado, então o grupo da rota nem sempre abria.
  //
  // O ajuste é feito durante o render (padrão do React pra derivar estado de
  // prop), sem efeito. O `|| aberto` é deliberado: chegar num grupo o abre,
  // mas sair dele NÃO fecha — nada colapsa embaixo do cursor de quem estava
  // navegando por ali.
  const [aberto, setAberto] = useState(abertoPorPadrao);
  const [padraoAnterior, setPadraoAnterior] = useState(abertoPorPadrao);
  if (abertoPorPadrao !== padraoAnterior) {
    setPadraoAnterior(abertoPorPadrao);
    setAberto(abertoPorPadrao || aberto);
  }

  // Rail de ícones: o Collapsible fica invisível (`SidebarMenuSub` some via
  // CSS no modo icon), então cada grupo vira um flyout — hover/clique no
  // ícone abre um balão portalizado à direita com os subitens clicáveis.
  // Sem `tooltip` aqui: o balão já traz o nome do grupo, e TooltipTrigger +
  // MenuTrigger no mesmo botão brigam pelos handlers de hover.
  if (state === "collapsed" && !isMobile) {
    return (
      <SidebarMenuItem>
        <DropdownMenu modal={false}>
          <DropdownMenuTrigger
            openOnHover
            delay={100}
            closeDelay={200}
            render={
              <SidebarMenuButton
                isActive={abertoPorPadrao}
                aria-label={grupo.label}
              >
                <Icone />
              </SidebarMenuButton>
            }
          />
          {/* w-auto: o Popup nasce com w-(--anchor-width) — 32px no rail. */}
          <DropdownMenuContent
            side="right"
            align="start"
            sideOffset={6}
            className="w-auto min-w-56"
          >
            {/* GroupLabel do Base UI exige estar dentro de Menu.Group —
                fora dele estoura o invariant #31 em produção. */}
            <DropdownMenuGroup>
              <DropdownMenuLabel>{grupo.label}</DropdownMenuLabel>
            </DropdownMenuGroup>
            {agruparPorSecao(grupo.itens).map(([secao, itens]) => (
              <Fragment key={secao ?? "_"}>
                {secao && <DropdownMenuSeparator />}
                <DropdownMenuGroup>
                  {secao && (
                    <DropdownMenuLabel className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                      {secao}
                    </DropdownMenuLabel>
                  )}
                  {itens.map((item) => (
                    <DropdownMenuItem
                      key={item.href}
                      render={<Link href={item.href} />}
                      className={cn(
                        isItemActive(pathname, item.href) &&
                          "bg-accent font-medium text-accent-foreground"
                      )}
                    >
                      {item.label}
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuGroup>
              </Fragment>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    );
  }

  return (
    <Collapsible
      open={aberto}
      onOpenChange={setAberto}
      className="group/collapsible"
      render={<SidebarMenuItem />}
    >
      <CollapsibleTrigger
        render={
          <SidebarMenuButton tooltip={grupo.label} isActive={abertoPorPadrao}>
            <Icone />
            <span>{grupo.label}</span>
            <ChevronRight className="ml-auto transition-transform duration-200 group-data-[open]/collapsible:rotate-90" />
          </SidebarMenuButton>
        }
      />
      <CollapsibleContent>
        <SidebarMenuSub>
          {agruparPorSecao(grupo.itens).map(([secao, itens]) => (
            <Fragment key={secao ?? "_"}>
              {/* Rótulo de seção: Governança tem 11 destinos, e lista corrida
                  não separa "quem é a empresa" de "quem pode o quê". */}
              {secao && (
                <li className="mt-2 px-2 pt-1 text-[10px] font-medium uppercase tracking-wider text-sidebar-foreground/45 first:mt-0">
                  {secao}
                </li>
              )}
              {itens.map((item) => (
                <SidebarMenuSubItem key={item.href}>
                  <SidebarMenuSubButton
                    isActive={isItemActive(pathname, item.href)}
                    render={<Link href={item.href} />}
                  >
                    <span>{item.label}</span>
                  </SidebarMenuSubButton>
                </SidebarMenuSubItem>
              ))}
            </Fragment>
          ))}
        </SidebarMenuSub>
      </CollapsibleContent>
    </Collapsible>
  );
}
