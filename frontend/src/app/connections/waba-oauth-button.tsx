"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Loader2 } from "lucide-react";

import { Button } from "@/components/ui/button";

import { getWabaConfigAction, wabaEmbeddedSignupAction } from "./actions";

interface Props {
  displayName?: string;
  onSuccess?: () => void;
  onError?: (error: string) => void;
}

// FB JS SDK é injetado no window — tipagem mínima pro que usamos.
declare global {
  interface Window {
    FB?: {
      init: (params: Record<string, unknown>) => void;
      login: (
        cb: (resp: {
          authResponse?: { code?: string } | null;
          status?: string;
        }) => void,
        opts: Record<string, unknown>
      ) => void;
    };
    fbAsyncInit?: () => void;
  }
}

const FB_SDK_SRC = "https://connect.facebook.net/en_US/sdk.js";

/**
 * Botão "Conectar com Meta" — Embedded Signup via FB JS SDK (método oficial).
 *
 * Fluxo:
 * 1. Mount → GET /waba/config (app_id + config_id) → FB.init
 * 2. Listener `message` captura WA_EMBEDDED_SIGNUP {waba_id, phone_number_id}
 * 3. Click → FB.login(config_id) abre popup oficial Meta
 * 4. Callback do FB.login → authResponse.code
 * 5. code + waba_id + phone_number_id → POST /waba/embedded-signup → conexão
 */
export function WabaOAuthButton({ displayName, onSuccess, onError }: Props) {
  const [busy, setBusy] = useState(false);
  const [sdkReady, setSdkReady] = useState(false);
  const configRef = useRef<{ app_id: string; config_id: string; graph_version: string } | null>(
    null
  );
  // sessionInfo (waba_id + phone_number_id) chega via postMessage ANTES do
  // callback do FB.login resolver — guardamos aqui pra combinar com o code.
  const sessionRef = useRef<{ waba_id?: string; phone_number_id?: string }>({});

  // 1) Carrega FB SDK + config no mount
  useEffect(() => {
    let cancelled = false;

    (async () => {
      const cfg = await getWabaConfigAction();
      if (cancelled) return;
      if (!cfg.ok) {
        onError?.(cfg.error);
        return;
      }
      configRef.current = cfg.data;

      // Injeta o script do SDK uma vez
      if (!document.getElementById("facebook-jssdk")) {
        window.fbAsyncInit = () => {
          window.FB?.init({
            appId: cfg.data.app_id,
            autoLogAppEvents: true,
            xfbml: false,
            version: cfg.data.graph_version,
          });
          setSdkReady(true);
        };
        const js = document.createElement("script");
        js.id = "facebook-jssdk";
        js.src = FB_SDK_SRC;
        js.async = true;
        js.defer = true;
        js.crossOrigin = "anonymous";
        document.body.appendChild(js);
      } else if (window.FB) {
        window.FB.init({
          appId: cfg.data.app_id,
          version: cfg.data.graph_version,
          xfbml: false,
        });
        setSdkReady(true);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [onError]);

  // 2) Listener do sessionInfo (evento WA_EMBEDDED_SIGNUP do popup Meta)
  useEffect(() => {
    function handleMessage(event: MessageEvent) {
      if (
        event.origin !== "https://www.facebook.com" &&
        event.origin !== "https://web.facebook.com"
      )
        return;
      try {
        const data =
          typeof event.data === "string" ? JSON.parse(event.data) : event.data;
        if (data?.type !== "WA_EMBEDDED_SIGNUP") return;
        // data.event: 'FINISH' | 'CANCEL' | 'ERROR'
        if (data.event === "FINISH" && data.data) {
          sessionRef.current = {
            waba_id: data.data.waba_id,
            phone_number_id: data.data.phone_number_id,
          };
        } else if (data.event === "CANCEL" || data.event === "ERROR") {
          sessionRef.current = {};
        }
      } catch {
        // mensagem não-JSON do FB — ignora
      }
    }
    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, []);

  const handleClick = useCallback(() => {
    const cfg = configRef.current;
    if (!cfg || !window.FB) {
      onError?.("SDK do Facebook ainda não carregou. Aguarde e tente de novo.");
      return;
    }
    setBusy(true);
    sessionRef.current = {};

    window.FB.login(
      (resp) => {
        const code = resp?.authResponse?.code;
        const session = sessionRef.current;
        if (!code) {
          setBusy(false);
          onError?.("Conexão cancelada ou sem autorização.");
          return;
        }
        if (!session.waba_id || !session.phone_number_id) {
          setBusy(false);
          onError?.(
            "Não recebemos os dados da conta WhatsApp (waba_id/phone). Tente de novo."
          );
          return;
        }
        (async () => {
          const r = await wabaEmbeddedSignupAction({
            code,
            waba_account_id: session.waba_id!,
            phone_number_id: session.phone_number_id!,
            display_name: displayName || null,
            register_phone: true,
          });
          setBusy(false);
          if (r.ok) onSuccess?.();
          else onError?.(r.error);
        })();
      },
      {
        config_id: cfg.config_id,
        response_type: "code",
        override_default_response_type: true,
        extras: {
          setup: {},
          featureType: "whatsapp_business_app_onboarding",
          sessionInfoVersion: "3",
        },
      }
    );
  }, [displayName, onSuccess, onError]);

  return (
    <Button onClick={handleClick} disabled={busy || !sdkReady} className="gap-2">
      {(busy || !sdkReady) && <Loader2 className="h-4 w-4 animate-spin" />}
      {sdkReady ? "Conectar com Meta" : "Carregando SDK..."}
    </Button>
  );
}
