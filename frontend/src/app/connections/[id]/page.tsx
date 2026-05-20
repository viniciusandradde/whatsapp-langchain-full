import { notFound } from "next/navigation";
import Link from "next/link";
import { ChevronLeft, FileCheck, Smartphone } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { getConexao } from "@/lib/api";
import { requireSession } from "@/lib/session";

export const dynamic = "force-dynamic";

interface PageProps {
  params: Promise<{ id: string }>;
}

const PROVIDER_LABEL: Record<string, string> = {
  twilio_sandbox: "Twilio Sandbox",
  twilio_prod: "Twilio Produção",
  waba: "WhatsApp Oficial (Meta)",
  evolution: "Evolution API",
};

const STATE_LABEL: Record<string, string> = {
  pending: "Pendente",
  qr_pending: "Aguardando QR",
  connecting: "Conectando",
  open: "Conectado",
  ready: "Pronto",
  disconnected: "Desconectado",
  error: "Erro",
};

export default async function ConexaoDetailPage({ params }: PageProps) {
  await requireSession();
  const { id } = await params;
  const conexaoId = parseInt(id, 10);
  if (isNaN(conexaoId)) notFound();

  let conexao;
  let error: string | null = null;
  try {
    conexao = await getConexao(conexaoId);
  } catch (e) {
    error = e instanceof Error ? e.message : "Erro ao carregar conexão.";
  }

  if (error || !conexao) {
    return (
      <div className="space-y-4">
        <Link
          href="/connections"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:underline"
        >
          <ChevronLeft className="h-4 w-4" />
          Voltar
        </Link>
        <div className="rounded-lg border border-destructive/50 bg-destructive/10 p-4 text-sm text-destructive">
          {error || "Conexão não encontrada."}
        </div>
      </div>
    );
  }

  const isWABA = conexao.provider === "waba";

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link
          href="/connections"
          className="inline-flex h-7 w-7 items-center justify-center rounded-md hover:bg-muted/30"
        >
          <ChevronLeft className="h-4 w-4" />
        </Link>
        <Smartphone className="h-6 w-6" />
        <h1 className="text-2xl font-semibold">
          {conexao.display_name || conexao.from_number || `Conexão #${conexao.id}`}
        </h1>
      </div>

      <div className="rounded-lg border border-border/40 p-4 space-y-3">
        <div className="grid grid-cols-2 gap-4 text-sm">
          <Field label="Provider" value={PROVIDER_LABEL[conexao.provider] || conexao.provider} />
          <Field
            label="Estado"
            value={
              <Badge variant="outline">
                {STATE_LABEL[conexao.connection_state || "pending"] || conexao.connection_state}
              </Badge>
            }
          />
          <Field
            label="Número"
            value={
              conexao.from_number?.startsWith("evolution:")
                ? <span className="text-muted-foreground italic">aguardando conexão</span>
                : conexao.from_number
            }
          />
          <Field label="Agente padrão" value={conexao.default_agent_id || "—"} />
          <Field label="Tipo atendimento" value={conexao.tipo_atendimento || "ia"} />
          <Field label="Padrão" value={conexao.is_default ? "Sim" : "Não"} />
          {isWABA && conexao.waba_account_id && (
            <>
              <Field label="WABA Account" value={conexao.waba_account_description || conexao.waba_account_id} />
              <Field label="Phone ID" value={conexao.waba_phone_id || "—"} />
            </>
          )}
          <Field
            label="Último health-check"
            value={
              conexao.ultimo_health_check_at
                ? `${conexao.ultimo_health_check_ok ? "✓" : "✗"} ${new Date(conexao.ultimo_health_check_at).toLocaleString("pt-BR")}`
                : "—"
            }
          />
          <Field label="Criada em" value={new Date(conexao.created_at).toLocaleString("pt-BR")} />
        </div>

        {conexao.state_message && (
          <div className="rounded-md border border-amber-500/30 bg-amber-500/5 p-2 text-xs text-amber-300">
            {conexao.state_message}
          </div>
        )}
      </div>

      {isWABA && (
        <Link
          href={`/connections/${conexao.id}/templates`}
          className="flex items-center gap-3 rounded-lg border border-border/40 p-4 hover:bg-muted/20"
        >
          <FileCheck className="h-5 w-5 text-emerald-400" />
          <div className="flex-1">
            <div className="font-medium">Templates HSM</div>
            <p className="text-xs text-muted-foreground">
              Mensagens template aprovadas pela Meta — necessárias pra enviar fora da janela 24h.
            </p>
          </div>
        </Link>
      )}

      <div className="flex items-center justify-end gap-2">
        <Link
          href="/connections"
          className="inline-flex h-9 items-center justify-center rounded-md border border-border/40 px-4 text-sm hover:bg-muted/20"
        >
          Voltar
        </Link>
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-0.5">{value}</div>
    </div>
  );
}
