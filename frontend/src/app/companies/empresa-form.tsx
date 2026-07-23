"use client";

import { useEffect, useState, useTransition } from "react";
import { AlertCircle, Building2, CheckCircle2, Loader2, MapPin } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import type { Empresa, EmpresaCsatConfig, PlanoCatalogo } from "@/lib/api";
import {
  formatCEP,
  formatCPFOrCNPJ,
  isValidCPFOrCNPJ,
  lookupCep,
  onlyDigits,
  slugify,
} from "@/lib/br-validators";

import {
  loadEmpresaCsatAction,
  saveEmpresa,
  saveEmpresaCsatAction,
  uploadEmpresaLogoAction,
} from "./actions";

interface Props {
  initial?: Empresa;
  onDone?: () => void;
}

const INPUT_CLASS =
  "w-full rounded-md border border-foreground/10 bg-obsidian-800 px-3 py-2 text-sm " +
  "placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-brand-primary/30";

const SELECT_CLASS = INPUT_CLASS;
const INPUT_ERROR_CLASS = INPUT_CLASS + " border-destructive/60";

const PLANO_INFO: Record<string, { label: string; descricao: string }> = {
  free: {
    label: "Free",
    descricao: "Até 1 conexão, 1 agente IA, 100 atendimentos/mês. Grátis.",
  },
  pessoal: {
    label: "Pessoal",
    descricao:
      "Uso pessoal/MEI: 1 conexão, 2 usuários, 500 atendimentos/mês, IA com teto US$10. R$ 97/mês.",
  },
  pro: {
    label: "Pro",
    descricao: "Até 3 conexões, 5 agentes IA, 2 mil atendimentos/mês. R$ 299/mês.",
  },
  enterprise: {
    label: "Enterprise",
    descricao: "Conexões/agentes ilimitados, white label, suporte dedicado. R$ 1.499/mês.",
  },
};

const UF_LIST = [
  "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA",
  "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN",
  "RS", "RO", "RR", "SC", "SP", "SE", "TO",
];

type TabId = "basico" | "fiscal" | "endereco" | "plano";

