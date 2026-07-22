"use client";

import { useEffect, useRef, useState, useTransition } from "react";
import { Camera, History, Save, Star, User, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { AtividadeEvento, Usuario } from "@/lib/api";

import {
  atualizarUsuarioAction,
  criarUsuarioAction,
  loadAtividadeAction,
  loadConexoesOptionsAction,
  loadDepartamentosOptionsAction,
  loadPerfisOptionsAction,
  setMaxParalelosAction,
  uploadAvatarAction,
  type ConexaoOption,
  type DepartamentoOption,
  type PerfilOption,
} from "./actions";

const ACAO_LABEL: Record<string, string> = {
  "member.add": "Adicionado à empresa",
  "member.remove": "Removido da empresa",
  "member.disable": "Desativado",
  "member.enable": "Reativado",
  "role.change": "Cargo alterado",
  "perfil.sync": "Perfis atualizados",
  "depto.sync": "Departamentos atualizados",
  "superadmin.grant": "Superadmin concedido",
  "superadmin.revoke": "Superadmin revogado",
};

interface Props {
  usuario: Usuario | null; // null = criar novo
  onClose: () => void;
  onCreated: (u: Usuario, password: string) => void;
  onUpdated: (u: Usuario) => void;
}

type TabId = "dados" | "acessos" | "atendimento" | "atividade";

interface ConexaoSel {
  id: number;
  is_default: boolean;
}

function _fmtData(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("pt-BR");
}

const INPUT_CLASS =
  "w-full rounded-md border border-foreground/10 bg-obsidian-800 px-3 py-2 text-sm " +
  "placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-brand-primary/30";

export function UsuarioFormModal({ usuario, onClose, onCreated, onUpdated }: Props) {
  const isEdit = usuario !== null;
  const [tab, setTab] = useState<TabId>("dados");
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);

  // Estados controlados
  const [nome, setNome] = useState(usuario?.nome ?? "");
  const [email, setEmail] = useState(
    usuario?.email && !usuario.email.endsWith("@no-email.local")
      ? usuario.email
      : ""
  );
  const [telefone, setTelefone] = useState(usuario?.telefone ?? "");
  const [roleLegacy, setRoleLegacy] = useState<"admin" | "operator" | "viewer">(
    usuario?.role_legacy ?? "operator"
  );
  const [perfisIds, setPerfisIds] = useState<number[]>(
    usuario?.perfis.map((p) => p.id) ?? []
  );
  const [departamentosIds, setDepartamentosIds] = useState<number[]>(
    usuario?.departamentos.map((d) => d.id) ?? []
  );
  const [conexoesSel, setConexoesSel] = useState<ConexaoSel[]>(
    usuario?.conexoes.map((c) => ({ id: c.id, is_default: c.is_default })) ?? []
  );
  const [maxParalelos, setMaxParalelos] = useState<number>(
    usuario?.atendente_max_paralelos ?? 5
  );

  // Opções (lazy load via apiFetch — direto no client via Server Action seria
  // possível, mas /api/perfis e /api/departamentos podem precisar wrapping)
  const [perfisDisponiveis, setPerfisDisponiveis] = useState<PerfilOption[]>([]);
  const [deptsDisponiveis, setDeptsDisponiveis] = useState<DepartamentoOption[]>([]);
  const [conexoesDisponiveis, setConexoesDisponiveis] = useState<ConexaoOption[]>([]);
  const [loadingOptions, setLoadingOptions] = useState(true);

  // Atividade (auditoria) — carregada sob demanda, só no modo edição
  const [atividade, setAtividade] = useState<AtividadeEvento[] | null>(null);
  const [atividadeLoading, setAtividadeLoading] = useState(false);

  // Avatar
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [avatarPreview, setAvatarPreview] = useState<string | null>(
    usuario?.avatar_path ?? usuario?.image_url ?? null
  );
  const [pendingAvatar, setPendingAvatar] = useState<File | null>(null);

  useEffect(() => {
    // Carrega perfis + deptos disponíveis na empresa atual via Server Actions
    let cancelled = false;
    Promise.all([
      loadPerfisOptionsAction(),
      loadDepartamentosOptionsAction(),
      loadConexoesOptionsAction(),
    ])
      .then(([perfisR, deptsR, conexoesR]) => {
        if (cancelled) return;
        if (perfisR.ok) setPerfisDisponiveis(perfisR.data);
        if (deptsR.ok) setDeptsDisponiveis(deptsR.data);
        if (conexoesR.ok) setConexoesDisponiveis(conexoesR.data);
      })
      .finally(() => {
        if (!cancelled) setLoadingOptions(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function togglePerfil(id: number) {
    setPerfisIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  }
  function toggleDepto(id: number) {
    setDepartamentosIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  }
  function toggleConexao(id: number) {
    setConexoesSel((prev) =>
      prev.some((c) => c.id === id)
        ? prev.filter((c) => c.id !== id)
        : [...prev, { id, is_default: prev.length === 0 }]
    );
  }
  function setDefaultConexao(id: number) {
    setConexoesSel((prev) =>
      prev.map((c) => ({ ...c, is_default: c.id === id }))
    );
  }

  function selectTab(id: TabId) {
    setTab(id);
    // Lazy-load da auditoria ao abrir a aba (só edição).
    if (
      id === "atividade" &&
      isEdit &&
      usuario &&
      atividade === null &&
      !atividadeLoading
    ) {
      setAtividadeLoading(true);
      loadAtividadeAction(usuario.id)
        .then((r) => setAtividade(r.ok ? r.data : []))
        .finally(() => setAtividadeLoading(false));
    }
  }

  function handleFilePick(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    if (f.size > 2 * 1024 * 1024) {
      setError("Imagem maior que 2MB");
      return;
    }
    setPendingAvatar(f);
    setAvatarPreview(URL.createObjectURL(f));
  }

  async function uploadPendingAvatar(userId: string): Promise<boolean> {
    if (!pendingAvatar) return true;
    const fd = new FormData();
    fd.set("file", pendingAvatar);
    const r = await uploadAvatarAction(userId, fd);
    if (!r.ok) {
      // Não engole o erro — avisa o admin (user já foi salvo, é não-fatal).
      alert("Usuário salvo, mas falha no upload do avatar: " + r.error);
      return false;
    }
    return true;
  }

  function handleSave() {
    setError(null);
    if (!nome.trim()) {
      setError("Nome é obrigatório.");
      setTab("dados");
      return;
    }

    startTransition(async () => {
      const baseBody = {
        nome: nome.trim(),
        email: email.trim() || null,
        telefone: telefone.trim() || null,
        role_legacy: roleLegacy,
        perfis_ids: perfisIds,
        departamentos_ids: departamentosIds,
        conexoes: conexoesSel,
      };

      if (isEdit && usuario) {
        const r = await atualizarUsuarioAction(usuario.id, baseBody);
        if (!r.ok) {
          setError(r.error);
          return;
        }
        // Capacidade tem endpoint próprio (atendentes).
        if (maxParalelos !== usuario.atendente_max_paralelos) {
          await setMaxParalelosAction(usuario.id, maxParalelos);
        }
        if (pendingAvatar) await uploadPendingAvatar(usuario.id);
        onUpdated(r.data);
      } else {
        const r = await criarUsuarioAction({
          ...baseBody,
          atendente_max_paralelos: maxParalelos,
        });
        if (!r.ok) {
          setError(r.error);
          return;
        }
        if (pendingAvatar) await uploadPendingAvatar(r.usuario.id);
        onCreated(r.usuario, r.password);
      }
    });
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4">
      <div className="w-full max-w-2xl rounded-xl border border-foreground/10 bg-obsidian-900 shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-foreground/10 p-4">
          <h2 className="flex items-center gap-2 text-lg font-semibold">
            <User className="size-4 text-brand-primary" />
            {isEdit ? `Editar — ${usuario.nome || usuario.email}` : "Novo usuário"}
          </h2>
          <Button variant="ghost" size="icon" onClick={onClose}>
            <X className="size-4" />
          </Button>
        </div>

        {/* Tabs */}
        <div className="flex gap-1 border-b border-foreground/10 px-4">
          {(
            [
              { id: "dados" as const, label: "Dados básicos" },
              { id: "acessos" as const, label: "Acessos" },
              { id: "atendimento" as const, label: "Atendimento" },
              ...(isEdit
                ? [{ id: "atividade" as const, label: "Atividade" }]
                : []),
            ]
          ).map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => selectTab(t.id)}
              className={
                "px-3 py-2 text-sm font-medium transition-colors border-b-2 -mb-px " +
                (tab === t.id
                  ? "border-brand-primary text-brand-primary"
                  : "border-transparent text-muted-foreground hover:text-foreground")
              }
            >
              {t.label}
            </button>
          ))}
        </div>

        {/* Body */}
        <div className="p-4 space-y-4">
          {tab === "dados" && (
            <div className="space-y-4">
              {/* Avatar */}
              <div className="flex items-start gap-4">
                <div className="space-y-2">
                  <div className="relative">
                    {avatarPreview ? (
                      <img
                        src={avatarPreview}
                        alt="Avatar"
                        className="size-20 rounded-full object-cover border border-foreground/15"
                      />
                    ) : (
                      <div className="size-20 rounded-full bg-brand-primary/15 border border-brand-primary/30 flex items-center justify-center text-2xl font-medium text-brand-primary">
                        {(nome || email || "?").slice(0, 1).toUpperCase()}
                      </div>
                    )}
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                      className="absolute -bottom-1 -right-1 flex size-7 items-center justify-center rounded-full border border-white/15 bg-brand-primary text-white hover:bg-brand-primary/90"
                      title="Alterar foto"
                    >
                      <Camera className="size-3.5" />
                    </button>
                  </div>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/png,image/jpeg,image/webp,image/gif"
                    onChange={handleFilePick}
                    className="hidden"
                  />
                  <p className="text-[10px] text-muted-foreground text-center">
                    Max 2MB
                  </p>
                </div>
                <div className="flex-1 space-y-3">
                  <Field label="Nome completo" required>
                    <input
                      type="text"
                      value={nome}
                      onChange={(e) => setNome(e.target.value)}
                      placeholder="Maria Silva"
                      className={INPUT_CLASS}
                      disabled={pending}
                    />
                  </Field>
                  <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                    <Field label="Email">
                      <input
                        type="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        placeholder="opcional"
                        className={INPUT_CLASS}
                        disabled={pending}
                      />
                    </Field>
                    <Field label="Telefone">
                      <input
                        type="tel"
                        value={telefone}
                        onChange={(e) => setTelefone(e.target.value)}
                        placeholder="+55 11 99999-9999"
                        className={INPUT_CLASS}
                        disabled={pending}
                      />
                    </Field>
                  </div>
                </div>
              </div>
            </div>
          )}

          {tab === "acessos" && (
            <div className="space-y-4">
              <Field label="Tipo de acesso (legado)" hint="admin = total | operator = padrão | viewer = só leitura">
                <select
                  value={roleLegacy}
                  onChange={(e) => setRoleLegacy(e.target.value as typeof roleLegacy)}
                  className={INPUT_CLASS}
                  disabled={pending}
                >
                  <option value="admin">Administrador</option>
                  <option value="operator">Operador</option>
                  <option value="viewer">Visualizador</option>
                </select>
              </Field>

              {loadingOptions ? (
                <p className="text-xs text-muted-foreground italic">Carregando perfis e departamentos…</p>
              ) : (
                <>
                  <Field label={`Perfis de acesso (${perfisIds.length} selecionados)`}>
                    {perfisDisponiveis.length === 0 ? (
                      <p className="text-xs text-muted-foreground italic">Nenhum perfil cadastrado.</p>
                    ) : (
                      <div className="grid grid-cols-1 gap-1.5 md:grid-cols-2 max-h-48 overflow-y-auto rounded-md border border-foreground/10 p-2">
                        {perfisDisponiveis.map((p) => (
                          <label
                            key={p.id}
                            className="flex items-center gap-2 rounded p-1.5 text-sm cursor-pointer hover:bg-foreground/[0.04]"
                          >
                            <input
                              type="checkbox"
                              checked={perfisIds.includes(p.id)}
                              onChange={() => togglePerfil(p.id)}
                              disabled={pending}
                              className="size-3.5"
                            />
                            <span>{p.nome}</span>
                            {p.is_system && (
                              <span className="text-[10px] text-muted-foreground">(sistema)</span>
                            )}
                          </label>
                        ))}
                      </div>
                    )}
                  </Field>

                  <Field label={`Departamentos (${departamentosIds.length} selecionados)`}>
                    {deptsDisponiveis.length === 0 ? (
                      <p className="text-xs text-muted-foreground italic">Nenhum departamento cadastrado.</p>
                    ) : (
                      <div className="grid grid-cols-1 gap-1.5 md:grid-cols-2 max-h-48 overflow-y-auto rounded-md border border-foreground/10 p-2">
                        {deptsDisponiveis.map((d) => (
                          <label
                            key={d.id}
                            className="flex items-center gap-2 rounded p-1.5 text-sm cursor-pointer hover:bg-foreground/[0.04]"
                          >
                            <input
                              type="checkbox"
                              checked={departamentosIds.includes(d.id)}
                              onChange={() => toggleDepto(d.id)}
                              disabled={pending}
                              className="size-3.5"
                            />
                            <span>{d.nome}</span>
                          </label>
                        ))}
                      </div>
                    )}
                  </Field>
                </>
              )}
            </div>
          )}

          {tab === "atendimento" && (
            <div className="space-y-4">
              <Field
                label="Capacidade (atendimentos simultâneos)"
                hint="Máximo de atendimentos paralelos na distribuição (1–50)."
              >
                <input
                  type="number"
                  min={1}
                  max={50}
                  value={maxParalelos}
                  onChange={(e) =>
                    setMaxParalelos(
                      Math.max(1, Math.min(50, Number(e.target.value) || 1))
                    )
                  }
                  className={INPUT_CLASS + " w-28"}
                  disabled={pending}
                />
              </Field>

              <Field
                label={`Conexões (${conexoesSel.length} atribuídas)`}
                hint="Conexões WhatsApp que o atendente pode usar. A estrela marca a conexão padrão."
              >
                {loadingOptions ? (
                  <p className="text-xs text-muted-foreground italic">Carregando conexões…</p>
                ) : conexoesDisponiveis.length === 0 ? (
                  <p className="text-xs text-muted-foreground italic">Nenhuma conexão cadastrada.</p>
                ) : (
                  <div className="space-y-1 max-h-48 overflow-y-auto rounded-md border border-foreground/10 p-2">
                    {conexoesDisponiveis.map((c) => {
                      const sel = conexoesSel.find((x) => x.id === c.id);
                      return (
                        <div
                          key={c.id}
                          className="flex items-center gap-2 rounded p-1.5 text-sm hover:bg-foreground/[0.04]"
                        >
                          <input
                            type="checkbox"
                            checked={!!sel}
                            onChange={() => toggleConexao(c.id)}
                            disabled={pending}
                            className="size-3.5"
                          />
                          <span className="flex-1 truncate">
                            {c.nome}
                            <span className="ml-1 text-[10px] text-muted-foreground">
                              {c.provider}
                            </span>
                          </span>
                          {sel && (
                            <button
                              type="button"
                              onClick={() => setDefaultConexao(c.id)}
                              title={sel.is_default ? "Conexão padrão" : "Definir como padrão"}
                              className="shrink-0"
                            >
                              <Star
                                className={
                                  "size-4 " +
                                  (sel.is_default
                                    ? "fill-amber-400 text-amber-400"
                                    : "text-muted-foreground hover:text-amber-400")
                                }
                              />
                            </button>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </Field>
            </div>
          )}

          {tab === "atividade" && (
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <History className="size-3.5" />
                Histórico de auditoria deste usuário (quem criou / alterou /
                ativou / desativou).
              </div>
              {atividadeLoading ? (
                <p className="text-xs italic text-muted-foreground">
                  Carregando atividade…
                </p>
              ) : !atividade || atividade.length === 0 ? (
                <p className="text-xs italic text-muted-foreground">
                  Nenhum evento de auditoria registrado.
                </p>
              ) : (
                <ul className="max-h-80 space-y-2 overflow-y-auto">
                  {atividade.map((ev) => (
                    <li
                      key={ev.id}
                      className="border-l-2 border-brand-primary/30 pl-3"
                    >
                      <p className="text-sm">
                        {ACAO_LABEL[ev.action] ?? ev.action}
                      </p>
                      <p className="text-[11px] text-muted-foreground">
                        por {ev.actor_nome ?? ev.actor_user_id} ·{" "}
                        {_fmtData(ev.created_at)}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between border-t border-foreground/10 p-4">
          <div className="text-sm">
            {error && <span className="text-destructive">{error}</span>}
          </div>
          <div className="flex gap-2">
            <Button variant="ghost" onClick={onClose} disabled={pending}>
              Cancelar
            </Button>
            <Button onClick={handleSave} disabled={pending}>
              {pending ? "Salvando…" : (
                <>
                  <Save className="mr-1 size-4" />
                  {isEdit ? "Atualizar" : "Criar usuário"}
                </>
              )}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

function Field({
  label,
  required,
  hint,
  children,
}: {
  label: string;
  required?: boolean;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label className="text-sm font-medium">
        {label}
        {required && <span className="ml-1 text-destructive">*</span>}
      </label>
      {children}
      {hint && <p className="text-[11px] text-muted-foreground">{hint}</p>}
    </div>
  );
}
