"use client";

import { useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import Script from "next/script";
import { signIn } from "@/lib/auth-client";
import { Button } from "@/components/ui/button";

interface LoginFormProps {
  defaultEmail?: string;
  defaultPassword?: string;
  showBootstrapHint?: boolean;
  helperMessage?: string;
  /** Site key do reCAPTCHA Enterprise; null = captcha desligado (dev sem chave). */
  recaptchaSiteKey?: string | null;
}

// `grecaptcha.enterprise` chega pelo script do Google (enterprise.js).
declare global {
  interface Window {
    grecaptcha?: {
      enterprise: {
        ready: (cb: () => void) => void;
        execute: (siteKey: string, opts: { action: string }) => Promise<string>;
      };
    };
  }
}

/**
 * Token do reCAPTCHA para a ação LOGIN. Chave por pontuação: invisível, sem
 * desafio — o Google pontua o comportamento e o servidor (`lib/captcha.ts`)
 * decide. Se o script não carregou (bloqueador, rede), devolve null e o
 * servidor responde "verificação ausente" — o operador vê a mensagem e
 * recarrega, em vez de o login ficar pendurado.
 */
async function obterTokenRecaptcha(siteKey: string): Promise<string | null> {
  const g = window.grecaptcha?.enterprise;
  if (!g) return null;
  try {
    await new Promise<void>((resolve) => g.ready(resolve));
    return await g.execute(siteKey, { action: "LOGIN" });
  } catch {
    return null;
  }
}

export function LoginForm({
  defaultEmail = "",
  defaultPassword = "",
  showBootstrapHint = false,
  helperMessage,
  recaptchaSiteKey = null,
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

    // Com captcha ligado, o token vai no header que o plugin do servidor lê.
    const headers: Record<string, string> = {};
    if (recaptchaSiteKey) {
      const token = await obterTokenRecaptcha(recaptchaSiteKey);
      if (token) headers["x-captcha-response"] = token;
    }

    const { error: authError } = await signIn.email(
      {
        email,
        password,
        callbackURL: "/",
      },
      { headers }
    );

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
      {recaptchaSiteKey && (
        <Script
          src={`https://www.google.com/recaptcha/enterprise.js?render=${encodeURIComponent(recaptchaSiteKey)}`}
          strategy="afterInteractive"
        />
      )}
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center">
          <Image
            src="/vsa-logo.png"
            alt="Chat Nexus"
            width={56}
            height={56}
            className="rounded"
            unoptimized
          />
          <span className="mt-3 text-lg font-semibold tracking-tight">
            Chat Nexus
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

        {recaptchaSiteKey && (
          // O Google exige este aviso quando o selo flutuante é escondido
          // (globals.css: .grecaptcha-badge). Texto e links são os pedidos.
          <p className="mt-6 text-center text-[11px] leading-relaxed text-muted-foreground">
            Este site é protegido pelo reCAPTCHA e se aplicam a{" "}
            <a
              href="https://policies.google.com/privacy"
              target="_blank"
              rel="noreferrer"
              className="underline"
            >
              Política de Privacidade
            </a>{" "}
            e os{" "}
            <a
              href="https://policies.google.com/terms"
              target="_blank"
              rel="noreferrer"
              className="underline"
            >
              Termos de Serviço
            </a>{" "}
            do Google.
          </p>
        )}
      </div>
    </div>
  );
}
