import { LoginForm } from "@/components/login-form";
import { getBootstrapAdminEmail } from "@/lib/admin-defaults";
import { ensureDefaultAdmin } from "@/lib/bootstrap-admin";
import { ensureFrontendRuntimeConfig } from "@/lib/runtime-config";

export const dynamic = "force-dynamic";

export default async function LoginPage() {
  ensureFrontendRuntimeConfig();

  const bootstrap = await ensureDefaultAdmin();
  const helperMessage =
    bootstrap.userCount === 0 && !bootstrap.bootstrapConfigured
      ? "Primeiro acesso: defina ADMIN_EMAIL e ADMIN_PASSWORD no ambiente e recarregue esta página."
      : undefined;

  // Google SSO: se backend tem GOOGLE_OAUTH_CLIENT_ID configurado, expõe
  // botão "Entrar com Google" (E1.9). O Better Auth lê a mesma var
  // server-side; aqui só passa flag pra UI mostrar o botão.
  const googleEnabled = Boolean(process.env.GOOGLE_OAUTH_CLIENT_ID);

  return (
    <LoginForm
      defaultEmail={
        bootstrap.bootstrapConfigured
          ? bootstrap.bootstrapEmail || getBootstrapAdminEmail()
          : ""
      }
      defaultPassword=""
      showBootstrapHint={bootstrap.bootstrapped}
      helperMessage={helperMessage}
      googleEnabled={googleEnabled}
    />
  );
}
