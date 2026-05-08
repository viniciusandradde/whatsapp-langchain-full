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
    <div className="flex min-h-screen items-center justify-center px-6 py-12">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center">
          <Image
            src="/vsa-logo.png"
            alt="VSA Tech"
            width={56}
            height={56}
            className="rounded"
            unoptimized
          />
          <span className="mt-3 text-lg font-semibold tracking-tight">
            VSA Tech
          </span>
        </div>

        <div className="mb-6 text-center">
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
  );
}