export function EmpresaForm({ initial, onDone }: Props) {
  const [tab, setTab] = useState<TabId>("basico");
  const [isPending, startTransition] = useTransition();
  const [feedback, setFeedback] = useState<
    { kind: "ok" } | { kind: "err"; message: string } | null
  >(null);

  // Estado controlado pra validações cliente-side + auto-slug + ViaCEP
  const [nome, setNome] = useState(initial?.nome ?? "");
  const [slug, setSlug] = useState(initial?.slug ?? "");
  const [slugManual, setSlugManual] = useState(Boolean(initial?.slug));
  const [doc, setDoc] = useState(initial?.doc ?? "");
  const [docTouched, setDocTouched] = useState(false);

  // Endereço fiscal
  const [cep, setCep] = useState(initial?.endereco_fiscal_cep ?? "");
  const [logradouro, setLogradouro] = useState(initial?.endereco_fiscal_logradouro ?? "");
  const [numero, setNumero] = useState(initial?.endereco_fiscal_numero ?? "");
  const [complemento, setComplemento] = useState(initial?.endereco_fiscal_complemento ?? "");
  const [bairro, setBairro] = useState(initial?.endereco_fiscal_bairro ?? "");
  const [cidade, setCidade] = useState(initial?.endereco_fiscal_cidade ?? "");
  const [uf, setUf] = useState(initial?.endereco_fiscal_uf ?? "");
  const [cepLoading, setCepLoading] = useState(false);
  const [cepError, setCepError] = useState<string | null>(null);

  const [plano, setPlano] = useState(initial?.plano ?? "free");
  // Catálogo data-driven (GET /api/billing/planos) — plano novo na tabela
  // aparece aqui sem mexer em código. PLANO_INFO fica só de fallback.
  const [planosCatalogo, setPlanosCatalogo] = useState<PlanoCatalogo[] | null>(
    null
  );
  useEffect(() => {
    import("./actions").then(({ loadPlanosCatalogoAction }) =>
      loadPlanosCatalogoAction().then((r) => {
        if (r.ok && r.data.length > 0) setPlanosCatalogo(r.data);
      })
    );
  }, []);

  // White-label (mig 115)
  const [nomeExibicao, setNomeExibicao] = useState(initial?.nome_exibicao ?? "");
  const [corPrimaria, setCorPrimaria] = useState(initial?.cor_primaria ?? "");
  const [corSecundaria, setCorSecundaria] = useState(
    initial?.cor_secundaria ?? ""
  );
  const [logoFile, setLogoFile] = useState<File | null>(null);
  const [logoPreview, setLogoPreview] = useState<string | null>(
    initial?.logo_path ?? null
  );

  // Auto-gera slug enquanto user digita o nome (até ele editar manualmente)
  useEffect(() => {
    if (!slugManual && !initial) {
      setSlug(slugify(nome));
    }
  }, [nome, slugManual, initial]);

  // Validação doc (CPF/CNPJ) — só erro se touched + non-empty
  const docDigits = onlyDigits(doc);
  const docInvalid = docTouched && doc !== "" && !isValidCPFOrCNPJ(doc);

  async function handleCepBlur(value: string) {
    const d = onlyDigits(value);
    if (d.length !== 8) return;
    setCepLoading(true);
    setCepError(null);
    try {
      const r = await lookupCep(d);
      if (r === null) {
        setCepError("CEP não encontrado.");
      } else {
        if (!logradouro) setLogradouro(r.logradouro);
        if (!bairro) setBairro(r.bairro);
        if (!cidade) setCidade(r.localidade);
        if (!uf) setUf(r.uf);
      }
    } finally {
      setCepLoading(false);
    }
  }

  function handleSubmit(formData: FormData) {
    setFeedback(null);
    // Validações cliente-side antes de enviar
    if (!nome.trim() || !slug.trim()) {
      setFeedback({ kind: "err", message: "Nome e slug são obrigatórios." });
      setTab("basico");
      return;
    }
    if (slug.length < 2) {
      setFeedback({ kind: "err", message: "Slug precisa ter pelo menos 2 caracteres." });
      setTab("basico");
      return;
    }
    if (!/^[a-z0-9][a-z0-9-]*[a-z0-9]$/.test(slug)) {
      setFeedback({
        kind: "err",
        message: "Slug deve conter só letras minúsculas, números e hífens (sem hífen no início/fim).",
      });
      setTab("basico");
      return;
    }
    if (doc.trim() && !isValidCPFOrCNPJ(doc)) {
      setFeedback({ kind: "err", message: "CPF/CNPJ inválido — verifique o dígito verificador." });
      setTab("basico");
      return;
    }
    // Envia
    formData.set("nome", nome.trim());
    formData.set("slug", slug.trim());
    formData.set("plano", plano);
    formData.set("doc", docDigits);
    formData.set("endereco_fiscal_cep", onlyDigits(cep));
    formData.set("endereco_fiscal_logradouro", logradouro.trim());
    formData.set("endereco_fiscal_numero", numero.trim());
    formData.set("endereco_fiscal_complemento", complemento.trim());
    formData.set("endereco_fiscal_bairro", bairro.trim());
    formData.set("endereco_fiscal_cidade", cidade.trim());
    formData.set("endereco_fiscal_uf", uf.trim().toUpperCase());
    // White-label
    formData.set("nome_exibicao", nomeExibicao.trim());
    formData.set("cor_primaria", corPrimaria);
    formData.set("cor_secundaria", corSecundaria);

    startTransition(async () => {
      const result = await saveEmpresa(initial?.id ?? null, formData);
      if (!result.ok) {
        setFeedback({ kind: "err", message: result.error });
        return;
      }
      // Logo é multipart — upload separado após salvar (precisa do id).
      if (logoFile) {
        const fd = new FormData();
        fd.set("file", logoFile);
        const up = await uploadEmpresaLogoAction(result.empresaId, fd);
        if (!up.ok) {
          setFeedback({
            kind: "err",
            message: "Empresa salva, mas falha no upload da logo: " + up.error,
          });
          return;
        }
      }
      setFeedback({ kind: "ok" });
      onDone?.();
    });
  }

  function handleLogoPick(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (!f) return;
    if (f.size > 2 * 1024 * 1024) {
      setFeedback({ kind: "err", message: "Logo maior que 2MB." });
      return;
    }
    setLogoFile(f);
    setLogoPreview(URL.createObjectURL(f));
  }

  const planoInfo = PLANO_INFO[plano] ?? PLANO_INFO.free;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Building2 className="h-4 w-4 text-brand-primary" />
          {initial ? `Editar empresa: ${initial.nome}` : "Nova empresa"}
        </CardTitle>
        <CardDescription>
          Slug é URL-friendly e único global. Quem cria vira admin. Dados
          fiscais opcionais — preencha quando emitir nota.
        </CardDescription>
      </CardHeader>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-foreground/10 px-6">
        {(
          [
            { id: "basico", label: "Básico" },
            { id: "fiscal", label: "Fiscal" },
            { id: "endereco", label: "Endereço" },
            { id: "plano", label: "Plano" },
          ] as { id: TabId; label: string }[]
        ).map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
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

      <form action={handleSubmit}>
        <CardContent className="space-y-4">
          {/* ----- TAB Básico ----- */}
          {tab === "basico" && (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <Field label="Nome fantasia" htmlFor="nome" required>
                <input
                  id="nome"
                  name="nome"
                  required
                  value={nome}
                  onChange={(e) => setNome(e.target.value)}
                  placeholder="Acme Inc"
                  className={INPUT_CLASS}
                  disabled={isPending}
                />
              </Field>

              <Field
                label="Slug"
                htmlFor="slug"
                required
                hint="Auto-gerado a partir do nome. Edite se quiser."
              >
                <input
                  id="slug"
                  name="slug"
                  required
                  minLength={2}
                  value={slug}
                  onChange={(e) => {
                    setSlug(slugify(e.target.value));
                    setSlugManual(true);
                  }}
                  placeholder="acme"
                  className={`${INPUT_CLASS} font-mono`}
                  disabled={isPending}
                />
              </Field>

              <Field
                label="Documento (CPF ou CNPJ)"
                htmlFor="doc"
                hint="Validação automática com dígito verificador."
                error={docInvalid ? "CPF/CNPJ inválido" : null}
              >
                <input
                  id="doc"
                  name="doc"
                  value={formatCPFOrCNPJ(doc)}
                  onChange={(e) => setDoc(e.target.value)}
                  onBlur={() => setDocTouched(true)}
                  placeholder="00.000.000/0000-00 ou 000.000.000-00"
                  className={docInvalid ? INPUT_ERROR_CLASS : INPUT_CLASS}
                  disabled={isPending}
                />
                {!docInvalid && docDigits.length >= 11 && isValidCPFOrCNPJ(doc) && (
                  <p className="mt-1 flex items-center gap-1 text-xs text-emerald-500">
                    <CheckCircle2 className="h-3 w-3" />
                    {docDigits.length === 11 ? "CPF válido" : "CNPJ válido"}
                  </p>
                )}
              </Field>

              {initial && (
                <Field label="Status" htmlFor="status">
                  <select
                    id="status"
                    name="status"
                    defaultValue={initial.status}
                    className={SELECT_CLASS}
                    disabled={isPending}
                  >
                    <option value="active">Active</option>
                    <option value="suspended">Suspended</option>
                    <option value="archived">Archived</option>
                  </select>
                </Field>
              )}

              {/* Identidade visual (white-label) */}
              <div className="space-y-3 rounded-lg border border-foreground/10 bg-obsidian-800/40 p-4 md:col-span-2">
                <p className="text-sm font-medium">
                  Identidade visual{" "}
                  <span className="text-xs font-normal text-muted-foreground">
                    — aparece no topo do menu (white-label)
                  </span>
                </p>
                <div className="flex flex-wrap items-start gap-4">
                  <div className="space-y-2">
                    <div className="flex h-20 w-20 items-center justify-center overflow-hidden rounded-lg border border-foreground/15 bg-obsidian-900">
                      {logoPreview ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={logoPreview}
                          alt="logo"
                          className="h-full w-full object-contain"
                        />
                      ) : (
                        <Building2 className="h-7 w-7 text-muted-foreground" />
                      )}
                    </div>
                    <label className="inline-flex cursor-pointer items-center gap-1 rounded-md border border-foreground/15 px-2 py-1 text-xs hover:bg-foreground/5">
                      <input
                        type="file"
                        accept="image/png,image/jpeg,image/webp,image/gif"
                        onChange={handleLogoPick}
                        className="hidden"
                        disabled={isPending}
                      />
                      Trocar logo
                    </label>
                    <p className="text-[10px] text-muted-foreground">
                      PNG transparente, ≤2MB
                    </p>
                  </div>
                  <div className="grid flex-1 grid-cols-1 gap-3 sm:grid-cols-2">
                    <Field
                      label="Nome de marca"
                      htmlFor="nome_exibicao"
                      hint="Vazio = nome fantasia."
                    >
                      <input
                        id="nome_exibicao"
                        value={nomeExibicao}
                        onChange={(e) => setNomeExibicao(e.target.value)}
                        maxLength={80}
                        placeholder={nome || "Sua Marca"}
                        className={INPUT_CLASS}
                        disabled={isPending}
                      />
                    </Field>
                    <div className="grid grid-cols-2 gap-3">
                      <Field label="Cor primária" htmlFor="cor_primaria">
                        <input
                          type="color"
                          value={corPrimaria || "#f97316"}
                          onChange={(e) => setCorPrimaria(e.target.value)}
                          className="h-10 w-full rounded-md border border-foreground/10 bg-obsidian-800"
                          disabled={isPending}
                        />
                      </Field>
                      <Field label="Cor secundária" htmlFor="cor_secundaria">
                        <input
                          type="color"
                          value={corSecundaria || "#3b82f6"}
                          onChange={(e) => setCorSecundaria(e.target.value)}
                          className="h-10 w-full rounded-md border border-foreground/10 bg-obsidian-800"
                          disabled={isPending}
                        />
                      </Field>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ----- TAB Fiscal ----- */}
          {tab === "fiscal" && (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <Field
                label="Razão social"
                htmlFor="razao_social"
                hint="Nome jurídico (vai na nota fiscal). Pode diferir do nome fantasia."
              >
                <input
                  id="razao_social"
                  name="razao_social"
                  defaultValue={initial?.razao_social ?? ""}
                  placeholder="Acme Tecnologia LTDA"
                  className={INPUT_CLASS}
                  disabled={isPending}
                />
              </Field>

              <Field label="Inscrição estadual" htmlFor="inscricao_estadual">
                <input
                  id="inscricao_estadual"
                  name="inscricao_estadual"
                  defaultValue={initial?.inscricao_estadual ?? ""}
                  placeholder="ISENTO ou número"
                  className={INPUT_CLASS}
                  disabled={isPending}
                />
              </Field>
            </div>
          )}

          {/* ----- TAB Endereço ----- */}
          {tab === "endereco" && (
            <div className="space-y-4">
              <Field
                label="CEP"
                htmlFor="endereco_fiscal_cep"
                hint="Autopreenche logradouro/bairro/cidade/UF via ViaCEP."
                error={cepError}
              >
                <div className="relative">
                  <input
                    id="endereco_fiscal_cep"
                    name="endereco_fiscal_cep"
                    value={formatCEP(cep)}
                    onChange={(e) => setCep(e.target.value)}
                    onBlur={(e) => handleCepBlur(e.target.value)}
                    placeholder="00000-000"
                    maxLength={9}
                    className={cepError ? INPUT_ERROR_CLASS : INPUT_CLASS}
                    disabled={isPending}
                  />
                  {cepLoading && (
                    <Loader2 className="absolute right-3 top-2.5 h-4 w-4 animate-spin text-muted-foreground" />
                  )}
                  {!cepLoading && cidade && (
                    <MapPin className="absolute right-3 top-2.5 h-4 w-4 text-emerald-500" />
                  )}
                </div>
              </Field>

              <div className="grid grid-cols-1 gap-4 md:grid-cols-[3fr_1fr]">
                <Field label="Logradouro" htmlFor="endereco_fiscal_logradouro">
                  <input
                    id="endereco_fiscal_logradouro"
                    name="endereco_fiscal_logradouro"
                    value={logradouro}
                    onChange={(e) => setLogradouro(e.target.value)}
                    placeholder="Av. Paulista"
                    className={INPUT_CLASS}
                    disabled={isPending}
                  />
                </Field>
                <Field label="Número" htmlFor="endereco_fiscal_numero">
                  <input
                    id="endereco_fiscal_numero"
                    name="endereco_fiscal_numero"
                    value={numero}
                    onChange={(e) => setNumero(e.target.value)}
                    placeholder="1000"
                    className={INPUT_CLASS}
                    disabled={isPending}
                  />
                </Field>
              </div>

              <Field label="Complemento" htmlFor="endereco_fiscal_complemento">
                <input
                  id="endereco_fiscal_complemento"
                  name="endereco_fiscal_complemento"
                  value={complemento}
                  onChange={(e) => setComplemento(e.target.value)}
                  placeholder="Sala 501, Bloco B (opcional)"
                  className={INPUT_CLASS}
                  disabled={isPending}
                />
              </Field>

              <div className="grid grid-cols-1 gap-4 md:grid-cols-[2fr_2fr_1fr]">
                <Field label="Bairro" htmlFor="endereco_fiscal_bairro">
                  <input
                    id="endereco_fiscal_bairro"
                    name="endereco_fiscal_bairro"
                    value={bairro}
                    onChange={(e) => setBairro(e.target.value)}
                    placeholder="Bela Vista"
                    className={INPUT_CLASS}
                    disabled={isPending}
                  />
                </Field>
                <Field label="Cidade" htmlFor="endereco_fiscal_cidade">
                  <input
                    id="endereco_fiscal_cidade"
                    name="endereco_fiscal_cidade"
                    value={cidade}
                    onChange={(e) => setCidade(e.target.value)}
                    placeholder="São Paulo"
                    className={INPUT_CLASS}
                    disabled={isPending}
                  />
                </Field>
                <Field label="UF" htmlFor="endereco_fiscal_uf">
                  <select
                    id="endereco_fiscal_uf"
                    name="endereco_fiscal_uf"
                    value={uf}
                    onChange={(e) => setUf(e.target.value)}
                    className={SELECT_CLASS}
                    disabled={isPending}
                  >
                    <option value="">--</option>
                    {UF_LIST.map((u) => (
                      <option key={u} value={u}>{u}</option>
                    ))}
                  </select>
                </Field>
              </div>
            </div>
          )}

          {/* ----- TAB Plano ----- */}
          {tab === "plano" && (
            <div className="space-y-3">
              <Field label="Plano" htmlFor="plano">
                <select
                  id="plano"
                  name="plano"
                  value={plano}
                  onChange={(e) => setPlano(e.target.value)}
                  className={SELECT_CLASS}
                  disabled={isPending}
                >
                  {planosCatalogo ? (
                    planosCatalogo.map((p) => (
                      <option key={p.slug} value={p.slug}>
                        {p.nome} —{" "}
                        {p.preco_mensal_brl
                          ? `R$ ${p.preco_mensal_brl.toFixed(0)}/mês`
                          : "R$ 0"}
                      </option>
                    ))
                  ) : (
                    <>
                      <option value="free">Free — R$ 0</option>
                      <option value="pessoal">Pessoal — R$ 97/mês</option>
                      <option value="pro">Pro — R$ 299/mês</option>
                      <option value="enterprise">Enterprise — R$ 1.499/mês</option>
                    </>
                  )}
                </select>
              </Field>

              <div className="rounded-md border border-foreground/10 bg-obsidian-800/50 p-3 text-sm">
                <p className="font-medium text-foreground">
                  {planosCatalogo?.find((p) => p.slug === plano)?.nome ??
                    planoInfo.label}
                </p>
                <p className="mt-1 text-muted-foreground">
                  {planosCatalogo?.find((p) => p.slug === plano)?.descricao ??
                    planoInfo.descricao}
                </p>
                <p className="mt-2 text-xs text-amber-500">
                  ⚠️ Billing (ASAAS) ainda não integrado — plano hoje é só
                  display. Cobranca real entra na próxima sprint.
                </p>
              </div>
            </div>
          )}
        </CardContent>

        <CardFooter className="flex flex-col items-stretch gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div aria-live="polite" className="text-sm flex items-center gap-1">
            {feedback?.kind === "ok" && (
              <>
                <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                <span className="text-emerald-500">Salvo com sucesso.</span>
              </>
            )}
            {feedback?.kind === "err" && (
              <>
                <AlertCircle className="h-4 w-4 text-destructive" />
                <span className="text-destructive">{feedback.message}</span>
              </>
            )}
          </div>
          <Button type="submit" disabled={isPending}>
            {isPending ? "Salvando…" : initial ? "Atualizar empresa" : "Criar empresa"}
          </Button>
        </CardFooter>
      </form>
    </Card>
  );
}

