"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";

import { wabaFinalizeAction, wabaOAuthResultAction, wabaOAuthStartAction } from "./actions";

interface Props {
  displayName?: string;
  onSuccess?: () => void;
  onError?: (error: string) => void;
}

/**
 * Botão "Conectar com Meta" — abre popup OAuth Embedded Signup.
 *
 * Fluxo:
 * 1. Click → POST /api/conexoes/waba/oauth/start → recebe redirect_url + state
 * 2. window.open() popup com redirect_url
 * 3. Listen postMessage do callback (oauth-callback/page.tsx)
 * 4. Em sucesso, GET /api/conexoes/waba/oauth/result → list de WABA accounts
 * 5. Se 1 account: POST finalize direto. Se N: callback onSuccess com picker
 */
export function WabaOAuthButton({ displayName, onSuccess, onError }: Props) {
  const [busy, setBusy] = useState(false);
  const popupRef = useRef<Window | null>(null);

  useEffect(() => {
    function handleMessage(event: MessageEvent) {
      // Aceita só do mesmo origin (CSRF protection)
      if (event.origin !== window.location.origin) return;
      if (event.data?.type !== "waba_oauth_callback") return;

      const { status, state, reason } = event.data;
      popupRef.current?.close();
      popupRef.current = null;

      if (status !== "ok") {
        setBusy(false);
        onError?.(reason || "OAuth cancelado.");
        return;
      }

      // Buscar accounts disponíveis
      (async () => {
        const r = await wabaOAuthResultAction(state);
        if (!r.ok) {
          setBusy(false);
          onError?.(r.error);
          return;
        }
        const accounts = r.data.accounts;
        if (accounts.length === 0) {
          setBusy(false);
          onError?.("Nenhuma WABA account encontrada na sua conta Meta.");
          return;
        }

        // Auto-finalize se só 1 account + 1 phone
        if (accounts.length === 1 && accounts[0].phone_numbers.length === 1) {
          const account = accounts[0];
          const phone = account.phone_numbers[0];
          const fin = await wabaFinalizeAction({
            state,
            waba_account_id: account.id,
            phone_id: phone.id,
            display_name: r.data.display_name || account.name,
            register_phone: false,
          });
          setBusy(false);
          if (fin.ok) onSuccess?.();
          else onError?.(fin.error);
          return;
        }

        // Múltiplos accounts/phones — redirecionar pra picker
        setBusy(false);
        const url = `/connections/oauth-picker?state=${encodeURIComponent(state)}`;
        window.location.href = url;
      })();
    }

    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, [onSuccess, onError]);

  async function handleClick() {
    setBusy(true);
    const r = await wabaOAuthStartAction(displayName);
    if (!r.ok) {
      setBusy(false);
      onError?.(r.error);
      return;
    }
    if (!r.data) {
      setBusy(false);
      onError?.("Sem URL de redirecionamento.");
      return;
    }
    const w = 600;
    const h = 700;
    const left = (window.screen.width - w) / 2;
    const top = (window.screen.height - h) / 2;
    popupRef.current = window.open(
      r.data.redirect_url,
      "waba_oauth",
      `width=${w},height=${h},left=${left},top=${top}`
    );
    if (!popupRef.current) {
      setBusy(false);
      onError?.("Popup bloqueado pelo browser. Permita pop-ups e tente de novo.");
    }
  }

  return (
    <Button onClick={handleClick} disabled={busy} className="gap-2">
      {busy && <Loader2 className="h-4 w-4 animate-spin" />}
      Conectar com Meta
    </Button>
  );
}
