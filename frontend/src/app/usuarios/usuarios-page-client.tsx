"use client";

import { useCallback, useEffect, useState, useTransition } from "react";
import {
  Copy,
  KeyRound,
  Pencil,
  Plus,
  Power,
  PowerOff,
  Search,
  Trash2,
  Users,
} from "lucide-react";
import { toast } from "sonner";

import { ConfirmDestrutivo } from "@/components/confirm-destrutivo";
import { PageHeader } from "@/components/page-header";
import { ApiError } from "@/components/ui/api-error";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { plural } from "@/lib/formato";
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

const STATUS_LABEL: Record<string, string> = {
  todos: "Todos os status",
  active: "Com acesso",
  disabled: "Sem acesso",
};

function formatRelative(iso: string | null): string {
  if (!iso) return "nunca entrou";
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

function iniciais(nome: string | null, email: string | null): string {
  const src = (nome || email || "?").trim();
  const parts = src.split(/\s+/);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }
  return src.slice(0, 2).toUpperCase();
}

/** Ação destrutiva pendente de confirmação — uma por vez. */
type Pendente =
  | { tipo: "reset"; usuario: Usuario }
  | { tipo: "reativar"; usuario: Usuario }
  | { tipo: "remover"; usuario: Usuario };

export function UsuariosPageClient() {
  const [usuarios, setUsuarios] = useState<Usuario[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<
    "todos" | "active" | "disabled"
  >("todos");
  const [pending, startTransition] = useTransition();
  const [editing, setEditing] = useState<Usuario | null>(null);
  const [creating, setCreating] = useState(false);
  const [disabling, setDisabling] = useState<Usuario | null>(null);
  const [cloning, setCloning] = useState<Usuario | null>(null);
  const [confirmando, setConfirmando] = useState<Pendente | null>(null);
  const [senhaGerada, setSenhaGerada] = useState<{
    password: string;
    userName: string;
  } | null>(null);

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

  const nomeDe = (u: Usuario) => u.nome || u.email || u.id;

  function executarPendente() {
    if (!confirmando) return;
    const { tipo, usuario } = confirmando;
    startTransition(async () => {
      if (tipo === "reset") {
        const r = await resetarSenhaUsuarioAction(usuario.id);
        if (r.ok) {
          setSenhaGerada({ password: r.password, userName: nomeDe(usuario) });
        } else {
          toast.error("Não deu pra gerar a senha", { description: r.error });
        }
        return;
      }
      if (tipo === "reativar") {
        const r = await setStatusUsuarioAction(usuario.id, { status: "active" });
        if (r.ok) {
          toast.success(`${nomeDe(usuario)} voltou a ter acesso.`);
          reload();
        } else {
          toast.error("Não deu pra reativar", { description: r.error });
        }
        return;
      }
      const r = await removerUsuarioAction(usuario.id);
      if (r.ok) {
        toast.success(`${nomeDe(usuario)} saiu desta empresa.`);
        reload();
      } else {
        toast.error("Não deu pra remover", { description: r.error });
      }
    });
  }

  const textoConfirmacao: Record<
    Pendente["tipo"],
    {
      titulo: string;
      acao: string;
      tom: "destrutivo" | "serio";
      descricao: React.ReactNode;
    }
  > = {
    reset: {
      titulo: "Gerar uma senha nova?",
      acao: "Gerar senha",
      // Não apaga nada, mas derruba a senha atual na hora — merece a pausa.
      tom: "serio",
      descricao: (
        <p>
          A senha atual para de funcionar imediatamente. A nova aparece uma
          única vez na tela seguinte — copie antes de fechar.
        </p>
      ),
    },
    reativar: {
      titulo: "Devolver o acesso?",
      acao: "Reativar",
      tom: "serio",
      descricao: <p>A pessoa volta a conseguir entrar no painel.</p>,
    },
    remover: {
      titulo: "Remover desta empresa?",
      acao: "Remover",
      tom: "destrutivo",
      descricao: (
        <p>
          Perfis, departamentos, conexões e avatar são apagados junto. O
          histórico de atendimento fica.
        </p>
      ),
    },
  };

  return (
    <div>
      <PageHeader
        titulo="Usuários"
        descricao="Quem entra no painel, o que cada um pode fazer e em que departamento atende."
        icon={Users}
        acoes={
          <Button onClick={() => setCreating(true)}>
            <Plus className="size-4" />
            Novo usuário
          </Button>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar por nome, email ou telefone…"
            className="w-80 pl-9"
            aria-label="Buscar usuários"
          />
        </div>
        <Select
          value={statusFilter}
          onValueChange={(v) => {
            setStatusFilter((v ?? "todos") as typeof statusFilter);
            setOffset(0);
          }}
        >
          <SelectTrigger className="h-9 w-44" aria-label="Filtrar por status">
            {/* Sem a função, o Base UI imprime o VALOR ("todos"), não o
                rótulo — a lista mostra "Todos os status" e o gatilho mostra
                "todos". A função é o contrato pra formatar. */}
            <SelectValue>
              {(v: string | null) => STATUS_LABEL[v ?? "todos"]}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            {Object.entries(STATUS_LABEL).map(([v, label]) => (
              <SelectItem key={v} value={v}>
                {label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {error ? (
        <ApiError error={error} variant="card" />
      ) : loading ? (
        <TabelaEsqueleto />
      ) : usuarios.length === 0 ? (
        <EmptyState
          icon={Users}
          title={
            search || statusFilter !== "todos"
              ? "Nenhum usuário com esse filtro"
              : "Nenhum usuário cadastrado"
          }
          description={
            search || statusFilter !== "todos"
              ? "Ajuste a busca ou volte pra todos os status."
              : "Cadastre a primeira pessoa que vai atender pelo painel."
          }
          action={
            search || statusFilter !== "todos"
              ? {
                  label: "Limpar filtros",
                  onClick: () => {
                    setSearch("");
                    setStatusFilter("todos");
                  },
                }
              : { label: "Novo usuário", onClick: () => setCreating(true) }
          }
        />
      ) : (
        <div className="overflow-hidden rounded-xl border">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Usuário</TableHead>
                  <TableHead>Contato</TableHead>
                  <TableHead>Perfis</TableHead>
                  <TableHead>Departamento</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Último acesso</TableHead>
                  <TableHead className="text-right">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {usuarios.map((u) => (
                  <TableRow key={u.id}>
                    <TableCell>
                      <div className="flex items-center gap-3">
                        <UserAvatar usuario={u} />
                        <div className="min-w-0">
                          <p className="truncate font-medium">
                            {u.nome || (
                              <span className="italic text-muted-foreground">
                                Sem nome
                              </span>
                            )}
                          </p>
                          {u.is_default_empresa && (
                            <p className="text-xs text-muted-foreground">
                              Empresa padrão desta pessoa
                            </p>
                          )}
                        </div>
                      </div>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {u.email && !u.email.endsWith("@no-email.local") ? (
                        <p>{u.email}</p>
                      ) : (
                        <p className="italic">Sem email</p>
                      )}
                      {u.telefone && (
                        <p className="mt-0.5 font-mono">{u.telefone}</p>
                      )}
                    </TableCell>
                    <TableCell>
                      <ListaDeChips
                        itens={u.perfis.map((p) => p.nome)}
                        limite={3}
                        variant="secondary"
                        vazio="Sem perfil"
                      />
                    </TableCell>
                    <TableCell>
                      <ListaDeChips
                        itens={u.departamentos.map((d) => d.nome)}
                        limite={2}
                        variant="outline"
                        vazio="Nenhum"
                      />
                    </TableCell>
                    <TableCell>
                      <StatusBadge usuario={u} />
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {formatRelative(u.last_login_at)}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center justify-end gap-1">
                        <AcaoIcone
                          rotulo="Editar"
                          onClick={() => setEditing(u)}
                        >
                          <Pencil className="size-3.5" />
                        </AcaoIcone>
                        <AcaoIcone
                          rotulo="Gerar nova senha"
                          disabled={pending}
                          onClick={() =>
                            setConfirmando({ tipo: "reset", usuario: u })
                          }
                        >
                          <KeyRound className="size-3.5" />
                        </AcaoIcone>
                        <AcaoIcone
                          rotulo="Clonar usuário"
                          disabled={pending}
                          onClick={() => setCloning(u)}
                        >
                          <Copy className="size-3.5" />
                        </AcaoIcone>
                        <AcaoIcone
                          rotulo={
                            u.status === "active"
                              ? "Desativar acesso"
                              : "Reativar acesso"
                          }
                          disabled={pending}
                          onClick={() =>
                            u.status === "active"
                              ? setDisabling(u)
                              : setConfirmando({ tipo: "reativar", usuario: u })
                          }
                        >
                          {u.status === "active" ? (
                            <PowerOff className="size-3.5 text-destructive" />
                          ) : (
                            <Power className="size-3.5 text-success" />
                          )}
                        </AcaoIcone>
                        <AcaoIcone
                          rotulo="Remover da empresa"
                          disabled={pending}
                          onClick={() =>
                            setConfirmando({ tipo: "remover", usuario: u })
                          }
                        >
                          <Trash2 className="size-3.5 text-destructive" />
                        </AcaoIcone>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          <div className="flex items-center justify-between border-t px-4 py-2 text-xs text-muted-foreground">
            <span>
              {total === 0
                ? "Nenhum usuário"
                : `${offset + 1}–${Math.min(offset + PAGE_SIZE, total)} de ${plural(total, "usuário", "usuários")}`}
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

      {confirmando && (
        <ConfirmDestrutivo
          aberto
          onAbertoChange={(v) => !v && setConfirmando(null)}
          titulo={textoConfirmacao[confirmando.tipo].titulo}
          objeto={nomeDe(confirmando.usuario)}
          descricao={textoConfirmacao[confirmando.tipo].descricao}
          rotuloAcao={textoConfirmacao[confirmando.tipo].acao}
          tom={textoConfirmacao[confirmando.tipo].tom}
          onConfirmar={executarPendente}
        />
      )}

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
              toast.success("Usuário desativado", {
                description: `${plural(transferidos, "atendimento transferido", "atendimentos transferidos")}.`,
              });
            } else {
              toast.success("Usuário desativado.");
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

/**
 * Botão de ícone com tooltip de verdade.
 *
 * Antes era `title=` — que só aparece depois de ~1s parado, não aparece em
 * toque, e não é lido como rótulo por leitor de tela. Com 5 ícones seguidos
 * numa linha de tabela, isso significava adivinhar qual é qual.
 */
function AcaoIcone({
  rotulo,
  onClick,
  disabled,
  children,
}: {
  rotulo: string;
  onClick: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Button
            variant="ghost"
            size="icon"
            aria-label={rotulo}
            disabled={disabled}
            onClick={onClick}
          />
        }
      >
        {children}
      </TooltipTrigger>
      <TooltipContent>{rotulo}</TooltipContent>
    </Tooltip>
  );
}

/** Chips com corte em N e "+X" — perfis e departamentos usam o mesmo. */
function ListaDeChips({
  itens,
  limite,
  variant,
  vazio,
}: {
  itens: string[];
  limite: number;
  variant: "secondary" | "outline";
  vazio: string;
}) {
  if (itens.length === 0) {
    return <span className="text-xs italic text-muted-foreground">{vazio}</span>;
  }
  const excedente = itens.slice(limite);
  return (
    <div className="flex flex-wrap gap-1">
      {itens.slice(0, limite).map((nome) => (
        <Badge key={nome} variant={variant}>
          {nome}
        </Badge>
      ))}
      {excedente.length > 0 && (
        <Tooltip>
          <TooltipTrigger
            render={
              <span className="cursor-default text-xs text-muted-foreground" />
            }
          >
            +{excedente.length}
          </TooltipTrigger>
          <TooltipContent>{excedente.join(", ")}</TooltipContent>
        </Tooltip>
      )}
    </div>
  );
}

function TabelaEsqueleto() {
  return (
    <div className="overflow-hidden rounded-xl border">
      <div className="space-y-px">
        {Array.from({ length: 6 }, (_, i) => (
          <div key={i} className="flex items-center gap-3 px-4 py-3.5">
            <Skeleton className="size-9 shrink-0 rounded-full" />
            <Skeleton className="h-4 w-40" />
            <Skeleton className="ml-auto h-4 w-52" />
            <Skeleton className="h-4 w-20" />
          </div>
        ))}
      </div>
    </div>
  );
}

function UserAvatar({ usuario }: { usuario: Usuario }) {
  const src = usuario.avatar_path || usuario.image_url;
  return (
    <Avatar className="size-9 shrink-0">
      {src ? <AvatarImage src={src} alt="" /> : null}
      <AvatarFallback className="bg-primary/10 text-xs font-medium text-primary">
        {iniciais(usuario.nome, usuario.email)}
      </AvatarFallback>
    </Avatar>
  );
}

function StatusBadge({ usuario }: { usuario: Usuario }) {
  if (usuario.status === "disabled") {
    return <Badge variant="destructive">Sem acesso</Badge>;
  }
  // Ativo é o piso: a pessoa entra no painel. `atendente_status` é a camada
  // de cima e só existe pra quem atende — por isso "Ativo" quando não há.
  const presenca = usuario.atendente_status;
  if (presenca === "online") return <Badge variant="success">Online</Badge>;
  if (presenca === "ausente") return <Badge variant="warning">Ausente</Badge>;
  if (presenca === "pausa") return <Badge variant="warning">Em pausa</Badge>;
  return <Badge variant="outline">Ativo</Badge>;
}