function Field({
  label,
  htmlFor,
  required,
  hint,
  error,
  children,
}: {
  label: string;
  htmlFor: string;
  required?: boolean;
  hint?: string;
  error?: string | null;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={htmlFor} className="text-sm font-medium">
        {label}
        {required && <span className="ml-1 text-destructive">*</span>}
      </label>
      {children}
      {hint && !error && (
        <p className="text-xs text-muted-foreground">{hint}</p>
      )}
      {error && (
        <p className="flex items-center gap-1 text-xs text-destructive">
          <AlertCircle className="h-3 w-3" />
          {error}
        </p>
      )}
    </div>
  );
}

// Sprint Y — section CSAT/NPS dentro do edit empresa
const DEFAULT_PERGUNTA = "Como você avalia o atendimento que acabou de receber?";
const DEFAULT_AGRADECIMENTO = "Obrigado pelo seu feedback! 😊";

export function CsatConfigSection({ empresaId }: { empresaId: number }) {
  const [config, setConfig] = useState<EmpresaCsatConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, startSaving] = useTransition();
  const [feedback, setFeedback] = useState<
    { kind: "ok" } | { kind: "err"; message: string } | null
  >(null);

  useEffect(() => {
    setLoading(true);
    loadEmpresaCsatAction(empresaId)
      .then((r) => {
        if (r.ok) setConfig(r.config);
      })
      .finally(() => setLoading(false));
  }, [empresaId]);

  if (loading || config === null) {
    return (
      <Card className="mt-4">
        <CardContent className="py-6 text-sm text-muted-foreground">
          Carregando config NPS…
        </CardContent>
      </Card>
    );
  }

  function handleSubmit(formData: FormData) {
    setFeedback(null);
    const body: EmpresaCsatConfig = {
      csat_ativo: formData.get("csat_ativo") === "on",
      csat_pergunta: String(formData.get("csat_pergunta") || "").trim() || null,
      csat_msg_agradecimento:
        String(formData.get("csat_msg_agradecimento") || "").trim() || null,
      csat_solicita_comentario:
        formData.get("csat_solicita_comentario") === "on",
    };
    startSaving(async () => {
      const r = await saveEmpresaCsatAction(empresaId, body);
      if (r.ok) {
        setConfig(r.config);
        setFeedback({ kind: "ok" });
      } else {
        setFeedback({ kind: "err", message: r.error });
      }
    });
  }

  return (
    <Card className="mt-4">
      <CardHeader>
        <CardTitle className="text-base">Pesquisa de Satisfação (NPS)</CardTitle>
        <CardDescription>
          Quando ativada, o cliente recebe uma pergunta com nota 0-10 ao
          fim de cada atendimento. Resultados em /dashboard/qualidade.
        </CardDescription>
      </CardHeader>
      <form action={handleSubmit}>
        <CardContent className="space-y-4">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              name="csat_ativo"
              defaultChecked={config.csat_ativo}
              disabled={saving}
            />
            <span className="font-medium">Ativar pesquisa NPS</span>
          </label>

          <Field label="Pergunta enviada ao cliente" htmlFor="csat_pergunta">
            <textarea
              id="csat_pergunta"
              name="csat_pergunta"
              rows={2}
              defaultValue={config.csat_pergunta ?? ""}
              placeholder={DEFAULT_PERGUNTA}
              className={INPUT_CLASS}
              disabled={saving}
            />
            <p className="mt-1 text-xs text-muted-foreground">
              Vazio = usa o texto padrão.
            </p>
          </Field>

          <Field
            label="Mensagem de agradecimento (após nota/comentário)"
            htmlFor="csat_msg_agradecimento"
          >
            <textarea
              id="csat_msg_agradecimento"
              name="csat_msg_agradecimento"
              rows={2}
              defaultValue={config.csat_msg_agradecimento ?? ""}
              placeholder={DEFAULT_AGRADECIMENTO}
              className={INPUT_CLASS}
              disabled={saving}
            />
          </Field>

          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              name="csat_solicita_comentario"
              defaultChecked={config.csat_solicita_comentario}
              disabled={saving}
            />
            <span>Pedir comentário textual após a nota (60s pra responder)</span>
          </label>
        </CardContent>
        <CardFooter className="flex items-center justify-between gap-2">
          <div className="text-sm">
            {feedback?.kind === "ok" && (
              <span className="text-green-500">Salvo.</span>
            )}
            {feedback?.kind === "err" && (
              <span className="text-destructive">{feedback.message}</span>
            )}
          </div>
          <Button type="submit" disabled={saving}>
            {saving ? "Salvando…" : "Salvar config NPS"}
          </Button>
        </CardFooter>
      </form>
    </Card>
  );
}

