import { LoginForm } from "@/components/login-form";
import { getBootstrapAdminEmail } from "@/lib/admin-defaults";
import { ensureDefaultAdmin } from "@/lib/bootstrap-admin";
import { configCaptcha } from "@/lib/captcha";
import { ensureFrontendRuntimeConfig } from "@/lib/runtime-config";

export const dynamic = "force-dynamic";

export default async function LoginPage() {
  ensureFrontendRuntimeConfig();

  const bootstrap = await ensureDefaultAdmin();
  const helperMessage =
    bootstrap.userCount === 0 && !bootstrap.bootstrapConfigured
      ? "Primeiro acesso: defina ADMIN_EMAIL e ADMIN_PASSWORD no ambiente e recarregue esta página."
      : undefined;

  return (
    <LoginForm
      // Pré-preencher o e-mail SÓ no primeiríssimo acesso (admin recém-criado
      // com o banco vazio). Fora disso o campo vem vazio: a página de login é
      // pública e pré-carregar o ADMIN_EMAIL vazava o e-mail do admin pra
      // qualquer visitante.
      defaultEmail={
        bootstrap.bootstrapped
          ? bootstrap.bootstrapEmail || getBootstrapAdminEmail()
          : ""
      }
      defaultPassword=""
      showBootstrapHint={bootstrap.bootstrapped}
      helperMessage={helperMessage}
      // Site key lida no servidor em runtime (não NEXT_PUBLIC_: o build do CI
      // não a tem e a inlinaria vazia). Sem ela o formulário nem carrega o
      // script do Google.
      recaptchaSiteKey={configCaptcha()?.siteKey ?? null}
    />
  );
}
