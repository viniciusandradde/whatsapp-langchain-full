"use client";

import { useCallback, useEffect, useState, useTransition } from "react";
import {
  Copy,
  KeyRound,
  Loader2,
  Pencil,
  Plus,
  Power,
  PowerOff,
  Search,
  Trash2,
  Users,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { ApiError } from "@/components/ui/api-error";
import type { Usuario } from "@/lib/api";

import {
  loadUsuariosAction,
  removerUsuarioAction,
  resetarSenhaUsuarioAction,
  setStatusUsuarioAction,
} from "./actions";
import { UsuarioFormModal } from "./usuario-form-modal";
import { SenhaGeradaModal } from "./senha-gerada-modal";
import { DisableUsuarioModal } from "./disable-usuario-modal";
import { CloneUsuarioModal } from "./clone-usuario-modal";

const PAGE_SIZE = 20;

function _formatRelative(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  const ms = Date.now() - d.getTime();
  const min = Math.floor(ms / 60000);
  if (min < 1) return "agora";
  if (min < 60) return `${min}min atrás`;
  const h = Math.floor(min / 60);
  if (h < 24) return `${h}h atrás`;
  const days = Math.floor(h / 24);
  if (days < 30) return `${days}d atrás`;
  return d.toLocaleDateString("pt-BR");
}

function _initials(nome: string | null, email: string | null): string {
  const src = (nome || email || "?").trim();
  const parts = src.split(/\s+/);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }
  return src.slice(0, 2).toUpperCase();
}