export function ResumoDiarioSection({ empresaId }: { empresaId: number }) {
  const [config, setConfig] =
    useState<import("@/lib/api").EmpresaResumoDiarioConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, startSaving] = useTransition();
  const [feedback, setFeedback] = useState<
    { kind: "ok" } | { kind: "err"; message: string } | null
  >(null);

  useEffect(() => {
    setLoading(true);
    import("./actions").then(({ loadResumoDiarioAction }) =>
      loadResumoDiarioAction(empresaId)
        .then((r) => {
          if (r.ok) setConfig(r.config);
        })
        .finally(() => setLoading(false))
    );
  }, [empresaId]);

  if (loading || config === null) {
    return (
      <Card className="mt-4">
        <CardContent className="py-6 text-sm text-muted-foreground">
          Carregando config do resumo diário…
        </CardContent>
      </Card>
    );
  }

  const DIAS = [
    { n: 1, label: "Seg" },
    { n: 2, label: "Ter" },
    { n: 3, label: "Qua" },
    { n: 4, label: "Qui" },
    { n: 5, label: "Sex" },
    { n: 6, label: "Sáb" },
    { n: 7, label: "Dom" },
  ];

  function toggleDia(n: number) {
    if (!config) return;
    const dias = config.resumo_diario_dias.includes(n)
      ? config.resumo_diario_dias.filter((d) => d !== n)
      : [...config.resumo_diario_dias, n].sort();
    setConfig({ ...config, resumo_diario_dias: dias });
  }

  function handleSave() {
    if (!config) return;
    setFeedback(null);
    startSaving(async () => {
      const { saveResumoDiarioAction } = await import("./actions");
      const r = await saveResumoDiarioAction(empresaId, config);
      if (r.ok) {
        setConfig(r.config);
        setFeedback({ kind: "ok" });
      } else {
        setFeedback({ kind: "err", message: r.error });
      }
    });
  }

  return (
    <Card className="mt-4">
      <CardHeader>
        <CardTitle className="text-base">
          Resumo diário por WhatsApp
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">
          Envia, no horário configurado, um resumo dos atendimentos do dia
          (novos, resolvidos, pendentes) pro número abaixo — saindo pela
          conexão padrão da empresa.
        </p>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={config.resumo_diario_ativo}
            onChange={(e) =>
              setConfig({ ...config, resumo_diario_ativo: e.target.checked })
            }
          />
          Ativar resumo diário
        </label>
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <div>
            <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
              Telefone de destino
            </label>
            <input
              type="tel"
              value={config.resumo_diario_telefone ?? ""}
              onChange={(e) =>
                setConfig({
                  ...config,
                  resumo_diario_telefone: e.target.value || null,
                })
              }
              placeholder="+5567999068963"
              className="h-9 w-full rounded-md border bg-background px-3 font-mono text-sm"
            />
          </div>
          <div>
            <label className="mb-1 block text-xs uppercase tracking-wide text-muted-foreground">
              Horário (fuso {config.resumo_diario_tz})
            </label>
            <input
              type="time"
              value={config.resumo_diario_horario}
              onChange={(e) =>
                setConfig({ ...config, resumo_diario_horario: e.target.value })
              }
              className="h-9 w-full rounded-md border bg-background px-3 text-sm"
            />
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          {DIAS.map((d) => (
            <button
              key={d.n}
              type="button"
              onClick={() => toggleDia(d.n)}
              className={`rounded-md border px-2.5 py-1 text-xs ${
                config.resumo_diario_dias.includes(d.n)
                  ? "border-brand-primary bg-brand-primary/15 text-brand-primary"
                  : "border-border text-muted-foreground"
              }`}
            >
              {d.label}
            </button>
          ))}
        </div>
        {feedback?.kind === "ok" && (
          <p className="text-sm text-emerald-500">Configuração salva.</p>
        )}
        {feedback?.kind === "err" && (
          <p className="text-sm text-destructive">{feedback.message}</p>
        )}
        <Button onClick={handleSave} disabled={saving}>
          {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          Salvar resumo diário
        </Button>
      </CardContent>
    </Card>
  );
}
