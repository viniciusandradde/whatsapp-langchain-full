"use client";

import { useState, useTransition } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { CalendarClock, Loader2 } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { Empresa } from "@/lib/api";
import { dataCivil } from "@/lib/formato";

import { setVigenciaAction } from "./actions";

/**
 * Vigência do plano pago (ADR-005 leva E) — só o superadmin vê e mexe: é a
 * decisão de cobrança da plataforma, não da empresa. Na leva F o "Registrar
 * pagamento" passa a estender esta data sozinho; aqui é o ajuste à mão
 * (cortesia, correção, teste).
 */
export function VigenciaSection({ empresa }: { empresa: Empresa }) {
  const queryClient = useQueryClient();
  const [data, setData] = useState(empresa.plano_valido_ate ?? "");
  const [saving, startSaving] = useTransition();

  function salvar(valor: string | null) {
    startSaving(async () => {
      const r = await setVigenciaAction(empresa.id, valor);
      if (!r.ok) {
        toast.error(r.error);
        return;
      }
      setData(valor ?? "");
      // O cadeado/banner de OUTRA tela lê o plano por esta chave.
      void queryClient.invalidateQueries({ queryKey: ["plano-empresa", empresa.id] });
      toast.success(
        valor ? `Plano válido até ${dataCivil(valor)}.` : "Plano sem vencimento (cortesia)."
      );
    });
  }

  const atual = empresa.plano_valido_ate;
  const ehFree = empresa.plano === "free";

  return (
    <Card className="mt-4">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <CalendarClock className="size-4" />
          Vigência do plano
        </CardTitle>
        <CardDescription>
          Último dia em que o plano pago vale. Sete, três dias antes e no dia a empresa recebe
          um lembrete por WhatsApp (no telefone do resumo diário) e um aviso no painel; cinco
          dias depois do vencimento sem renovação, a conta volta ao plano Free sozinha. Sem
          data, o plano não vence.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-muted-foreground">
          Hoje: <span className="font-medium text-foreground">{empresa.plano}</span>
          {atual ? (
            <>
              {" "}
              · válido até <span className="font-medium text-foreground">{dataCivil(atual)}</span>
            </>
          ) : (
            <> · sem vencimento</>
          )}
          {ehFree && " — o plano Free não vence; a data só faz sentido num plano pago."}
        </p>
        <div className="flex flex-wrap items-end gap-2">
          <div className="space-y-1">
            <Label htmlFor="plano_valido_ate">Válido até</Label>
            <Input
              id="plano_valido_ate"
              type="date"
              value={data}
              onChange={(e) => setData(e.target.value)}
              disabled={saving}
              className="w-44"
            />
          </div>
          <Button type="button" onClick={() => salvar(data || null)} disabled={saving || !data}>
            {saving ? <Loader2 className="size-4 animate-spin" /> : null}
            Salvar data
          </Button>
          <Button
            type="button"
            variant="outline"
            onClick={() => salvar(null)}
            disabled={saving || !atual}
          >
            Sem vencimento
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
