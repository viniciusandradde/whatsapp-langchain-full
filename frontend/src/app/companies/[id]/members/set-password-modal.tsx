"use client";

/**
 * Modal "Resetar senha" — admin confirma reset, backend gera senha
 * forte com CSPRNG no servidor e retorna pro admin compartilhar com
 * o usuário pelo canal seguro (WhatsApp pessoal, etc).
 *
 * SEGURANÇA: senha NUNCA é digitada pelo admin no client (evita
 * histórico de browser, autocomplete, screen-share). Backend gera,
 * aplica via Better Auth, retorna UMA VEZ pro admin copiar.
 */

import { useState, useTransition } from "react";
import {
  Check,
  Copy,
  Eye,
  EyeOff,
  Key,
  Loader2,
  ShieldAlert,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";

import { resetMemberPasswordAction } from "./actions";

interface Props {
  userId: string;
  userEmail?: string | null;
  onClose: () => void;
  onSaved?: () => void;
}

export function SetPasswordModal({ userId, userEmail, onClose, onSaved }: Props) {
  const [error, setError] = useState<string | null>(null);
  const [generated, setGenerated] = useState<{
    password: string;
    email: string;
  } | null>(null);
  const [show, setShow] = useState(false);
  const [copied, setCopied] = useState(false);
  const [pending, startSave] = useTransition();

  function handleConfirm() {
    setError(null);
    startSave(async () => {
      const r = await resetMemberPasswordAction(userId);
      if (r.ok) {
        setGenerated({ password: r.password, email: r.email });
        if (onSaved) onSaved();
      } else {
        setError(r.error);
      }
    });
  }

  async function handleCopy() {
    if (!generated) return;
    try {
      await navigator.clipboard.writeText(generated.password);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback: select all
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="relative w-full max-w-md rounded-lg border border-border bg-background p-6 shadow-xl">
        <button
          type="button"
          onClick={onClose}
          className="absolute right-3 top-3 rounded-md p-1 text-muted-foreground hover:bg-muted"
          aria-label="Fechar"
        >
          <X className="size-4" />
        </button>

        <header className="mb-4">
          <div className="flex items-center gap-2">
            <Key className="size-5 text-primary" />
            <h2 className="text-lg font-semibold">Resetar senha</h2>
          </div>
          {userEmail && (
            <p className="mt-1 text-xs text-muted-foreground">{userEmail}</p>
          )}
          <p className="mt-1 font-mono text-[10px] text-muted-foreground">
            {userId}
          </p>
        </header>

        {generated ? (
          <div className="space-y-3">
            <p className="rounded-md border border-emerald-500/40 bg-emerald-500/10 p-3 text-sm text-emerald-700 dark:text-emerald-300">
              ✓ Senha redefinida. Compartilhe com o usuário pelo canal
              seguro (WhatsApp pessoal, etc) e oriente a trocar no
              primeiro login.
            </p>

            <div className="rounded-md border border-border bg-muted/30 p-3">
              <div className="mb-2 flex items-center justify-between">
                <p className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                  Nova senha
                </p>
                <div className="flex gap-1">
                  <button
                    type="button"
                    onClick={() => setShow((s) => !s)}
                    className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"
                    aria-label={show ? "Esconder" : "Mostrar"}
                  >
                    {show ? (
                      <EyeOff className="size-3.5" />
                    ) : (
                      <Eye className="size-3.5" />
                    )}
                  </button>
                  <button
                    type="button"
                    onClick={handleCopy}
                    className="flex items-center gap-1 rounded px-1.5 py-1 text-xs text-muted-foreground hover:bg-muted hover:text-foreground"
                  >
                    {copied ? (
                      <>
                        <Check className="size-3.5 text-emerald-500" />
                        Copiado
                      </>
                    ) : (
                      <>
                        <Copy className="size-3.5" />
                        Copiar
                      </>
                    )}
                  </button>
                </div>
              </div>
              <p className="break-all font-mono text-base">
                {show
                  ? generated.password
                  : "•".repeat(generated.password.length)}
              </p>
            </div>

            <p className="text-xs text-muted-foreground">
              ⚠ Esta senha aparece UMA VEZ. Não é armazenada em texto —
              só o hash. Sessões antigas continuam até expirarem; pra
              forçar logout combine com &ldquo;Desativar usuário&rdquo;.
            </p>
            <Button onClick={onClose} className="w-full">
              Fechar
            </Button>
          </div>
        ) : (
          <>
            {error && (
              <p className="mb-3 rounded-md border border-destructive/50 bg-destructive/10 p-2 text-xs text-destructive">
                {error}
              </p>
            )}

            <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-xs text-amber-700 dark:text-amber-300">
              <div className="mb-1 flex items-center gap-1.5 font-semibold">
                <ShieldAlert className="size-4" />
                O servidor vai gerar uma senha forte aleatória
              </div>
              <p>
                Isso é mais seguro que admin digitar: senha nunca passa
                pelo formulário (sem autocomplete, histórico, etc).
                Backend gera com CSPRNG, aplica via Better Auth, e
                retorna UMA vez pra você copiar e enviar pelo canal
                seguro.
              </p>
            </div>

            <footer className="mt-6 flex justify-end gap-2 border-t border-border pt-4">
              <Button variant="outline" onClick={onClose} disabled={pending}>
                Cancelar
              </Button>
              <Button onClick={handleConfirm} disabled={pending}>
                {pending ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Key className="size-4" />
                )}
                Gerar nova senha
              </Button>
            </footer>
          </>
        )}
      </div>
    </div>
  );
}
