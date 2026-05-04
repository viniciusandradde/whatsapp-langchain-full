"use client";

import { useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { signIn } from "@/lib/auth-client";
import { Button } from "@/components/ui/button";

interface LoginFormProps {
  defaultEmail?: string;
  defaultPassword?: string;
  showBootstrapHint?: boolean;
  helperMessage?: string;
  /** Habilita botão "Entrar com Google" se SSO está configurado no backend. */
  googleEnabled?: boolean;
}

export function LoginForm({
  defaultEmail = "",
  defaultPassword = "",
  showBootstrapHint = false,
  helperMessage,
  googleEnabled = false,
}: LoginFormProps) {
  const router = useRouter();
  const [email, setEmail] = useState(defaultEmail);
  const [password, setPassword] = useState(defaultPassword);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setLoading(true);

    const { error: authError } = await signIn.email({
      email,
      password,
      callbackURL: "/",
    });

    if (authError) {
      setError(authError.message || "Erro ao fazer login");
      setLoading(false);
      return;
    }

    router.push("/");
    router.refresh();
  }

  async function handleGoogleSignIn() {
    setError("");
    setLoading(true);
    const { error: authError } = await signIn.social({
      provider: "google",
      callbackURL: "/",
    });
    if (authError) {
      setError(authError.message || "Erro ao iniciar login com Google");
      setLoading(false);
    }
  }

  return (
    <div className="flex min-h-screen">
      {/* Painel esquerdo — identidade da marca (escondido no mobile) */}
      <div className="relative hidden w-[45%] overflow-hidden bg-obsidian-900 md:flex md:flex-col md:justify-between">
        {/* Gradiente Obsidian — orange + blue glow sobre o void */}
        <div
          className="absolute inset-0"
          style={{
            background:
              "radial-gradient(ellipse at 30% 20%, rgba(249, 115, 22, 0.18), transparent 60%), radial-gradient(ellipse at 80% 80%, rgba(59, 130, 246, 0.18), transparent 50%)",
          }}
        />

        {/* Conteúdo */}
        <div className="relative z-10 flex flex-1 flex-col justify-center px-10 lg:px-14">
          {/* Marca */}
          <div className="mb-8">
            <div className="mb-3 flex items-center gap-3">
              <Image src="/vsa-logo.png" alt="VSA Tech" width={32} height={32} className="rounded" unoptimized />
              <span className="text-lg font-semibold tracking-tight text-white/90">
                VSA Tech
              </span>
            </div>
            <p className="text-[10px] font-medium uppercase tracking-[0.2em] text-brand-secondary/80">
              Harness para agentes de WhatsApp
            </p>
          </div>

          {/* Descrição */}
          <h1 className="mb-4 text-2xl font-semibold leading-tight text-white/90 lg:text-3xl">
            Painel de operações
          </h1>
          <p className="max-w-sm text-sm leading-relaxed text-white/40">
            Métricas, fila de mensagens, conversas e configurações do harness em uma interface administrativa.
          </p>
        </div>

        {/* Rodapé do painel */}
        <div className="relative z-10 px-10 pb-8 lg:px-14">
          <div className="h-px w-12 bg-brand-secondary/20" />
          <p className="mt-3 text-[11px] text-white/25">
            VSA TECH
          </p>
        </div>
      </div>

      {/* Painel direito — formulário */}
      <div className="flex flex-1 items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm">
          {/* Marca no mobile */}
          <div className="mb-8 flex flex-col items-center md:hidden">
            <div className="mb-3 flex items-center gap-2.5">
              <Image src="/vsa-logo.png" alt="VSA Tech" width={28} height={28} className="rounded" unoptimized />
              <span className="text-lg font-semibold tracking-tight">VSA Tech</span>
            </div>
          </div>

          {/* Cabeçalho do form */}
          <div className="mb-6">
            <h2 className="text-xl font-semibold">Entrar</h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Acesse o painel administrativo
            </p>
          </div>

          {helperMessage && (
            <div className="mb-4 rounded-lg bg-muted px-4 py-3 text-sm text-muted-foreground">
              {helperMessage}
            </div>
          )}

          {showBootstrapHint && (
            <div className="mb-4 rounded-lg bg-primary/5 border border-primary/10 px-4 py-3 text-sm text-muted-foreground">
              Primeiro admin criado automaticamente a partir de
              <strong> ADMIN_EMAIL</strong> e <strong>ADMIN_PASSWORD</strong>.
              Entre e troque a senha em <strong>/settings</strong>.
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <label htmlFor="email" className="text-sm font-medium">
                Email
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                required
                className="flex h-10 w-full rounded-lg border bg-transparent px-3 py-2 text-sm outline-none transition-colors focus:border-primary focus:ring-2 focus:ring-ring/20"
                placeholder="Digite seu email"
              />
            </div>
            <div className="space-y-2">
              <label htmlFor="password" className="text-sm font-medium">
                Senha
              </label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                required
                minLength={8}
                className="flex h-10 w-full rounded-lg border bg-transparent px-3 py-2 text-sm outline-none transition-colors focus:border-primary focus:ring-2 focus:ring-ring/20"
                placeholder="Digite sua senha"
              />
            </div>

            {error && (
              <div className="rounded-lg bg-destructive/10 px-4 py-3 text-sm text-destructive">
                {error}
              </div>
            )}

            <Button type="submit" className="w-full h-10" disabled={loading}>
              {loading ? "Entrando..." : "Entrar"}
            </Button>
          </form>

          {googleEnabled && (
            <>
              <div className="my-6 flex items-center gap-3">
                <div className="h-px flex-1 bg-border" />
                <span className="text-xs text-muted-foreground">ou</span>
                <div className="h-px flex-1 bg-border" />
              </div>

              <Button
                type="button"
                variant="outline"
                className="w-full h-10"
                disabled={loading}
                onClick={handleGoogleSignIn}
              >
                <svg
                  className="size-4"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <path
                    fill="#4285F4"
                    d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                  />
                  <path
                    fill="#34A853"
                    d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84A10.99 10.99 0 0 0 12 23z"
                  />
                  <path
                    fill="#FBBC05"
                    d="M5.84 14.09a6.6 6.6 0 0 1 0-4.18V7.07H2.18a11 11 0 0 0 0 9.86l3.66-2.84z"
                  />
                  <path
                    fill="#EA4335"
                    d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1A10.99 10.99 0 0 0 2.18 7.07l3.66 2.84C6.71 7.31 9.14 5.38 12 5.38z"
                  />
                </svg>
                Entrar com Google
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
