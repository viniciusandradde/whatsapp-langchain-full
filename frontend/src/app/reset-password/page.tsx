import { Suspense } from "react";

import { ResetPasswordForm } from "./reset-password-form";

/**
 * Destino do link de definição de senha (convite de acesso por WhatsApp e
 * reset sem SMTP, mig 025/167).
 *
 * O Better Auth valida o token em `/api/auth/reset-password/:token` e
 * redireciona pra cá com `?token=...` (ou `?error=INVALID_TOKEN` quando o
 * link expirou ou já foi usado). Esta página existia só como `redirectTo`
 * nas chamadas — ninguém a tinha construído, e o link levava a um 404.
 *
 * `useSearchParams` exige Suspense no App Router — o fallback nunca é visto
 * na prática (a página é estática e leve).
 */
export default function ResetPasswordPage() {
  return (
    <Suspense fallback={null}>
      <ResetPasswordForm />
    </Suspense>
  );
}