export function UsuariosPageClient() {
  const [usuarios, setUsuarios] = useState<Usuario[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"todos" | "active" | "disabled">("todos");
  const [pending, startTransition] = useTransition();
  const [editing, setEditing] = useState<Usuario | null>(null);
  const [creating, setCreating] = useState(false);
  const [disabling, setDisabling] = useState<Usuario | null>(null);
  const [cloning, setCloning] = useState<Usuario | null>(null);
  const [senhaGerada, setSenhaGerada] = useState<{ password: string; userName: string } | null>(null);

  // Debounce da busca → reseta paginação ao digitar.
  useEffect(() => {
    const t = setTimeout(() => {
      setDebouncedSearch(search.trim());
      setOffset(0);
    }, 300);
    return () => clearTimeout(t);
  }, [search]);

  // setState só dentro de callbacks async (evita set-state-in-effect do
  // React Compiler). Retorna cleanup que invalida resultados obsoletos.
  const reload = useCallback(() => {
    let alive = true;
    loadUsuariosAction({
      search: debouncedSearch || undefined,
      status: statusFilter === "todos" ? undefined : statusFilter,
      limit: PAGE_SIZE,
      offset,
    })
      .then((r) => {
        if (!alive) return;
        if (r.ok) {
          setUsuarios(r.data.items);
          setTotal(r.data.total);
          setError(null);
        } else {
          setError(new Error(r.error));
        }
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [debouncedSearch, statusFilter, offset]);

  useEffect(() => reload(), [reload]);

  function handleReset(u: Usuario) {
    if (!confirm(`Gerar nova senha pra ${u.nome || u.email}?`)) return;
    startTransition(async () => {
      const r = await resetarSenhaUsuarioAction(u.id);
      if (r.ok) {
        setSenhaGerada({
          password: r.password,
          userName: u.nome || u.email || u.id,
        });
      } else {
        alert("Erro: " + r.error);
      }
    });
  }

  function handleToggleStatus(u: Usuario) {
    if (u.status === "active") {
      // Desativar passa pelo modal (tratamento de atendimentos abertos).
      setDisabling(u);
      return;
    }
    if (!confirm(`Reativar ${u.nome || u.email}?`)) return;
    startTransition(async () => {
      const r = await setStatusUsuarioAction(u.id, { status: "active" });
      if (r.ok) reload();
      else alert("Erro: " + r.error);
    });
  }

  function handleDelete(u: Usuario) {
    if (
      !confirm(
        `Remover ${u.nome || u.email} desta empresa? ` +
          "Perfis, departamentos, conexões e avatar serão apagados."
      )
    )
      return;
    startTransition(async () => {
      const r = await removerUsuarioAction(u.id);
      if (r.ok) reload();
      else alert("Erro: " + r.error);
    });
  }

  const filtered = usuarios;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold">
            <Users className="size-5 text-brand-primary" />
            Usuários
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Gestão completa: criar, editar perfis &amp; departamentos, resetar senha, ativar/desativar.
          </p>
        </div>
        <Button onClick={() => setCreating(true)}>
          <Plus className="mr-1 size-4" />
          Novo usuário
        </Button>
      </div>

      {/* Filtros */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
          <input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar por nome, email ou telefone…"
            className="h-9 w-72 rounded-md border border-white/10 bg-obsidian-800 pl-9 pr-3 text-sm focus:outline-none focus:ring-2 focus:ring-brand-primary/30"
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value as typeof statusFilter)}
          className="h-9 rounded-md border border-white/10 bg-obsidian-800 px-3 text-sm"
        >
          <option value="todos">Todos status</option>
          <option value="active">Ativos</option>
          <option value="disabled">Desativados</option>
        </select>
      </div>

      {/* Conteúdo */}
      {error ? (
        <ApiError error={error} variant="card" />
      ) : loading ? (
        <div className="flex items-center gap-2 p-8 text-muted-foreground">
          <Loader2 className="size-4 animate-spin" /> Carregando usuários…
        </div>
      ) : filtered.length === 0 ? (
        <EmptyState
          icon={Users}
          title={search ? "Nenhum usuário encontrado" : "Nenhum usuário cadastrado"}
          description={
            search
              ? "Ajuste o filtro ou limpe a busca."
              : "Comece adicionando o primeiro usuário pra atender clientes."
          }
          action={search ? undefined : {
            label: "Novo usuário",
            onClick: () => setCreating(true),
          }}
        />
      ) : (
        <div className="overflow-hidden rounded-xl border border-white/10 bg-obsidian-900">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/10 text-xs uppercase tracking-wide text-muted-foreground">
                <th className="px-4 py-3 text-left">Usuário</th>
                <th className="px-4 py-3 text-left">Contato</th>
                <th className="px-4 py-3 text-left">Perfis</th>
                <th className="px-4 py-3 text-left">Depto</th>
                <th className="px-4 py-3 text-left">Status</th>
                <th className="px-4 py-3 text-left">Último acesso</th>
                <th className="px-4 py-3 text-right">Ações</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((u) => (
                <tr key={u.id} className="border-b border-white/5 hover:bg-white/[0.02]">
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      <UserAvatar usuario={u} />
                      <div className="min-w-0">
                        <p className="truncate font-medium">
                          {u.nome || <span className="italic text-muted-foreground">Sem nome</span>}
                        </p>
                        {u.is_default_empresa && (
                          <p className="text-[10px] uppercase tracking-wider text-brand-primary">
                            Default
                          </p>
                        )}
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-xs text-muted-foreground">
                    {u.email && !u.email.endsWith("@no-email.local") ? (
                      <p>{u.email}</p>
                    ) : (
                      <p className="italic">Sem email</p>
                    )}
                    {u.telefone && <p className="font-mono mt-0.5">{u.telefone}</p>}
                  </td>
                  <td className="px-4 py-3">
                    {u.perfis.length === 0 ? (
                      <span className="text-xs text-muted-foreground italic">—</span>
                    ) : (
                      <div className="flex flex-wrap gap-1">
                        {u.perfis.slice(0, 3).map((p) => (
                          <span
                            key={p.id}
                            className="rounded bg-brand-primary/15 px-1.5 py-0.5 text-[11px] text-brand-primary border border-brand-primary/20"
                          >
                            {p.nome}
                          </span>
                        ))}
                        {u.perfis.length > 3 && (
                          <span className="text-[11px] text-muted-foreground">
                            +{u.perfis.length - 3}
                          </span>
                        )}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    {u.departamentos.length === 0 ? (
                      <span className="text-xs text-muted-foreground italic">—</span>
                    ) : (
                      <div className="flex flex-wrap gap-1">
                        {u.departamentos.slice(0, 2).map((d) => (
                          <span
                            key={d.id}
                            className="rounded bg-white/[0.06] px-1.5 py-0.5 text-[11px]"
                          >
                            {d.nome}
                          </span>
                        ))}
                        {u.departamentos.length > 2 && (
                          <span className="text-[11px] text-muted-foreground">
                            +{u.departamentos.length - 2}
                          </span>
                        )}
                      </div>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge usuario={u} />
                  </td>
                  <td className="px-4 py-3 text-xs text-muted-foreground">
                    {_formatRelative(u.last_login_at)}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-1">
                      <Button
                        variant="ghost"
                        size="icon"
                        title="Editar"
                        onClick={() => setEditing(u)}
                      >
                        <Pencil className="size-3.5" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        title="Resetar senha"
                        disabled={pending}
                        onClick={() => handleReset(u)}
                      >
                        <KeyRound className="size-3.5" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        title="Clonar usuário"
                        disabled={pending}
                        onClick={() => setCloning(u)}
                      >
                        <Copy className="size-3.5" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        title={u.status === "active" ? "Desativar" : "Reativar"}
                        disabled={pending}
                        onClick={() => handleToggleStatus(u)}
                      >
                        {u.status === "active" ? (
                          <PowerOff className="size-3.5 text-destructive" />
                        ) : (
                          <Power className="size-3.5 text-emerald-500" />
                        )}
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        title="Remover da empresa"
                        disabled={pending}
                        onClick={() => handleDelete(u)}
                      >
                        <Trash2 className="size-3.5 text-destructive" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* Paginação */}
          <div className="flex items-center justify-between border-t border-white/10 px-4 py-2 text-xs text-muted-foreground">
            <span>
              {total === 0
                ? "0 usuários"
                : `${offset + 1}–${Math.min(offset + PAGE_SIZE, total)} de ${total}`}
            </span>
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                size="sm"
                disabled={offset === 0 || loading}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              >
                Anterior
              </Button>
              <Button
                variant="ghost"
                size="sm"
                disabled={offset + PAGE_SIZE >= total || loading}
                onClick={() => setOffset(offset + PAGE_SIZE)}
              >
                Próxima
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Modais */}
      {(creating || editing) && (
        <UsuarioFormModal
          usuario={editing}
          onClose={() => {
            setCreating(false);
            setEditing(null);
          }}
          onCreated={(usuario, password) => {
            setSenhaGerada({
              password,
              userName: usuario.nome || usuario.email || usuario.id,
            });
            setCreating(false);
            reload();
          }}
          onUpdated={() => {
            setEditing(null);
            reload();
          }}
        />
      )}
      {disabling && (
        <DisableUsuarioModal
          usuario={disabling}
          onClose={() => setDisabling(null)}
          onDone={(transferidos) => {
            setDisabling(null);
            if (transferidos > 0) {
              alert(`Usuário desativado. ${transferidos} atendimento(s) transferido(s).`);
            }
            reload();
          }}
        />
      )}
      {cloning && (
        <CloneUsuarioModal
          origem={cloning}
          onClose={() => setCloning(null)}
          onCloned={(usuario, password) => {
            setCloning(null);
            setSenhaGerada({
              password,
              userName: usuario.nome || usuario.email || usuario.id,
            });
            reload();
          }}
        />
      )}
      {senhaGerada && (
        <SenhaGeradaModal
          password={senhaGerada.password}
          userName={senhaGerada.userName}
          onClose={() => setSenhaGerada(null)}
        />
      )}
    </div>
  );
}

function UserAvatar({ usuario }: { usuario: Usuario }) {
  const src = usuario.avatar_path
    ? usuario.avatar_path
    : usuario.image_url;
  if (src) {
    return (
      <img
        src={src}
        alt={usuario.nome || "Avatar"}
        className="size-9 shrink-0 rounded-full object-cover border border-white/10"
      />
    );
  }
  return (
    <div className="size-9 shrink-0 rounded-full bg-brand-primary/15 border border-brand-primary/30 flex items-center justify-center text-xs font-medium text-brand-primary">
      {_initials(usuario.nome, usuario.email)}
    </div>
  );
}

function StatusBadge({ usuario }: { usuario: Usuario }) {
  if (usuario.status === "disabled") {
    return (
      <span className="inline-flex rounded-md border border-destructive/30 bg-destructive/10 px-2 py-0.5 text-xs text-destructive">
        Desativado
      </span>
    );
  }
  const online = usuario.atendente_status === "online";
  const color = online
    ? "border-emerald-500/40 bg-emerald-500/15 text-emerald-300"
    : usuario.atendente_status === "ausente"
      ? "border-amber-500/40 bg-amber-500/15 text-amber-300"
      : "border-white/10 bg-white/5 text-muted-foreground";
  const label = online
    ? "Online"
    : usuario.atendente_status === "ausente"
      ? "Ausente"
      : usuario.atendente_status === "pausa"
        ? "Em pausa"
        : "Ativo";
  return (
    <span className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs ${color}`}>
      <span
        className={`size-1.5 rounded-full ${
          online
            ? "bg-emerald-400"
            : usuario.atendente_status === "ausente"
              ? "bg-amber-400"
              : "bg-muted-foreground"
        }`}
      />
      {label}
    </span>
  );
}
