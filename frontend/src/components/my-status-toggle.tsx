"use client";

/**
 * Sprint G.5 — Toggle de status do atendente no footer da sidebar.
 *
 * - Fetch inicial de status via /api/atendentes/empresa-status (filter pelo
 *   user atual). Sem 1 endpoint /me/status GET separado pra economizar; reusa
 *   o que já existe.
 * - Click abre dropdown com 4 opções; persistência via POST /me/status.
 * - Heartbeat: a cada 60s envia POST /me/heartbeat se status='online'.
 *   Sem heartbeat por 5min, worker auto-marca offline (Sprint G.4).
 */

import { useEffect, useRef, useState } from "react";
import { Circle } from "lucide-react";

import { cn } from "@/lib/utils";

type Status = "online" | "ausente" | "pausa" | "offline";

const OPTIONS: { v: Status; label: string; cls: string }[] = [
  { v: "online", label: "Online", cls: "bg-emerald-500" },
  { v: "ausente", label: "Ausente", cls: "bg-amber-500" },
  { v: "pausa", label: "Em pausa", cls: "bg-blue-500" },
  { v: "offline", label: "Offline", cls: "bg-muted-foreground" },
];

const HEARTBEAT_MS = 60_000;

async function fetchMyStatus(): Promise<Status | null> {
  try {
    const r = await fetch("/api/proxy/atendentes/me-status", {
      cache: "no-store",
    });
    if (!r.ok) return null;
    const data = (await r.json()) as { atendente_status: Status | null };
    return data.atendente_status ?? null;
  } catch {
    return null;
  }
}

async function setMyStatus(status: Status): Promise<boolean> {
  try {
    const r = await fetch("/api/proxy/atendentes/me-status", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    });
    return r.ok;
  } catch {
    return false;
  }
}

async function sendHeartbeat(): Promise<void> {
  try {
    await fetch("/api/proxy/atendentes/heartbeat", { method: "POST" });
  } catch {
    // silencioso — próximo tick tenta de novo
  }
}

export function MyStatusToggle() {
  const [status, setStatus] = useState<Status | null>(null);
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const heartbeatTimer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    void fetchMyStatus().then(setStatus);
  }, []);

  // Heartbeat: dispara só quando status='online'. Outros status não
  // precisam de prova-de-vida (auto-offline 5min só vale pra online).
  useEffect(() => {
    if (heartbeatTimer.current) {
      clearInterval(heartbeatTimer.current);
      heartbeatTimer.current = null;
    }
    if (status === "online") {
      void sendHeartbeat();
      heartbeatTimer.current = setInterval(() => void sendHeartbeat(), HEARTBEAT_MS);
    }
    return () => {
      if (heartbeatTimer.current) {
        clearInterval(heartbeatTimer.current);
        heartbeatTimer.current = null;
      }
    };
  }, [status]);

  const current = OPTIONS.find((o) => o.v === status);

  const handlePick = async (next: Status) => {
    setSaving(true);
    setOpen(false);
    const ok = await setMyStatus(next);
    if (ok) setStatus(next);
    setSaving(false);
  };

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        disabled={saving}
        className={cn(
          "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm",
          "text-sidebar-foreground/70 hover:bg-sidebar-accent/50",
          "transition-colors disabled:opacity-50"
        )}
      >
        <span className="relative inline-flex">
          <Circle className="h-4 w-4 stroke-current" strokeWidth={1.5} />
          {current && (
            <span
              className={cn(
                "absolute inset-0 m-auto h-2 w-2 rounded-full",
                current.cls
              )}
            />
          )}
        </span>
        <span className="flex-1 text-left">
          {saving ? "Salvando…" : current?.label || "Indefinido"}
        </span>
      </button>

      {open && (
        <div className="absolute bottom-full left-0 z-20 mb-1 w-full overflow-hidden rounded-md border bg-popover p-1 shadow-md">
          {OPTIONS.map((o) => (
            <button
              key={o.v}
              type="button"
              onClick={() => void handlePick(o.v)}
              className={cn(
                "flex w-full items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-accent",
                status === o.v && "bg-accent/50 font-medium"
              )}
            >
              <span className={cn("h-2 w-2 rounded-full", o.cls)} />
              {o.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
