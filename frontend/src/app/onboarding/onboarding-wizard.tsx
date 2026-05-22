"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowRight,
  Bot,
  Building2,
  Check,
  CheckCircle2,
  Circle,
  Headphones,
  Loader2,
  Rocket,
  Smartphone,
  Sparkles,
  Users,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

import { fetchOnboardingStatusAction } from "./actions";

interface Step {
  id: "empresa" | "conexao" | "agente" | "atendente";
  numero: number;
  titulo: string;
  descricao: string;
  icon: typeof Building2;
  ctaLabel: string;
  ctaHref: string;
  checkKey: "empresa_doc_ok" | "conexoes_ok" | "agentes_ok" | "atendentes_ok";
}

const STEPS: Step[] = [
  {
    id: "empresa",
    numero: 1,
    titulo: "Complete os dados da empresa",
    descricao:
      "Preencha CNPJ (ou CPF), razão social e endereço fiscal. Necessário pra cobrança e nota fiscal.",
    icon: Building2,
    ctaLabel: "Editar empresa",
    ctaHref: "/companies",
    checkKey: "empresa_doc_ok",
  },
  {
    id: "conexao",
    numero: 2,
    titulo: "Conecte seu WhatsApp",
    descricao:
      "Escolha entre WhatsApp Oficial (WABA), Evolution (Baileys) ou Twilio. Sem conexão, seu agente não conversa com clientes.",
    icon: Smartphone,
    ctaLabel: "Criar conexão",
    ctaHref: "/connections",
    checkKey: "conexoes_ok",
  },
  {
    id: "agente",
    numero: 3,
    titulo: "Configure um agente IA",
    descricao:
      "Escolha um template (atendimento, agendamentos, exames…) e personalize o prompt pra seu negócio.",
    icon: Bot,
    ctaLabel: "Configurar agente",
    ctaHref: "/agents",
    checkKey: "agentes_ok",
  },
  {
    id: "atendente",
    numero: 4,
    titulo: "Convide um atendente humano",
    descricao:
      "Quando o agente IA precisa transferir pra alguém de carne e osso, esse user recebe. Pode ser você mesmo no início.",
    icon: Users,
    ctaLabel: "Convidar atendente",
    ctaHref: "/atendentes",
    checkKey: "atendentes_ok",
  },
];

export function OnboardingWizard() {
  const [status, setStatus] = useState<Awaited<ReturnType<typeof fetchOnboardingStatusAction>> | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchOnboardingStatusAction().then((s) => {
      setStatus(s);
      setLoading(false);
    });
  }, []);

  if (loading || !status) {
    return (
      <div className="flex items-center gap-2 p-8 text-muted-foreground">
        <Loader2 className="size-4 animate-spin" /> Verificando seu cadastro…
      </div>
    );
  }

  const checks = {
    empresa_doc_ok: status.empresa_doc_ok,
    conexoes_ok: status.conexoes_count > 0,
    agentes_ok: status.agentes_count > 0,
    atendentes_ok: status.atendentes_count > 0,
  };
  const done = STEPS.filter((s) => checks[s.checkKey]).length;
  const total = STEPS.length;
  const percent = Math.round((done / total) * 100);

  if (status.completo) {
    return (
      <div className="space-y-6 p-2 max-w-2xl mx-auto">
        <div className="flex flex-col items-center gap-4 text-center py-12">
          <div className="flex size-20 items-center justify-center rounded-full bg-emerald-500/15">
            <Rocket className="size-10 text-emerald-500" />
          </div>
          <div className="space-y-1">
            <h1 className="text-2xl font-bold">Tudo pronto! 🎉</h1>
            <p className="text-muted-foreground">
              {status.empresa_nome} está configurada e pronta pra atender.
              Bem-vindo ao Chat Nexus!
            </p>
          </div>
          <Link
            href="/dashboard/atendimento"
            className="inline-flex h-11 items-center justify-center gap-1.5 rounded-md bg-brand-primary px-6 text-sm font-medium text-white hover:bg-brand-primary/90"
          >
            <Headphones className="size-4" />
            Ir pro painel de atendimentos
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6 p-2 max-w-3xl mx-auto">
      {/* Header */}
      <div className="space-y-2">
        <div className="flex items-center gap-2">
          <Sparkles className="size-5 text-brand-primary" />
          <h1 className="text-2xl font-bold">Bem-vindo, {status.empresa_nome}!</h1>
        </div>
        <p className="text-sm text-muted-foreground">
          4 passos rápidos pra você começar a atender pelo WhatsApp com IA.
          Você pode pular e voltar aqui depois quando quiser.
        </p>
      </div>

      {/* Progress */}
      <div className="rounded-xl border border-white/10 bg-obsidian-900 p-4 space-y-2">
        <div className="flex items-center justify-between text-sm">
          <span className="font-medium">
            Progresso: {done} de {total} passos
          </span>
          <span className="text-muted-foreground">{percent}%</span>
        </div>
        <div className="h-2 rounded-full bg-white/5 overflow-hidden">
          <div
            className="h-full bg-emerald-500 transition-all"
            style={{ width: `${percent}%` }}
          />
        </div>
      </div>

      {/* Passos */}
      <div className="space-y-3">
        {STEPS.map((step) => {
          const ok = checks[step.checkKey];
          const Icon = step.icon;
          return (
            <div
              key={step.id}
              className={cn(
                "rounded-xl border p-4 transition-colors",
                ok
                  ? "border-emerald-500/30 bg-emerald-500/5"
                  : "border-white/10 bg-obsidian-900"
              )}
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="flex gap-3 flex-1 min-w-0">
                  <div
                    className={cn(
                      "flex size-10 shrink-0 items-center justify-center rounded-full",
                      ok ? "bg-emerald-500/20" : "bg-white/[0.04]"
                    )}
                  >
                    {ok ? (
                      <CheckCircle2 className="size-5 text-emerald-500" />
                    ) : (
                      <Icon className="size-5 text-muted-foreground" />
                    )}
                  </div>
                  <div className="space-y-1 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="rounded-md bg-white/[0.06] px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                        Passo {step.numero}
                      </span>
                      {ok && (
                        <span className="rounded-md bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide text-emerald-300">
                          <Check className="inline size-2.5" /> Feito
                        </span>
                      )}
                    </div>
                    <p className="font-medium">{step.titulo}</p>
                    <p className="text-xs text-muted-foreground">{step.descricao}</p>
                  </div>
                </div>
                {!ok && (
                  <Link
                    href={step.ctaHref}
                    className="inline-flex h-9 items-center justify-center gap-1.5 rounded-md bg-brand-primary px-4 text-sm font-medium text-white hover:bg-brand-primary/90"
                  >
                    {step.ctaLabel}
                    <ArrowRight className="size-3.5" />
                  </Link>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* Skip */}
      <div className="flex items-center justify-between border-t border-white/5 pt-4">
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <Circle className="size-3" />
          Configurações podem ser feitas a qualquer momento
        </div>
        <Link
          href="/dashboard/atendimento"
          className="inline-flex h-8 items-center justify-center gap-1 rounded-md px-3 text-xs font-medium text-muted-foreground hover:bg-white/5 hover:text-foreground"
        >
          Pular pra agora <ArrowRight className="size-3" />
        </Link>
      </div>
    </div>
  );
}
