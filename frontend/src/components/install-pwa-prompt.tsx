"use client";

/**
 * Banner "Instalar como aplicativo" — aparece automaticamente em browsers
 * que suportam `beforeinstallprompt` (Chrome Android, Edge desktop), com
 * fallback de instruções manuais no iOS Safari.
 *
 * Persistência: ao "Agora não" gravamos em localStorage com TTL de 7 dias
 * pra não atormentar o usuário em cada visita. "Instalar" chama o prompt
 * nativo do browser. Após instalar (`appinstalled`), ocultamos pra sempre.
 */

import { useEffect, useState } from "react";
import { Download, X } from "lucide-react";

import { Button } from "@/components/ui/button";

// Evento BeforeInstallPrompt — não vem em lib.dom.d.ts ainda.
interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

const STORAGE_KEY = "vsa.pwa.dismissed_at";
const DISMISS_TTL_MS = 7 * 24 * 60 * 60 * 1000; // 7 dias

function recentlyDismissed(): boolean {
  if (typeof window === "undefined") return true;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return false;
    const ts = Number(raw);
    if (!Number.isFinite(ts)) return false;
    return Date.now() - ts < DISMISS_TTL_MS;
  } catch {
    return false;
  }
}

function isStandalone(): boolean {
  if (typeof window === "undefined") return false;
  // PWA instalada (Chrome/Edge) OU adicionada à home no iOS
  return (
    window.matchMedia?.("(display-mode: standalone)").matches ||
    // @ts-expect-error iOS-only Safari property
    window.navigator?.standalone === true
  );
}

function isIOS(): boolean {
  if (typeof navigator === "undefined") return false;
  return /iPhone|iPad|iPod/.test(navigator.userAgent);
}

export function InstallPwaPrompt() {
  const [event, setEvent] = useState<BeforeInstallPromptEvent | null>(null);
  const [showIosHint, setShowIosHint] = useState(false);
  const [installing, setInstalling] = useState(false);

  useEffect(() => {
    if (isStandalone() || recentlyDismissed()) return;

    const handler = (e: Event) => {
      // Bloqueia o mini-info-bar nativo do Chrome pra mostrarmos o nosso
      e.preventDefault();
      setEvent(e as BeforeInstallPromptEvent);
    };
    window.addEventListener("beforeinstallprompt", handler);

    // iOS Safari nunca dispara beforeinstallprompt — mostramos hint manual
    // após 3s pra não cobrir a primeira interação do usuário.
    let iosTimer: ReturnType<typeof setTimeout> | null = null;
    if (isIOS()) {
      iosTimer = setTimeout(() => setShowIosHint(true), 3000);
    }

    const onInstalled = () => {
      setEvent(null);
      setShowIosHint(false);
      try {
        localStorage.setItem(STORAGE_KEY, String(Date.now()));
      } catch {
        /* ignore */
      }
    };
    window.addEventListener("appinstalled", onInstalled);

    return () => {
      window.removeEventListener("beforeinstallprompt", handler);
      window.removeEventListener("appinstalled", onInstalled);
      if (iosTimer) clearTimeout(iosTimer);
    };
  }, []);

  function dismiss() {
    setEvent(null);
    setShowIosHint(false);
    try {
      localStorage.setItem(STORAGE_KEY, String(Date.now()));
    } catch {
      /* ignore */
    }
  }

  async function handleInstall() {
    if (!event) return;
    setInstalling(true);
    try {
      await event.prompt();
      const { outcome } = await event.userChoice;
      if (outcome === "dismissed") dismiss();
      setEvent(null);
    } catch {
      dismiss();
    } finally {
      setInstalling(false);
    }
  }

  if (!event && !showIosHint) return null;

  return (
    <div className="fixed inset-x-2 bottom-2 z-50 flex justify-center sm:bottom-4">
      <div className="w-full max-w-md rounded-lg border bg-background/95 p-3 shadow-xl backdrop-blur sm:p-4">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-primary/10">
            <Download className="h-5 w-5 text-primary" />
          </div>
          <div className="flex-1 text-sm">
            <p className="font-medium">Instalar Nexus Chat</p>
            {event ? (
              <p className="mt-0.5 text-muted-foreground">
                Adicione à tela inicial pra abrir como aplicativo, sem barra
                do navegador.
              </p>
            ) : (
              <p className="mt-0.5 text-muted-foreground">
                No iOS: toque em <span className="font-mono">Compartilhar</span>{" "}
                → <span className="font-mono">Adicionar à Tela de Início</span>.
              </p>
            )}
            <div className="mt-3 flex justify-end gap-2">
              <Button
                variant="ghost"
                size="sm"
                onClick={dismiss}
                disabled={installing}
              >
                Agora não
              </Button>
              {event && (
                <Button
                  size="sm"
                  onClick={handleInstall}
                  disabled={installing}
                >
                  {installing ? "Instalando…" : "Instalar"}
                </Button>
              )}
            </div>
          </div>
          <button
            type="button"
            onClick={dismiss}
            aria-label="Fechar"
            className="rounded p-1 text-muted-foreground hover:bg-muted"
            disabled={installing}
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
