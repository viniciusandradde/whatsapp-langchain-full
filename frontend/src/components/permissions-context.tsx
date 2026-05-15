"use client";

/**
 * PermissionsContext — distribui set de permissões do user logado pra
 * toda a árvore de Client Components que precisa filtrar UI por RBAC.
 *
 * Carrega via Server Action `loadMyPermissionsAction` (que envolve
 * `getMyPermissions()` server-only de lib/api.ts). Cache em React state
 * por session — multi-empresa: se admin trocar empresa ativa, o layout
 * deve disparar `refresh()` ou re-mount.
 *
 * Uso típico via hook `usePermission(perm)`.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { loadMyPermissionsAction } from "@/lib/permissions-actions";

interface PermissionsContextValue {
  perms: Set<string>;
  perfis: { id: number; nome: string }[];
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  /**
   * Helper. Reusa semantics do `effective_scope` do backend:
   * pra perm 'cliente.read' retorna true se user tem QUALQUER variante:
   * - cliente.read        (legacy alias)
   * - cliente.read.all
   * - cliente.read.own
   *
   * Aceita string única OU array (OR — qualquer uma serve).
   */
  hasPerm: (perm: string | string[]) => boolean;
}

const PermissionsContext = createContext<PermissionsContextValue | null>(null);

export function PermissionsProvider({
  children,
  /** Permissões iniciais carregadas server-side (evita flash de "sem perm"). */
  initialPerms,
  initialPerfis,
}: {
  children: ReactNode;
  initialPerms?: string[];
  initialPerfis?: { id: number; nome: string }[];
}) {
  const [perms, setPerms] = useState<Set<string>>(
    () => new Set(initialPerms ?? [])
  );
  const [perfis, setPerfis] = useState<{ id: number; nome: string }[]>(
    initialPerfis ?? []
  );
  const [loading, setLoading] = useState(initialPerms === undefined);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    const r = await loadMyPermissionsAction();
    if (r.ok) {
      setPerms(new Set(r.permissoes));
      setPerfis(r.perfis);
    } else {
      setError(r.error);
    }
    setLoading(false);
  }, []);

  // Se não veio initial (sem SSR), carrega no mount.
  useEffect(() => {
    if (initialPerms === undefined) {
      void refresh();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const hasPerm = useCallback(
    (target: string | string[]) => {
      const list = Array.isArray(target) ? target : [target];
      for (const base of list) {
        // Match exato OU variantes .all/.own (legacy alias = .all)
        if (
          perms.has(base) ||
          perms.has(`${base}.all`) ||
          perms.has(`${base}.own`)
        ) {
          return true;
        }
      }
      return false;
    },
    [perms]
  );

  const value = useMemo<PermissionsContextValue>(
    () => ({ perms, perfis, loading, error, refresh, hasPerm }),
    [perms, perfis, loading, error, refresh, hasPerm]
  );

  return (
    <PermissionsContext.Provider value={value}>
      {children}
    </PermissionsContext.Provider>
  );
}

export function usePermissionsContext(): PermissionsContextValue {
  const ctx = useContext(PermissionsContext);
  if (!ctx) {
    // Default permissivo evita crash em árvores fora do Provider (ex:
    // /login). Retorna `hasPerm = () => true` pra não esconder UI sem
    // querer. Em rotas autenticadas, o Provider está presente.
    return {
      perms: new Set(),
      perfis: [],
      loading: false,
      error: null,
      refresh: async () => {},
      hasPerm: () => true,
    };
  }
  return ctx;
}
