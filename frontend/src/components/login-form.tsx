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
}

export function LoginForm({
  defaultEmail = "",
  defaultPassword = "",
  showBootstrapHint = false,
  helperMessage,
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

  return (
    <div className="flex min-h-screen">
      {/* Painel esquerdo — identidade da marca (escondido no mobile) */}
      <div className="relative hidden w-[45%] overflow-hidden bg-hawk-navy-deep md:flex md:flex-col md:justify-between">
        {/* Gradiente sutil */}
        <div
          className="absolute inset-0"
          style={{
            background:
              "radial-gradient(ellipse at 30% 20%, oklch(0.25 0.10 200 / 0.4), transparent 60%), radial-gradient(ellipse at 80% 80%, oklch(0.20 0.08 265 / 0.3), transparent 50%)",
          }}
        />

        {/* Conteúdo */}
        <div className="relative z-10 flex flex-1 flex-col justify-center px-10 lg:px-14">
          {/* Marca */}
          <div className="mb-8">
            <div className="mb-3 flex items-center gap-3">
              <Image src="/logo-hawk.png" alt="rhawk.pro" width={32} height={32} className="rounded" unoptimized />
              <span className="text-lg font-semibold tracking-tight text-white/90">
                rhawk.pro
              </span>
            </div>
            <p className="text-[10px] font-medium uppercase tracking-[0.2em] text-hawk-blue/80">
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
          <div className="h-px w-12 bg-hawk-blue/20" />
          <p className="mt-3 text-[11px] text-white/25">
            TOPHAWKS
          </p>
        </div>
      </div>

      {/* Painel direito — formulário */}
      <div className="flex flex-1 items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm">
          {/* Marca no mobile */}
          <div className="mb-8 flex flex-col items-center md:hidden">
            <div className="mb-3 flex items-center gap-2.5">
              <Image src="/logo-hawk.png" alt="rhawk.pro" width={28} height={28} className="rounded" unoptimized />
              <span className="text-lg font-semibold tracking-tight">rhawk.pro</span>
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
        </div>
      </div>
    </div>
  );
}
