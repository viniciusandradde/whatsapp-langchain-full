import { ShieldCheck } from "lucide-react";

import { PageHeader } from "@/components/page-header";
import { ChangePasswordForm } from "@/components/change-password-form";
import { requireSession } from "@/lib/session";

export const dynamic = "force-dynamic";

export default async function SettingsPage() {
  const session = await requireSession();

  return (
    <div className="space-y-6">
      <PageHeader
        titulo="Segurança"
        icon={ShieldCheck}
      />

      <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-4 text-sm text-amber-950">
        No primeiro acesso, o painel pode criar o admin a partir de
        `ADMIN_EMAIL` e `ADMIN_PASSWORD` definidos no ambiente. Depois de
        validar o acesso, altere a senha imediatamente em qualquer ambiente
        compartilhado ou de produção.
      </div>

      <ChangePasswordForm email={session.user.email} />
    </div>
  );
}
