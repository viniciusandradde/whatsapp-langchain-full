"use client";

import { useEffect, useId, useRef, useState, useTransition } from "react";
import { Camera, Loader2, Save, Star, User } from "lucide-react";
import { toast } from "sonner";

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Field,
  FieldDescription,
  FieldError,
  FieldLabel,
} from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { dataHora } from "@/lib/formato";
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
  type ConviteResultado,
  type DepartamentoOption,
  type PerfilOption,
} from "./actions";

const ACAO_LABEL: Record<string, string> = {
  "member.add": "Entrou na empresa",
  "member.remove": "Saiu da empresa",
  "member.disable": "Perdeu o acesso",
  "member.enable": "Recuperou o acesso",
  "role.change": "Cargo alterado",
  "perfil.sync": "Perfis atualizados",
  "depto.sync": "Departamentos atualizados",
  "superadmin.grant": "Virou superadmin",
  "superadmin.revoke": "Deixou de ser superadmin",
};

const CARGO_LABEL: Record<string, string> = {
  admin: "Administrador",
  operator: "Operador",
  viewer: "Visualizador",
};

interface Props {
  usuario: Usuario | null; // null = criar novo
  onClose: () => void;
  onCreated: (u: Usuario, password: string, convite?: ConviteResultado) => void;
  onUpdated: (u: Usuario) => void;
}

type TabId = "dados" | "acessos" | "atendimento" | "atividade";

interface ConexaoSel {
  id: number;
  is_default: boolean;
}

