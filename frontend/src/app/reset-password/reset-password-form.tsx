"use client";

import { useState } from "react";
import Image from "next/image";
import { useRouter, useSearchParams } from "next/navigation";

import { resetPassword } from "@/lib/auth-client";

/**
 * A pessoa chega aqui pelo link recebido no WhatsApp (uso único, 1h).
 * Escolhe a própria senha e é mandada pro login — nada de sessão automática:
 * provar que consegue entrar com a senha nova faz parte do fluxo.
 */
export function ResetPasswordForm() {
  const router = useRouter();
  const params = useSearchParams();
  const token = params.get("token");
  const linkInvalido = !token || !!params.get("error");

  const [senha, setSenha] = useState("");
  const [confirma, setConfirma] = useState("");
  const [erro, setErro] = useState("");
  const [carregando, setCarregando] = useState(false);
  const [concluido, setConcluido] = useState(false);

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErro("");
    if (senha.length < 8) {
      setErro("A senha precisa ter pelo menos 8 caracteres.");
      return;
    }
    if (senha !== confirma) {
      setErro("As duas senhas não conferem.");
      return;
    }
    setCarregando(true);
    const { error } = await resetPassword({
      newPassword: senha,
      token: token ?? undefined,
    });
    if (error) {
      // Melhor causa provável: o link venceu ou já foi usado.
      setErro(
        "Não foi possível definir a senha — o link pode ter expirado ou já " +
          "ter sido usado. Peça um novo convite a quem criou seu acesso."
      );
      setCarregando(false);
      return;
    }
    setConcluido(true);
    setTimeout(() => router.push("/login"), 2500);
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-6 py-12">
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
          <h2 className="text-xl font-semibold">Criar sua senha</h2>
          <p className="mt-1 text-sm text-muted-foreground">
            Escolha a senha que você vai usar para entrar no painel.
          </p>
        </div>

        {linkInvalido ? (
          <div className="rounded-lg bg-muted px-4 py-3 text-sm text-muted-foreground">
            Este link não é mais válido — ele expira em 1 hora e funciona uma
            única vez. Peça um novo convite a quem criou seu acesso.
          </div>
        ) : concluido ? (
          <div className="rounded-lg border border-primary/10 bg-primary/5 px-4 py-3 text-sm">
            Senha criada! Levando você para o login…
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <label htmlFor="senha" className="text-sm font-medium">
                Nova senha
              </label>
              <input
                id="senha"
                type="password"
                value={senha}
                onChange={(e) => setSenha(e.target.value)}
                required
                minLength={8}
                autoComplete="new-password"
                className="flex h-10 w-full rounded-lg border bg-transparent px-3 py-2 text-sm outline-none transition-colors focus:border-primary focus:ring-2 focus:ring-ring/20"
                placeholder="Pelo menos 8 caracteres"
              />
            </div>
            <div className="space-y-2">
              <label htmlFor="confirma" className="text-sm font-medium">
                Repita a senha
              </label>
              <input
                id="confirma"
                type="password"
                value={confirma}
                onChange={(e) => setConfirma(e.target.value)}
                required
                autoComplete="new-password"
                className="flex h-10 w-full rounded-lg border bg-transparent px-3 py-2 text-sm outline-none transition-colors focus:border-primary focus:ring-2 focus:ring-ring/20"
                placeholder="A mesma senha de novo"
              />
            </div>
            {erro && <p className="text-sm text-destructive">{erro}</p>}
            <button
              type="submit"
              disabled={carregando}
              className="flex h-10 w-full items-center justify-center rounded-lg bg-primary text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
            >
              {carregando ? "Salvando…" : "Criar senha e continuar"}
            </button>
          </form>
        )}
      </div>
    </div>
  );
}
