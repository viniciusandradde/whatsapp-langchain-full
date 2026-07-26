"use client";

import { useEffect, useState, useTransition } from "react";
import { ShieldCheck, Flame } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { ConexaoQuota } from "@/lib/api";

import { getConexaoQuotaAction, patchConexaoAction } from "../actions";

const inputCls =
  "h-9 w-full rounded-md border border-border/40 bg-background px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring";

interface Props {
  conexaoId: number;
  initialDailyCap: number | null;
  initialWarmupAtivo: boolean;
}

export function AntiBanPanel({
  conexaoId,
  initialDailyCap,
  initialWarmupAtivo,
}: Props) {
  const [cap, setCap] = useState<string>(
    initialDailyCap != null ? String(initialDailyCap) : ""
  );
  const [warmup, setWarmup] = useState<boolean>(initialWarmupAtivo);
  const [quota, setQuota] = useState<ConexaoQuota | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [saving, startSaving] = useTransition();

  async function loadQuota() {
    const r = await getConexaoQuotaAction(conexaoId);
    if (r.ok) setQuota(r.data!);
  }

  useEffect(() => {
    void loadQuota();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conexaoId]);

  function handleSave() {
    setMsg(null);
    const capNum = cap.trim() === "" ? 0 : parseInt(cap, 10);
    if (cap.trim() !== "" && (isNaN(capNum) || capNum < 0)) {
      setMsg("Teto diário inválido.");
      return;
    }
    startSaving(async () => {
      const r = await patchConexaoAction(conexaoId, {
        // 0 limpa o teto (NULL) no backend; >0 define
        daily_send_cap: capNum,
        warmup_enabled: warmup,
      });
      if (r.ok) {
        setMsg("✓ Salvo.");
        await loadQuota();
      } else {
        setMsg(`Erro: ${r.error}`);
      }
    });
  }

  return (
    <div className="rounded-lg border border-border/40 p-4 space-y-4">
      <div className="flex items-center gap-2">
        <ShieldCheck className="h-5 w-5 text-emerald-400" />
        <div>
          <div className="font-medium">Anti-ban — teto diário & aquecimento</div>
          <p className="text-xs text-muted-foreground">
            Limita quantas mensagens este número dispara por dia. Ao atingir o
            teto, a campanha é reagendada pro dia seguinte (sem abortar).
          </p>
        </div>
      </div>

      {/* Uso de hoje */}
      {quota && (
        <div className="grid grid-cols-1 gap-3 rounded-md border border-border/30 bg-muted/10 p-3 text-sm sm:grid-cols-3">
          <Stat label="Teto de hoje" value={quota.cap == null ? "∞" : quota.cap} />
          <Stat label="Enviados hoje" value={quota.usados} />
          <Stat
            label="Restante"
            value={quota.restante == null ? "∞" : quota.restante}
          />
          {quota.motivo && (
            <div className="col-span-3 text-xs text-muted-foreground">
              Limitado por: {quota.motivo}
            </div>
          )}
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div>
          <label className="text-xs uppercase tracking-wide text-muted-foreground">
            Teto diário (msgs)
          </label>
          <input
            type="number"
            min={0}
            inputMode="numeric"
            value={cap}
            onChange={(e) => setCap(e.target.value)}
            placeholder="vazio = sem teto"
            className={`${inputCls} mt-1`}
          />
        </div>
        <div className="flex items-end">
          <label className="inline-flex cursor-pointer items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={warmup}
              onChange={(e) => setWarmup(e.target.checked)}
              className="h-4 w-4 rounded border-border/40"
            />
            <Flame className="h-4 w-4 text-orange-400" />
            Modo aquecimento (número novo)
          </label>
        </div>
      </div>

      <p className="text-xs text-muted-foreground">
        Aquecimento: começa em ~20 msgs/dia e cresce ~1,8×/dia até estabilizar em
        ~8 dias. O menor entre o teto manual e a curva de aquecimento vale.
      </p>

      <div className="flex items-center gap-3">
        <Button onClick={handleSave} disabled={saving} size="sm">
          {saving ? "Salvando…" : "Salvar"}
        </Button>
        {msg && (
          <span
            className={
              msg.startsWith("Erro")
                ? "text-sm text-destructive"
                : "text-sm text-emerald-400"
            }
          >
            {msg}
          </span>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wide text-muted-foreground">
        {label}
      </div>
      <div className="mt-0.5 text-lg font-semibold">{value}</div>
    </div>
  );
}