export function UsuarioFormModal({
  usuario,
  onClose,
  onCreated,
  onUpdated,
}: Props) {
  const isEdit = usuario !== null;
  const id = useId();
  const [tab, setTab] = useState<TabId>("dados");
  const [pending, startTransition] = useTransition();
  const [error, setError] = useState<string | null>(null);
  const [erroNome, setErroNome] = useState<string | null>(null);

  const [nome, setNome] = useState(usuario?.nome ?? "");
  const [email, setEmail] = useState(
    usuario?.email && !usuario.email.endsWith("@no-email.local")
      ? usuario.email
      : ""
  );
  const [telefone, setTelefone] = useState(usuario?.telefone ?? "");
  // Convite de acesso por WhatsApp (só no criar): manda um link de uso único
  // pra pessoa criar a própria senha, em vez de o admin repassar a gerada.
  const [enviarConvite, setEnviarConvite] = useState(true);
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

  const [perfisDisponiveis, setPerfisDisponiveis] = useState<PerfilOption[]>([]);
  const [deptsDisponiveis, setDeptsDisponiveis] = useState<DepartamentoOption[]>(
    []
  );
  const [conexoesDisponiveis, setConexoesDisponiveis] = useState<
    ConexaoOption[]
  >([]);
  const [loadingOptions, setLoadingOptions] = useState(true);

  // Auditoria — carregada só ao abrir a aba, e só no modo edição.
  const [atividade, setAtividade] = useState<AtividadeEvento[] | null>(null);
  const [atividadeLoading, setAtividadeLoading] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [avatarPreview, setAvatarPreview] = useState<string | null>(
    usuario?.avatar_path ?? usuario?.image_url ?? null
  );
  const [pendingAvatar, setPendingAvatar] = useState<File | null>(null);

  useEffect(() => {
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

  function togglePerfil(pid: number) {
    setPerfisIds((prev) =>
      prev.includes(pid) ? prev.filter((x) => x !== pid) : [...prev, pid]
    );
  }
  function toggleDepto(did: number) {
    setDepartamentosIds((prev) =>
      prev.includes(did) ? prev.filter((x) => x !== did) : [...prev, did]
    );
  }
  function toggleConexao(cid: number) {
    setConexoesSel((prev) =>
      prev.some((c) => c.id === cid)
        ? prev.filter((c) => c.id !== cid)
        : [...prev, { id: cid, is_default: prev.length === 0 }]
    );
  }
  function setDefaultConexao(cid: number) {
    setConexoesSel((prev) => prev.map((c) => ({ ...c, is_default: c.id === cid })));
  }

  function selectTab(next: TabId) {
    setTab(next);
    if (
      next === "atividade" &&
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
      toast.error("Imagem grande demais", {
        description: "O limite é 2MB. Reduza a foto e tente de novo.",
      });
      return;
    }
    setPendingAvatar(f);
    setAvatarPreview(URL.createObjectURL(f));
  }

  async function uploadPendingAvatar(userId: string) {
    if (!pendingAvatar) return;
    const fd = new FormData();
    fd.set("file", pendingAvatar);
    const r = await uploadAvatarAction(userId, fd);
    if (!r.ok) {
      // O usuário já foi salvo; só a foto falhou. Falha não-fatal, mas o admin
      // precisa saber — senão fica achando que subiu.
      toast.error("Usuário salvo, mas a foto não subiu", {
        description: r.error,
      });
    }
  }

  function handleSave() {
    setError(null);
    setErroNome(null);
    if (!nome.trim()) {
      setErroNome("Informe o nome de quem vai usar esta conta.");
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
        await uploadPendingAvatar(usuario.id);
        toast.success(`${r.data.nome || "Usuário"} atualizado.`);
        onUpdated(r.data);
      } else {
        const r = await criarUsuarioAction(
          {
            ...baseBody,
            atendente_max_paralelos: maxParalelos,
          },
          { enviarConvite: enviarConvite && !!telefone.trim() }
        );
        if (!r.ok) {
          setError(r.error);
          return;
        }
        await uploadPendingAvatar(r.usuario.id);
        onCreated(r.usuario, r.password, r.convite);
      }
    });
  }

  return (
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <User className="size-4 text-primary" />
            {isEdit
              ? `Editar ${usuario.nome || usuario.email}`
              : "Novo usuário"}
          </DialogTitle>
          <DialogDescription>
            {isEdit
              ? "Alterações valem no próximo carregamento de página da pessoa."
              : "A senha é gerada automaticamente e aparece uma única vez ao salvar."}
          </DialogDescription>
        </DialogHeader>

        <Tabs value={tab} onValueChange={(v) => selectTab(v as TabId)}>
          <TabsList>
            <TabsTrigger value="dados">Dados</TabsTrigger>
            <TabsTrigger value="acessos">Acessos</TabsTrigger>
            <TabsTrigger value="atendimento">Atendimento</TabsTrigger>
            {isEdit && <TabsTrigger value="atividade">Atividade</TabsTrigger>}
          </TabsList>

          <TabsContent value="dados" className="space-y-4 pt-2">
            <div className="flex items-start gap-4">
              <div className="space-y-1">
                <div className="relative">
                  <Avatar className="size-20">
                    {avatarPreview ? (
                      <AvatarImage src={avatarPreview} alt="" />
                    ) : null}
                    <AvatarFallback className="bg-primary/10 text-2xl font-medium text-primary">
                      {(nome || email || "?").slice(0, 1).toUpperCase()}
                    </AvatarFallback>
                  </Avatar>
                  <Button
                    type="button"
                    size="icon-sm"
                    className="absolute -bottom-1 -right-1 rounded-full"
                    onClick={() => fileInputRef.current?.click()}
                    aria-label="Escolher foto"
                  >
                    <Camera className="size-3.5" />
                  </Button>
                </div>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/png,image/jpeg,image/webp,image/gif"
                  onChange={handleFilePick}
                  className="hidden"
                />
                <p className="text-center text-xs text-muted-foreground">
                  até 2MB
                </p>
              </div>

              <div className="flex-1 space-y-3">
                <Field>
                  <FieldLabel htmlFor={`${id}-nome`}>Nome completo</FieldLabel>
                  <Input
                    id={`${id}-nome`}
                    value={nome}
                    onChange={(e) => setNome(e.target.value)}
                    placeholder="Maria Silva"
                    aria-invalid={!!erroNome}
                    disabled={pending}
                  />
                  {erroNome ? <FieldError>{erroNome}</FieldError> : null}
                </Field>
                <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
                  <Field>
                    <FieldLabel htmlFor={`${id}-email`}>
                      Email (opcional)
                    </FieldLabel>
                    <Input
                      id={`${id}-email`}
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="maria@empresa.com.br"
                      disabled={pending}
                    />
                  </Field>
                  <Field>
                    <FieldLabel htmlFor={`${id}-telefone`}>
                      WhatsApp (com DDD)
                    </FieldLabel>
                    <Input
                      id={`${id}-telefone`}
                      type="tel"
                      value={telefone}
                      onChange={(e) => setTelefone(e.target.value)}
                      placeholder="+5567999990000"
                      disabled={pending}
                    />
                    <p className="text-xs text-muted-foreground">
                      É para este número que o convite de acesso e os avisos
                      são enviados. Opcional — mas sem ele o convite não sai.
                    </p>
                  </Field>
                  {!isEdit && (
                    <label className="flex items-start gap-2 rounded-md border bg-muted/20 p-3 text-sm">
                      <Checkbox
                        checked={enviarConvite && !!telefone.trim()}
                        disabled={pending || !telefone.trim()}
                        onCheckedChange={(v) => setEnviarConvite(v === true)}
                        className="mt-0.5"
                      />
                      <span>
                        Enviar convite de acesso pelo WhatsApp
                        <span className="mt-0.5 block text-xs text-muted-foreground">
                          A pessoa recebe um link que vale 1 hora e funciona uma
                          única vez, e cria a própria senha. Se o envio falhar,
                          a senha gerada aparece para você repassar como hoje.
                        </span>
                      </span>
                    </label>
                  )}
                </div>
              </div>
            </div>
          </TabsContent>

          <TabsContent value="acessos" className="space-y-4 pt-2">
            <Field>
              <FieldLabel htmlFor={`${id}-cargo`}>Cargo na empresa</FieldLabel>
              <Select
                value={roleLegacy}
                onValueChange={(v) => setRoleLegacy(v as typeof roleLegacy)}
              >
                <SelectTrigger
                  id={`${id}-cargo`}
                  className="w-full"
                  disabled={pending}
                >
                  {/* Sem a função o Base UI imprime o valor cru ("operator"). */}
                  <SelectValue>
                    {(v: string | null) => CARGO_LABEL[v ?? "operator"]}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {Object.entries(CARGO_LABEL).map(([v, label]) => (
                    <SelectItem key={v} value={v}>
                      {label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FieldDescription>
                Define o piso de acesso. Quem precisa de permissão fina recebe
                por perfil, abaixo.
              </FieldDescription>
            </Field>

            {loadingOptions ? (
              <ListaEsqueleto />
            ) : (
              <>
                <CaixaDeSelecao
                  titulo="Perfis de acesso"
                  selecionados={perfisIds.length}
                  vazio="Nenhum perfil cadastrado nesta empresa."
                  itens={perfisDisponiveis.map((p) => ({
                    chave: p.id,
                    rotulo: p.nome,
                    sufixo: p.is_system ? "do sistema" : undefined,
                    marcado: perfisIds.includes(p.id),
                    alternar: () => togglePerfil(p.id),
                  }))}
                  disabled={pending}
                  idPrefixo={`${id}-perfil`}
                />

                <CaixaDeSelecao
                  titulo="Departamentos"
                  selecionados={departamentosIds.length}
                  vazio="Nenhum departamento cadastrado nesta empresa."
                  itens={deptsDisponiveis.map((d) => ({
                    chave: d.id,
                    rotulo: d.nome,
                    marcado: departamentosIds.includes(d.id),
                    alternar: () => toggleDepto(d.id),
                  }))}
                  disabled={pending}
                  idPrefixo={`${id}-depto`}
                />
              </>
            )}
          </TabsContent>

          <TabsContent value="atendimento" className="space-y-4 pt-2">
            <Field>
              <FieldLabel htmlFor={`${id}-cap`}>
                Conversas ao mesmo tempo
              </FieldLabel>
              <Input
                id={`${id}-cap`}
                type="number"
                min={1}
                max={50}
                value={maxParalelos}
                onChange={(e) =>
                  setMaxParalelos(
                    Math.max(1, Math.min(50, Number(e.target.value) || 1))
                  )
                }
                className="w-28"
                disabled={pending}
              />
              <FieldDescription>
                Teto que a distribuição automática respeita ao escolher para
                quem mandar a próxima conversa. De 1 a 50.
              </FieldDescription>
            </Field>

            <div className="space-y-2">
              <div className="flex items-baseline justify-between">
                <Label>Conexões que pode usar</Label>
                <span className="text-xs text-muted-foreground">
                  {conexoesSel.length} de {conexoesDisponiveis.length}
                </span>
              </div>
              {loadingOptions ? (
                <ListaEsqueleto />
              ) : conexoesDisponiveis.length === 0 ? (
                <p className="text-xs italic text-muted-foreground">
                  Nenhuma conexão cadastrada nesta empresa.
                </p>
              ) : (
                <div className="max-h-48 space-y-1 overflow-y-auto rounded-md border p-2">
                  {conexoesDisponiveis.map((c) => {
                    const sel = conexoesSel.find((x) => x.id === c.id);
                    return (
                      <div
                        key={c.id}
                        className="flex items-center gap-2 rounded p-1.5 text-sm hover:bg-accent"
                      >
                        <Checkbox
                          id={`${id}-conexao-${c.id}`}
                          checked={!!sel}
                          onCheckedChange={() => toggleConexao(c.id)}
                          disabled={pending}
                        />
                        <Label
                          htmlFor={`${id}-conexao-${c.id}`}
                          className="flex-1 truncate font-normal"
                        >
                          {c.nome}
                          <span className="ml-1.5 text-xs text-muted-foreground">
                            {c.provider}
                          </span>
                        </Label>
                        {sel && (
                          <Tooltip>
                            <TooltipTrigger
                              render={
                                <button
                                  type="button"
                                  className="shrink-0"
                                  aria-label={
                                    sel.is_default
                                      ? "É a conexão padrão"
                                      : "Tornar a conexão padrão"
                                  }
                                  onClick={() => setDefaultConexao(c.id)}
                                />
                              }
                            >
                              <Star
                                className={
                                  sel.is_default
                                    ? "size-4 fill-warning text-warning"
                                    : "size-4 text-muted-foreground hover:text-warning"
                                }
                              />
                            </TooltipTrigger>
                            <TooltipContent>
                              {sel.is_default
                                ? "Conexão padrão — é por ela que sai o envio quando o atendente não escolhe"
                                : "Tornar esta a conexão padrão"}
                            </TooltipContent>
                          </Tooltip>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </TabsContent>

          {isEdit && (
            <TabsContent value="atividade" className="space-y-2 pt-2">
              <p className="text-xs text-muted-foreground">
                Quem mexeu nesta conta, o que mudou e quando.
              </p>
              {atividadeLoading ? (
                <ListaEsqueleto />
              ) : !atividade || atividade.length === 0 ? (
                <p className="text-xs italic text-muted-foreground">
                  Nada registrado ainda.
                </p>
              ) : (
                <ul className="max-h-80 space-y-2 overflow-y-auto">
                  {atividade.map((ev) => (
                    <li key={ev.id} className="border-l-2 border-primary/30 pl-3">
                      <p className="text-sm">
                        {ACAO_LABEL[ev.action] ?? ev.action}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        por {ev.actor_nome ?? ev.actor_user_id} ·{" "}
                        {dataHora(ev.created_at)}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </TabsContent>
          )}
        </Tabs>

        {error && <p className="text-sm text-destructive">{error}</p>}

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={pending}>
            Cancelar
          </Button>
          <Button onClick={handleSave} disabled={pending}>
            {pending ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Save className="size-4" />
            )}
            {isEdit ? "Salvar" : "Criar usuário"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Lista de checkbox com contador — perfis e departamentos usam a mesma. */
function CaixaDeSelecao({
  titulo,
  selecionados,
  vazio,
  itens,
  disabled,
  idPrefixo,
}: {
  titulo: string;
  selecionados: number;
  vazio: string;
  itens: {
    chave: number;
    rotulo: string;
    sufixo?: string;
    marcado: boolean;
    alternar: () => void;
  }[];
  disabled?: boolean;
  idPrefixo: string;
}) {
  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between">
        <Label>{titulo}</Label>
        <span className="text-xs text-muted-foreground">
          {selecionados} de {itens.length}
        </span>
      </div>
      {itens.length === 0 ? (
        <p className="text-xs italic text-muted-foreground">{vazio}</p>
      ) : (
        <div className="grid max-h-48 grid-cols-1 gap-1.5 overflow-y-auto rounded-md border p-2 md:grid-cols-2">
          {itens.map((it) => (
            <div
              key={it.chave}
              className="flex items-center gap-2 rounded p-1.5 text-sm hover:bg-accent"
            >
              <Checkbox
                id={`${idPrefixo}-${it.chave}`}
                checked={it.marcado}
                onCheckedChange={it.alternar}
                disabled={disabled}
              />
              <Label
                htmlFor={`${idPrefixo}-${it.chave}`}
                className="flex-1 font-normal"
              >
                {it.rotulo}
                {it.sufixo && (
                  <span className="ml-1.5 text-xs text-muted-foreground">
                    {it.sufixo}
                  </span>
                )}
              </Label>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ListaEsqueleto() {
  return (
    <div className="space-y-2 rounded-md border p-2">
      {Array.from({ length: 3 }, (_, i) => (
        <Skeleton key={i} className="h-6 w-full" />
      ))}
    </div>
  );
}
