"use client";

import { useState, useTransition } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarClock, Loader2, Receipt } from "lucide-react";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { BillingTransacao, Empresa, GatewayPagamento, PlanoCatalogo } from "@/lib/api";
import { dataCivil, dataHora } from "@/lib/formato";
import { rotuloPlano } from "@/lib/plano";

import {
  loadPagamentosAction,
  loadPlanosCatalogoAction,
  registrarPagamentoAction,
  setVigenciaAction,
} from "./actions";

const GATEWAY_ROTULO: Record<GatewayPagamento, string> = {
  infinitepay: "InfinitePay (Pix ou cartão)",
  mercadopago: "Mercado Pago (cartão)",
  manual: "Outro (transferência, cortesia…)",
};

/**
 * Plano e vigência (ADR-005 levas E e F) — só o superadmin vê e mexe: é a
 * decisão de cobrança da plataforma, não da empresa.
 *
 * "Registrar pagamento" é a ativação manual (D8): o dono confere o
 * pagamento no painel do gateway e registra aqui — grava em `transacao`,
 * sobe o plano se preciso e estende a vigência; a empresa recebe a
 * confirmação por WhatsApp. A data à mão continua existindo para cortesia,
 * correção e teste.
 */
export function VigenciaSection({ empresa }: { empresa: Empresa }) {
  const queryClient = useQueryClient();
  const [data, setData] = useState(empresa.plano_valido_ate ?? "");
  const [saving, startSaving] = useTransition();
  const [registrando, setRegistrando] = useState(false);

  const pagamentos = useQuery({
    queryKey: ["pagamentos-empresa", empresa.id],
    queryFn: async () => {
      const r = await loadPagamentosAction(empresa.id);
      if (!r.ok) throw new Error(r.error);
      return r.data;
    },
    staleTime: 30_000,
  });
  const catalogo = useQuery({
    queryKey: ["planos-catalogo"],
    queryFn: async () => {
      const r = await loadPlanosCatalogoAction();
      if (!r.ok) throw new Error(r.error);
      return r.data;
    },
    staleTime: 10 * 60_000,
  });

  function invalidar() {
    void queryClient.invalidateQueries({ queryKey: ["pagamentos-empresa", empresa.id] });
    void queryClient.invalidateQueries({ queryKey: ["plano-empresa", empresa.id] });
  }

  function salvarData(valor: string | null) {
    startSaving(async () => {
      const r = await setVigenciaAction(empresa.id, valor);
      if (!r.ok) {
        toast.error(r.error);
        return;
      }
      setData(valor ?? "");
      invalidar();
      toast.success(
        valor ? `Plano válido até ${dataCivil(valor)}.` : "Plano sem vencimento (cortesia)."
      );
    });
  }

  const info = pagamentos.data;
  const planoAtual = info?.plano_atual ?? empresa.plano;
  const validoAte = info?.plano_valido_ate ?? empresa.plano_valido_ate ?? null;

  return (
    <Card className="mt-4">
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <CalendarClock className="size-4" />
          Plano e vigência
        </CardTitle>
        <CardDescription>
          Confira o pagamento no painel do gateway e registre aqui: a vigência é estendida e a
          empresa recebe a confirmação por WhatsApp. Sete, três dias antes e no dia do vencimento
          ela é lembrada; cinco dias depois sem renovação, volta ao plano Free sozinha. Sem data,
          o plano não vence.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <p className="text-sm text-muted-foreground">
          Hoje:{" "}
          <span className="font-medium text-foreground">{rotuloPlano(planoAtual)}</span>
          {validoAte ? (
            <>
              {" "}
              · válido até{" "}
              <span className="font-medium text-foreground">{dataCivil(validoAte)}</span>
            </>
          ) : (
            <> · sem vencimento</>
          )}
        </p>

        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" onClick={() => setRegistrando((v) => !v)} disabled={saving}>
            <Receipt className="size-4" />
            {registrando ? "Fechar" : "Registrar pagamento"}
          </Button>
        </div>

        {registrando && info && (
          <FormPagamento
            empresa={empresa}
            sugestao={info.sugestao}
            planos={(catalogo.data ?? []).filter((p) => p.slug !== "free")}
            planoAtual={planoAtual}
            onRegistrado={(validoAteNovo) => {
              setData(validoAteNovo);
              setRegistrando(false);
              invalidar();
            }}
          />
        )}

        <div className="space-y-2">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Histórico de pagamentos
          </p>
          {pagamentos.isPending ? (
            <p className="text-sm text-muted-foreground">Carregando…</p>
          ) : pagamentos.isError ? (
            <p className="text-sm text-destructive">{pagamentos.error.message}</p>
          ) : info && info.items.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nenhum pagamento registrado ainda.</p>
          ) : (
            <HistoricoPagamentos items={info?.items ?? []} />
          )}
        </div>

        <details className="rounded-md border border-border p-3">
          <summary className="cursor-pointer text-sm font-medium">
            Ajustar a data à mão (cortesia, correção)
          </summary>
          <div className="mt-3 flex flex-wrap items-end gap-2">
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
            <Button
              type="button"
              variant="outline"
              onClick={() => salvarData(data || null)}
              disabled={saving || !data}
            >
              {saving ? <Loader2 className="size-4 animate-spin" /> : null}
              Salvar data
            </Button>
            <Button
              type="button"
              variant="outline"
              onClick={() => salvarData(null)}
              disabled={saving || !validoAte}
            >
              Sem vencimento
            </Button>
          </div>
        </details>
      </CardContent>
    </Card>
  );
}

