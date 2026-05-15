"use client";

/**
 * Modal "Editar permissões" — atribui perfis (RBAC) e departamentos a
 * um member da empresa. UI multi-select simples (checkboxes) com sync
 * via PUT (substitui o set inteiro de uma vez).
 *
 * Sprint Governança RBAC: dispense gradual do `role` legacy
 * (admin/operator/viewer) em favor de perfis granulares + scope por
 * depto (record-level via .own/.all).
 */

import { useEffect, useState, useTransition } from "react";
import { Loader2, Save, Shield, Users, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  getMemberDepartamentos,
  getMemberPerfis,
  setMemberDepartamentos,
  setMemberPerfis,
} from "@/lib/api";

interface PerfilOption {
  id: number;
  nome: string;
  descricao?: string | null;
  is_system?: boolean;
}

interface DepartamentoOption {
  id: number;
  nome: string;
  ativo?: boolean;
}

interface Props {
  empresaId: number;
  userId: string;
  userEmail?: string | null;
  perfis: PerfilOption[];
  departamentos: DepartamentoOption[];
  onClose: () => void;
  onSaved?: () => void;
}

export function EditPermissionsModal({
  empresaId,
  userId,
  userEmail,
  perfis,
  departamentos,
  onClose,
  onSaved,
}: Props) {
  const [loading, setLoading] = useState(true);
  const [perfilIds, setPerfilIds] = useState<Set<number>>(new Set());
  const [deptoIds, setDeptoIds] = useState<Set<number>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [pending, startSave] = useTransition();

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    Promise.all([
      getMemberPerfis(empresaId, userId),
      getMemberDepartamentos(empresaId, userId),
    ])
      .then(([p, d]) => {
        if (cancelled) return;
        setPerfilIds(new Set(p.perfil_ids));
        setDeptoIds(new Set(d.departamento_ids));
      })
      .catch((e) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "Erro ao carregar.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [empresaId, userId]);

  function togglePerfil(id: number) {
    setPerfilIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleDepto(id: number) {
    setDeptoIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function handleSave() {
    setError(null);
    startSave(async () => {
      try {
        await setMemberPerfis(empresaId, userId, [...perfilIds]);
        await setMemberDepartamentos(empresaId, userId, [...deptoIds]);
        if (onSaved) onSaved();
        onClose();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Erro ao salvar.");
      }
    });
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="relative w-full max-w-2xl rounded-lg border border-border bg-background p-6 shadow-xl max-h-[90vh] overflow-y-auto">
        <button
          type="button"
          onClick={onClose}
          className="absolute right-3 top-3 rounded-md p-1 text-muted-foreground hover:bg-muted"
          aria-label="Fechar"
        >
          <X className="size-4" />
        </button>

        <header className="mb-4">
          <h2 className="text-lg font-semibold">Permissões do membro</h2>
          {userEmail && (
            <p className="text-xs text-muted-foreground">{userEmail}</p>
          )}
          <p className="mt-1 font-mono text-[10px] text-muted-foreground">
            {userId}
          </p>
        </header>

        {error && (
          <p className="mb-3 rounded-md border border-destructive/50 bg-destructive/10 p-2 text-xs text-destructive">
            {error}
          </p>
        )}

        {loading ? (
          <div className="flex items-center gap-2 py-8 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            Carregando permissões atuais...
          </div>
        ) : (
          <div className="space-y-5">
            {/* Perfis */}
            <section>
              <div className="mb-2 flex items-center gap-2">
                <Shield className="size-4 text-primary" />
                <h3 className="text-sm font-semibold">Perfis (RBAC)</h3>
                <Badge variant="outline" className="text-[10px]">
                  {perfilIds.size} selecionados
                </Badge>
              </div>
              <p className="mb-2 text-xs text-muted-foreground">
                Cada perfil agrega N permissões. Múltiplos perfis se somam
                (união). Edite perfis em{" "}
                <code className="rounded bg-muted px-1">/settings/perfis</code>.
              </p>
              {perfis.length === 0 ? (
                <p className="text-xs italic text-muted-foreground">
                  Nenhum perfil cadastrado. Crie em /settings/perfis.
                </p>
              ) : (
                <ul className="space-y-1">
                  {perfis.map((p) => (
                    <li key={p.id}>
                      <label className="flex items-center gap-2 rounded-md p-2 text-sm hover:bg-muted/50 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={perfilIds.has(p.id)}
                          onChange={() => togglePerfil(p.id)}
                          className="size-4"
                        />
                        <span className="font-medium">{p.nome}</span>
                        {p.is_system && (
                          <Badge variant="outline" className="text-[10px]">
                            system
                          </Badge>
                        )}
                        {p.descricao && (
                          <span className="text-xs text-muted-foreground">
                            — {p.descricao}
                          </span>
                        )}
                      </label>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {/* Departamentos */}
            <section>
              <div className="mb-2 flex items-center gap-2">
                <Users className="size-4 text-primary" />
                <h3 className="text-sm font-semibold">Departamentos</h3>
                <Badge variant="outline" className="text-[10px]">
                  {deptoIds.size} selecionados
                </Badge>
              </div>
              <p className="mb-2 text-xs text-muted-foreground">
                Define o escopo do user. Quando perfil tem permissão{" "}
                <code className="rounded bg-muted px-1">.own</code>, só vê
                clientes/atendimentos dos deptos selecionados aqui.
              </p>
              {departamentos.length === 0 ? (
                <p className="text-xs italic text-muted-foreground">
                  Nenhum departamento cadastrado.
                </p>
              ) : (
                <ul className="space-y-1">
                  {departamentos.map((d) => (
                    <li key={d.id}>
                      <label className="flex items-center gap-2 rounded-md p-2 text-sm hover:bg-muted/50 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={deptoIds.has(d.id)}
                          onChange={() => toggleDepto(d.id)}
                          className="size-4"
                        />
                        <span>{d.nome}</span>
                        {d.ativo === false && (
                          <Badge variant="outline" className="text-[10px]">
                            inativo
                          </Badge>
                        )}
                      </label>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        )}

        <footer className="mt-6 flex justify-end gap-2 border-t border-border pt-4">
          <Button variant="outline" onClick={onClose} disabled={pending}>
            Cancelar
          </Button>
          <Button onClick={handleSave} disabled={pending || loading}>
            {pending ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Save className="size-4" />
            )}
            Salvar permissões
          </Button>
        </footer>
      </div>
    </div>
  );
}
