"use client";

import { useState, useTransition } from "react";
import { Save, User, MapPin, TrendingUp, Globe } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { Cliente, ClienteUpdateInput } from "@/lib/api";

import { updateClienteAction } from "./cliente-form-actions";

interface Props {
  initialCliente: Cliente;
}

type TabId = "dados" | "endereco" | "comercial" | "social";

const TABS: { id: TabId; label: string; icon: typeof User }[] = [
  { id: "dados", label: "Dados", icon: User },
  { id: "endereco", label: "Endereço", icon: MapPin },
  { id: "comercial", label: "Comercial", icon: TrendingUp },
  { id: "social", label: "Social/Outros", icon: Globe },
];

const LIFECYCLE_OPTIONS = [
  { v: "", l: "—" },
  { v: "lead", l: "Lead" },
  { v: "qualified", l: "Qualified" },
  { v: "opportunity", l: "Opportunity" },
  { v: "customer", l: "Customer" },
  { v: "evangelist", l: "Evangelist" },
  { v: "churned", l: "Churned" },
];

const UF_OPTIONS = [
  "AC","AL","AP","AM","BA","CE","DF","ES","GO","MA","MT","MS","MG","PA",
  "PB","PR","PE","PI","RJ","RN","RS","RO","RR","SC","SP","SE","TO",
];