function FormPagamento({
  empresa,
  sugestao,
  planos,
  planoAtual,
  onRegistrado,
}: {
  empresa: Empresa;
  sugestao: { periodo_inicio: string; periodo_fim: string };
  planos: PlanoCatalogo[];
  planoAtual: string;
  onRegistrado: (validoAte: string) => void;
}) {
  const planoInicial = planos.some((p) => p.slug === planoAtual)
    ? planoAtual
    : (planos[0]?.slug ?? "pro");
  const [planoSlug, setPlanoSlug] = useState(planoInicial);
  const [gateway, setGateway] = useState<GatewayPagamento>("infinitepay");
  const [gatewayId, setGatewayId] = useState("");
  const [valor, setValor] = useState(
    String(planos.find((p) => p.slug === planoInicial)?.preco_mensal_brl ?? "")
  );
  const [inicio, setInicio] = useState(sugestao.periodo_inicio);
  const [fim, setFim] = useState(sugestao.periodo_fim);
  const [observacao, setObservacao] = useState("");
  const [enviando, startEnviar] = useTransition();

  function trocarPlano(slug: string) {
    setPlanoSlug(slug);
    const preco = planos.find((p) => p.slug === slug)?.preco_mensal_brl;
    if (preco != null) setValor(String(preco));
  }

  function registrar() {
    const valorNum = Number(valor.replace(",", "."));
    if (!Number.isFinite(valorNum) || valorNum < 0) {
      toast.error("Informe o valor pago.");
      return;
    }
    if (!inicio || !fim) {
      toast.error("Informe o período coberto.");
      return;
    }
    startEnviar(async () => {
      const r = await registrarPagamentoAction(empresa.id, {
        plano_slug: planoSlug,
        gateway,
        gateway_id: gatewayId.trim() || null,
        valor_brl: valorNum,
        periodo_inicio: inicio,
        periodo_fim: fim,
        observacao: observacao.trim() || null,
      });
      if (!r.ok) {
        toast.error(r.error);
        return;
      }
      toast.success(
        `Pagamento registrado: plano ${r.data.plano_nome} até ${dataCivil(r.data.plano_valido_ate)}` +
          (r.data.whatsapp_enviado ? " — confirmação enviada por WhatsApp." : ".")
      );
      onRegistrado(r.data.plano_valido_ate);
    });
  }

  return (
    <div className="space-y-3 rounded-md border border-border bg-muted/30 p-3">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <div className="space-y-1">
          <Label htmlFor="pg_plano">Plano</Label>
          <Select value={planoSlug} onValueChange={(v: string | null) => v && trocarPlano(v)}>
            <SelectTrigger id="pg_plano" className="w-full" disabled={enviando}>
              <SelectValue>
                {(v: string | null) => planos.find((p) => p.slug === v)?.nome ?? rotuloPlano(v)}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              {planos.map((p) => (
                <SelectItem key={p.slug} value={p.slug}>
                  {p.nome}
                  {p.preco_mensal_brl ? ` — R$ ${p.preco_mensal_brl.toFixed(0)}/mês` : ""}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="pg_gateway">Pago por</Label>
          <Select
            value={gateway}
            onValueChange={(v: string | null) => v && setGateway(v as GatewayPagamento)}
          >
            <SelectTrigger id="pg_gateway" className="w-full" disabled={enviando}>
              <SelectValue>
                {(v: string | null) => (v ? GATEWAY_ROTULO[v as GatewayPagamento] : "")}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              {(Object.keys(GATEWAY_ROTULO) as GatewayPagamento[]).map((g) => (
                <SelectItem key={g} value={g}>
                  {GATEWAY_ROTULO[g]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="pg_id">Identificação no gateway</Label>
          <Input
            id="pg_id"
            value={gatewayId}
            onChange={(e) => setGatewayId(e.target.value)}
            placeholder="número da cobrança / id do pagamento"
            disabled={enviando}
            maxLength={120}
          />
          <p className="text-xs text-muted-foreground">
            Evita registrar o mesmo pagamento duas vezes. Pode ficar vazio.
          </p>
        </div>
        <div className="space-y-1">
          <Label htmlFor="pg_valor">Valor pago (R$)</Label>
          <Input
            id="pg_valor"
            inputMode="decimal"
            value={valor}
            onChange={(e) => setValor(e.target.value)}
            disabled={enviando}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="pg_inicio">Período — início</Label>
          <Input
            id="pg_inicio"
            type="date"
            value={inicio}
            onChange={(e) => setInicio(e.target.value)}
            disabled={enviando}
          />
        </div>
        <div className="space-y-1">
          <Label htmlFor="pg_fim">Período — fim (novo “válido até”)</Label>
          <Input
            id="pg_fim"
            type="date"
            value={fim}
            onChange={(e) => setFim(e.target.value)}
            disabled={enviando}
          />
        </div>
        <div className="space-y-1 sm:col-span-2">
          <Label htmlFor="pg_obs">Observação</Label>
          <Input
            id="pg_obs"
            value={observacao}
            onChange={(e) => setObservacao(e.target.value)}
            placeholder="opcional — aparece no histórico"
            disabled={enviando}
            maxLength={300}
          />
        </div>
      </div>
      <div className="flex justify-end">
        <Button type="button" onClick={registrar} disabled={enviando}>
          {enviando ? <Loader2 className="size-4 animate-spin" /> : <Receipt className="size-4" />}
          Confirmar pagamento
        </Button>
      </div>
    </div>
  );
}

function HistoricoPagamentos({ items }: { items: BillingTransacao[] }) {
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Registrado em</TableHead>
            <TableHead>Plano</TableHead>
            <TableHead>Período</TableHead>
            <TableHead>Pago por</TableHead>
            <TableHead className="text-right">Valor</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.slice(0, 12).map((t) => (
            <TableRow key={t.id}>
              <TableCell className="text-xs text-muted-foreground">{dataHora(t.created_at)}</TableCell>
              <TableCell className="text-xs">{t.plano_nome ?? "—"}</TableCell>
              <TableCell className="text-xs">
                {t.periodo_inicio
                  ? `${dataCivil(t.periodo_inicio)} a ${dataCivil(t.periodo_fim)}`
                  : "—"}
              </TableCell>
              <TableCell className="text-xs">
                {t.gateway ? (GATEWAY_ROTULO[t.gateway as GatewayPagamento] ?? t.gateway) : "—"}
                {t.gateway_id ? ` · ${t.gateway_id}` : ""}
              </TableCell>
              <TableCell className="text-right font-mono text-xs tabular-nums">
                R$ {t.valor_brl.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
