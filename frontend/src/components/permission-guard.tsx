"use client";

/**
 * PermissionGuard — esconde (ou substitui) UI que o usuário não pode usar.
 *
 * Padrão trazido do blueprint `one-for-all` (`components/shared/permission-guard`),
 * adaptado ao RBAC do Nexus: a regra continua vindo do
 * `PermissionsContext` (`hasPerm`, com as variantes `.own`/`.all`, e
 * `isSuperadmin`) — este componente só troca o `if` espalhado pela tela por
 * uma marcação declarativa.
 *
 * ```tsx
 * <PermissionGuard requer="campanha.write">
 *   <Button>Nova campanha</Button>
 * </PermissionGuard>
 *
 * <PermissionGuard requer={["cliente.read", "atendimento.read"]} fallback={<SemAcesso />}>
 *   <PainelCliente />
 * </PermissionGuard>
 * ```
 *
 * ⚠️ Isto é UX, não segurança. Esconder o botão não protege o endpoint — quem
 * autoriza de verdade é o `require_permission` no backend. Serve para não
 * oferecer ao operador uma ação que vai voltar 403.
 */

import type { ReactNode } from "react";

import { usePermissionsContext } from "@/components/permissions-context";

interface Props {
  /** Permissão exigida. Array = basta UMA (OR), mesma semântica do `hasPerm`. */
  requer?: string | string[];
  /** Exige superadmin de PLATAFORMA (`auth.user.is_superadmin`). */
  exigeSuperadmin?: boolean;
  /** O que mostrar quando não tem acesso. Padrão: nada. */
  fallback?: ReactNode;
  /** Enquanto as permissões carregam, não pisca o conteúdo nem o fallback. */
  carregando?: ReactNode;
  children: ReactNode;
}

export function PermissionGuard({
  requer,
  exigeSuperadmin = false,
  fallback = null,
  carregando = null,
  children,
}: Props) {
  const { hasPerm, isSuperadmin, loading } = usePermissionsContext();

  if (loading) return <>{carregando}</>;

  const passaSuperadmin = !exigeSuperadmin || isSuperadmin;
  const passaPerm = !requer || hasPerm(requer);

  // Superadmin recebe o catálogo inteiro de permissões, então `hasPerm` já o
  // deixa passar — não há atalho aqui além do gate explícito acima.
  if (!passaSuperadmin || !passaPerm) return <>{fallback}</>;

  return <>{children}</>;
}