export function ClienteEnrichedForm({ initialCliente }: Props) {
  const [c, setC] = useState(initialCliente);
  const [tab, setTab] = useState<TabId>("dados");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError(null);
    setSuccess(null);
    const fd = new FormData(e.currentTarget);
    const patch: ClienteUpdateInput = {};

    function add<K extends keyof ClienteUpdateInput>(
      key: K,
      value: ClienteUpdateInput[K] | undefined
    ) {
      if (value !== undefined) {
        patch[key] = value;
      }
    }

    function getStr(name: string): string | null {
      const v = fd.get(name);
      if (v === null) return null;
      const s = String(v).trim();
      return s === "" ? null : s;
    }

    function getNum(name: string): number | null {
      const v = getStr(name);
      if (v === null) return null;
      const n = Number(v);
      return Number.isFinite(n) ? n : null;
    }

    // Aba dados
    if (tab === "dados") {
      add("nome", getStr("nome"));
      add("email", getStr("email"));
      add("tipo_pessoa", (getStr("tipo_pessoa") as "PF" | "PJ" | null) ?? null);
      add("cpf", getStr("cpf"));
      add("cnpj", getStr("cnpj"));
      add("rg", getStr("rg"));
      add("razao_social", getStr("razao_social"));
      add("nome_fantasia", getStr("nome_fantasia"));
      add("data_nascimento", getStr("data_nascimento"));
      add("genero", getStr("genero"));
    }
    if (tab === "endereco") {
      add("cep", getStr("cep"));
      add("logradouro", getStr("logradouro"));
      add("numero", getStr("numero"));
      add("complemento", getStr("complemento"));
      add("bairro", getStr("bairro"));
      add("cidade", getStr("cidade"));
      add("uf", getStr("uf"));
      add("pais", getStr("pais") ?? "BR");
    }
    if (tab === "comercial") {
      add("segmento", getStr("segmento"));
      add(
        "lifecycle_stage",
        (getStr("lifecycle_stage") as Cliente["lifecycle_stage"]) ?? null
      );
      add("score", getNum("score"));
      add("source", getStr("source"));
      add("responsavel_user_id", getStr("responsavel_user_id"));
      add("valor_estimado_brl", getNum("valor_estimado_brl"));
      add("notes", getStr("notes"));
    }
    if (tab === "social") {
      add("instagram", getStr("instagram"));
      add("linkedin", getStr("linkedin"));
      add("facebook", getStr("facebook"));
      add("website", getStr("website"));
      add("email_alternativo", getStr("email_alternativo"));
      add("telefone_alternativo", getStr("telefone_alternativo"));
      add("locale", getStr("locale"));
      add("timezone", getStr("timezone"));
      add("avatar_url", getStr("avatar_url"));
    }

    startTransition(async () => {
      const r = await updateClienteAction(c.id, patch);
      if (!r.ok) {
        setError(r.error);
        return;
      }
      setC(r.cliente);
      setSuccess("Salvo.");
    });
  }

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between gap-3">
          <CardTitle className="text-base">Ficha enriquecida (F1.A)</CardTitle>
          {c.lifecycle_stage && (
            <Badge variant="outline">{c.lifecycle_stage}</Badge>
          )}
        </div>

        {/* Tabs nav */}
        <nav className="mt-3 flex flex-wrap gap-1 border-b border-white/[0.06]">
          {TABS.map((t) => {
            const Icon = t.icon;
            const active = tab === t.id;
            return (
              <button
                key={t.id}
                type="button"
                onClick={() => {
                  setTab(t.id);
                  setError(null);
                  setSuccess(null);
                }}
                className={`flex items-center gap-1.5 border-b-2 px-3 py-2 text-sm transition-colors ${
                  active
                    ? "border-brand-primary text-brand-primary"
                    : "border-transparent text-muted-foreground hover:text-foreground"
                }`}
              >
                <Icon className="size-3.5" />
                {t.label}
              </button>
            );
          })}
        </nav>
      </CardHeader>

      <CardContent>
        {error && (
          <p className="mb-3 rounded-md border border-destructive/50 bg-destructive/10 p-3 text-sm text-destructive">
            {error}
          </p>
        )}
        {success && (
          <p className="mb-3 text-sm text-emerald-300">{success}</p>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          {tab === "dados" && (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <FieldText name="nome" label="Nome" defaultValue={c.nome} />
              <FieldText name="email" label="Email" defaultValue={c.email} type="email" />
              <FieldSelect
                name="tipo_pessoa"
                label="Tipo"
                defaultValue={c.tipo_pessoa ?? ""}
                options={[
                  { v: "", l: "—" },
                  { v: "PF", l: "Pessoa Física" },
                  { v: "PJ", l: "Pessoa Jurídica" },
                ]}
              />
              <FieldText
                name="cpf"
                label="CPF"
                defaultValue={c.cpf}
                placeholder="111.444.777-35"
              />
              <FieldText
                name="cnpj"
                label="CNPJ"
                defaultValue={c.cnpj}
                placeholder="11.222.333/0001-81"
              />
              <FieldText name="rg" label="RG" defaultValue={c.rg} />
              <FieldText
                name="razao_social"
                label="Razão social"
                defaultValue={c.razao_social}
              />
              <FieldText
                name="nome_fantasia"
                label="Nome fantasia"
                defaultValue={c.nome_fantasia}
              />
              <FieldText
                name="data_nascimento"
                label="Data nasc."
                defaultValue={c.data_nascimento}
                type="date"
              />
              <FieldText name="genero" label="Gênero" defaultValue={c.genero} />
            </div>
          )}

          {tab === "endereco" && (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <FieldText
                name="cep"
                label="CEP"
                defaultValue={c.cep}
                placeholder="01310-100"
              />
              <FieldSelect
                name="uf"
                label="UF"
                defaultValue={c.uf ?? ""}
                options={[{ v: "", l: "—" }, ...UF_OPTIONS.map((u) => ({ v: u, l: u }))]}
              />
              <FieldText
                name="logradouro"
                label="Logradouro"
                defaultValue={c.logradouro}
                colSpan={2}
              />
              <FieldText name="numero" label="Número" defaultValue={c.numero} />
              <FieldText
                name="complemento"
                label="Complemento"
                defaultValue={c.complemento}
              />
              <FieldText name="bairro" label="Bairro" defaultValue={c.bairro} />
              <FieldText name="cidade" label="Cidade" defaultValue={c.cidade} />
              <FieldText
                name="pais"
                label="País"
                defaultValue={c.pais}
                placeholder="BR"
              />
            </div>
          )}

          {tab === "comercial" && (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <FieldText name="segmento" label="Segmento" defaultValue={c.segmento} />
              <FieldSelect
                name="lifecycle_stage"
                label="Lifecycle stage"
                defaultValue={c.lifecycle_stage ?? ""}
                options={LIFECYCLE_OPTIONS}
              />
              <FieldText
                name="score"
                label="Score (0-100)"
                defaultValue={c.score?.toString() ?? null}
                type="number"
              />
              <FieldText name="source" label="Source" defaultValue={c.source} />
              <FieldText
                name="responsavel_user_id"
                label="Responsável (user_id)"
                defaultValue={c.responsavel_user_id}
                placeholder="UUID"
              />
              <FieldText
                name="valor_estimado_brl"
                label="Valor estimado (R$)"
                defaultValue={c.valor_estimado_brl?.toString() ?? null}
                type="number"
              />
              <div className="md:col-span-2">
                <FieldTextarea
                  name="notes"
                  label="Notas internas"
                  defaultValue={c.notes}
                />
              </div>
            </div>
          )}

          {tab === "social" && (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              <FieldText
                name="instagram"
                label="Instagram"
                defaultValue={c.instagram}
                placeholder="@usuario"
              />
              <FieldText name="linkedin" label="LinkedIn" defaultValue={c.linkedin} />
              <FieldText name="facebook" label="Facebook" defaultValue={c.facebook} />
              <FieldText name="website" label="Website" defaultValue={c.website} />
              <FieldText
                name="email_alternativo"
                label="Email alternativo"
                defaultValue={c.email_alternativo}
                type="email"
              />
              <FieldText
                name="telefone_alternativo"
                label="Telefone alternativo"
                defaultValue={c.telefone_alternativo}
              />
              <FieldText
                name="locale"
                label="Locale"
                defaultValue={c.locale}
                placeholder="pt-BR"
              />
              <FieldText
                name="timezone"
                label="Timezone"
                defaultValue={c.timezone}
                placeholder="America/Sao_Paulo"
              />
              <FieldText
                name="avatar_url"
                label="Avatar URL"
                defaultValue={c.avatar_url}
                colSpan={2}
              />
            </div>
          )}

          <div className="flex justify-end pt-3">
            <Button type="submit" disabled={isPending}>
              <Save className="size-3.5" />
              {isPending ? "Salvando…" : "Salvar"}
            </Button>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}

// ---------- helpers de field ----------

interface FieldProps {
  name: string;
  label: string;
  defaultValue: string | null;
  type?: string;
  placeholder?: string;
  colSpan?: number;
}

function FieldText({
  name,
  label,
  defaultValue,
  type = "text",
  placeholder,
  colSpan,
}: FieldProps) {
  return (
    <div className={colSpan === 2 ? "md:col-span-2" : ""}>
      <label
        htmlFor={name}
        className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground"
      >
        {label}
      </label>
      <input
        id={name}
        name={name}
        type={type}
        defaultValue={defaultValue ?? ""}
        placeholder={placeholder}
        className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
      />
    </div>
  );
}

function FieldTextarea({
  name,
  label,
  defaultValue,
}: {
  name: string;
  label: string;
  defaultValue: string | null;
}) {
  return (
    <div>
      <label
        htmlFor={name}
        className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground"
      >
        {label}
      </label>
      <textarea
        id={name}
        name={name}
        defaultValue={defaultValue ?? ""}
        rows={4}
        className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
      />
    </div>
  );
}

function FieldSelect({
  name,
  label,
  defaultValue,
  options,
}: {
  name: string;
  label: string;
  defaultValue: string;
  options: { v: string; l: string }[];
}) {
  return (
    <div>
      <label
        htmlFor={name}
        className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground"
      >
        {label}
      </label>
      <select
        id={name}
        name={name}
        defaultValue={defaultValue}
        className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
      >
        {options.map((o) => (
          <option key={o.v} value={o.v}>
            {o.l}
          </option>
        ))}
      </select>
    </div>
  );
}
