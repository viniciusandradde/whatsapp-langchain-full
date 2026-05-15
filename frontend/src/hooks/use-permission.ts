"use client";

/**
 * Hook `usePermission` — açúcar pra `usePermissionsContext().hasPerm()`.
 *
 * Uso:
 *   const canEdit = usePermission("cliente.write");
 *   if (canEdit) <Button>Editar</Button>
 *
 *   // OR (qualquer uma serve):
 *   const canSee = usePermission(["cliente.read", "atendimento.read"]);
 *
 *   // AND (todas precisam):
 *   const canManage = useAllPermissions(["empresa.update", "perfil.write"]);
 */

import { usePermissionsContext } from "@/components/permissions-context";

export function usePermission(perm: string | string[]): boolean {
  const { hasPerm } = usePermissionsContext();
  return hasPerm(perm);
}

export function useAllPermissions(perms: string[]): boolean {
  const { hasPerm } = usePermissionsContext();
  return perms.every((p) => hasPerm(p));
}

export function usePermissionsState() {
  return usePermissionsContext();
}
