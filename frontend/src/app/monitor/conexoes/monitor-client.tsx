"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  CheckCircle2,
  CircleAlert,
  TriangleAlert,
  WifiOff,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type {
  ConexaoAlerta,
  MonitorConexao,
  MonitorConexoesResposta,
} from "@/lib/api";
import { dataHora } from "@/lib/formato";
import { cn } from "@/lib/utils";

import { loadMonitorAction } from "./actions";

/** Tick esperado a cada 5 min; acima disto o monitor está parado. */
const TICK_ATRASADO_MIN = 15;

function minutosDesde(iso: string | null | undefined): number | null {
  if (!iso) return null;
  return Math.round((Date.now() - new Date(iso).getTime()) / 60_000);
}

function quandoCurto(iso: string | null | undefined): string {
  const min = minutosDesde(iso);
  if (min === null) return "—";
  if (min < 1) return "agora";
  if (min < 60) return `há ${min} min`;
  const h = Math.round(min / 60);
  return h < 48 ? `há ${h} h` : `há ${Math.round(h / 24)} dias`;
}

function horasCurtas(h: number | null | undefined): string {
  if (h === null || h === undefined) return "—";
  if (h < 1) return `${Math.round(h * 60)} min`;
  if (h < 48) return `${Math.round(h * 10) / 10} h`;
  return `${Math.round(h / 24)} dias`;
}

const ESTADO_LABEL: Record<string, string> = {
  open: "Conectada",
  ready: "Conectada",
  connecting: "Conectando",
  disconnected: "Desconectada",
  error: "Erro",
  pending: "Pendente",
  qr_pending: "Aguardando QR",
  pairing_code_pending: "Aguardando código",
};

function estadoVariant(
  estado: string,
): "success" | "warning" | "destructive" | "secondary" {
  if (estado === "open" || estado === "ready") return "success";
  if (estado === "disconnected" || estado === "error") return "destructive";
  if (estado === "connecting") return "warning";
  return "secondary";
}

const ALERTA_LABEL: Record<string, string> = {
  conexao_caida: "Conexão caída",
  sem_atividade: "Sem mensagens",
};

function motivoAlerta(a: ConexaoAlerta): string {
  const d = a.detalhe ?? {};
  if (a.tipo === "conexao_caida") {
    return typeof d.motivo === "string" ? d.motivo : "conexão fechada";
  }
  const esperadas =
    typeof d.esperadas === "number"
      ? ` (esperadas ≈ ${Math.round(d.esperadas)})`
      : "";
  const sonda =
    d.sonda_ok === true
      ? " · conexão responde"
      : d.sonda_ok === false
        ? " · conexão sem resposta"
        : "";
  return `nada recebido${esperadas}${sonda}`;
}

function nomeConexao(c: {
  display_name: string | null;
  from_number: string | null;
}): string {
  const nome = (c.display_name ?? "").trim();
  const numero = (c.from_number ?? "").startsWith("evolution:")
    ? ""
    : (c.from_number ?? "");
  return [nome, numero].filter(Boolean).join(" ") || "conexão";
}

function temAlerta(c: MonitorConexao): boolean {
  return c.alertas.length > 0;
}

export function MonitorClient({
  inicial,
}: {
  inicial: MonitorConexoesResposta;
}) {
  const [soProblema, setSoProblema] = useState(false);
  const { data, error, isFetching } = useQuery({
    queryKey: ["monitor-conexoes"],
    queryFn: async () => {
      const r = await loadMonitorAction();
      if (!r.ok) throw new Error(r.error);
      return r.data;
    },
    initialData: inicial,
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  const items = data.items;
  const estado = data.estado ?? {};
  const visiveis = soProblema ? items.filter(temAlerta) : items;
  const caidas = items.filter((c) =>
    c.alertas.some((a) => a.tipo === "conexao_caida"),
  ).length;
  // mig 198: silêncio acima da régua da própria conexão é informação, não alerta
  const quietas = items.filter((c) => c.acima_do_normal).length;
  const comProblema = items.filter(temAlerta).length;

  const ultimoTick = estado.ultimo_tick_em ?? null;
  const minutosTick = minutosDesde(ultimoTick);
  const monitorParado = minutosTick === null || minutosTick > TICK_ATRASADO_MIN;
  const evolutionFora = Boolean(estado.evolution_indisponivel_desde);

  return (
    <div className="space-y-4">
      {(monitorParado || evolutionFora || estado.ultimo_tick_ok === false) && (
        <div
          role="status"
          className="flex items-start gap-2.5 rounded-lg border border-warning/40 bg-warning/10 px-4 py-2 text-sm"
        >
          <TriangleAlert
            className="mt-0.5 size-4 shrink-0 text-warning"
            aria-hidden
          />
          <p className="min-w-0 flex-1">
            {evolutionFora
              ? `A Evolution não responde desde ${dataHora(estado.evolution_indisponivel_desde)} — nenhuma conexão pôde ser verificada.`
              : monitorParado
                ? ultimoTick
                  ? `O monitor não verifica as conexões há ${minutosTick} min (esperado a cada 5). Confira o worker.`
                  : "O monitor ainda não fez a primeira verificação."
                : `A última verificação falhou: ${estado.ultimo_erro ?? "erro não informado"}.`}
          </p>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
        <span className="text-muted-foreground">
          Última verificação {quandoCurto(ultimoTick)}
          {ultimoTick ? ` (${dataHora(ultimoTick)})` : ""}
          {isFetching ? " · atualizando…" : ""}
        </span>
        <span className="flex flex-wrap items-center gap-2">
          <Badge variant="outline">{items.length} conexões</Badge>
          {caidas > 0 && <Badge variant="destructive">{caidas} caída(s)</Badge>}
          {quietas > 0 && (
            <Badge
              variant="outline"
              title="Sem mensagens há mais tempo que o normal desta conexão; o Nexus envia uma verificação ao próprio número — alerta só se ela não voltar."
            >
              {quietas} quieta{quietas > 1 ? "s" : ""} acima do normal
            </Badge>
          )}
          {comProblema === 0 && <Badge variant="success">tudo normal</Badge>}
        </span>
        <span className="ml-auto flex items-center gap-2">
          <Switch
            id="so-problema"
            checked={soProblema}
            onCheckedChange={setSoProblema}
          />
          <Label htmlFor="so-problema">Só com problema</Label>
        </span>
      </div>

      {error ? (
        <p className="text-sm text-destructive">
          Não foi possível atualizar:{" "}
          {error instanceof Error ? error.message : "erro"}.
        </p>
      ) : null}

      <Card>
        <CardContent className="p-0">
          {/* w-0 min-w-full: a tabela não contribui largura mínima ao <main>
              (item flex sem min-w-0) — sem isto a página inteira alargava e
              as últimas colunas saíam do viewport. */}
          <div className="w-0 min-w-full overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Cliente</TableHead>
                  <TableHead>Conexão</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead>Verificação</TableHead>
                  <TableHead>Última mensagem</TableHead>
                  <TableHead>Eco</TableHead>
                  <TableHead>Entrega</TableHead>
                  <TableHead className="text-right">Recebidas 24 h</TableHead>
                  <TableHead>Alerta</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {visiveis.length === 0 ? (
                  <TableRow>
                    <TableCell
                      colSpan={7}
                      className="py-8 text-center text-muted-foreground"
                    >
                      {soProblema
                        ? "Nenhuma conexão com problema."
                        : "Nenhuma conexão ativa."}
                    </TableCell>
                  </TableRow>
                ) : (
                  visiveis.map((c) => <LinhaConexao key={c.conexao_id} c={c} />)
                )}
              </TableBody>
            </Table>
          </div>
        </CardContent>
      </Card>

      {data.resolvidos_recentes.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">
              Normalizadas nas últimas 48 h
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-1 text-sm">
            {data.resolvidos_recentes.map((r) => (
              <p key={r.id} className="flex flex-wrap items-center gap-2">
                <CheckCircle2
                  className="size-3.5 shrink-0 text-success"
                  aria-hidden
                />
                <span className="font-medium">
                  {r.empresa_nome} ({r.empresa_id})
                </span>
                <span className="text-muted-foreground">
                  {nomeConexao(r)} · {ALERTA_LABEL[r.tipo] ?? r.tipo} ·
                  resolvido {quandoCurto(r.resolvido_em)}
                </span>
              </p>
            ))}
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function LinhaConexao({ c }: { c: MonitorConexao }) {
  const caida = c.alertas.some((a) => a.tipo === "conexao_caida");
  const esperadas = Math.round(c.esperadas_24h);
  return (
    <TableRow className={cn(caida && "bg-destructive/5")}>
      <TableCell>
        <div className="font-medium">{c.empresa_nome}</div>
        <div className="text-xs text-muted-foreground">#{c.empresa_id}</div>
      </TableCell>
      <TableCell>
        <div className="max-w-56 truncate" title={nomeConexao(c)}>
          {(c.display_name ?? "").trim() || nomeConexao(c)}
        </div>
        <div className="text-xs text-muted-foreground">
          {(c.from_number ?? "").startsWith("evolution:")
            ? ""
            : `${c.from_number ?? ""} · `}
          {c.provider === "waba" ? "Meta" : "Evolution"} ·{" "}
          {c.tipo_atendimento === "ia"
            ? "com IA"
            : c.tipo_atendimento === "hibrido"
              ? "híbrido"
              : "manual"}
        </div>
      </TableCell>
      <TableCell>
        <Badge variant={estadoVariant(c.connection_state)}>
          {ESTADO_LABEL[c.connection_state] ?? c.connection_state}
        </Badge>
        {!c.monitorada && (
          <div className="mt-1 text-xs text-muted-foreground">
            ainda não pareada
          </div>
        )}
      </TableCell>
      <TableCell className="whitespace-normal">
        {c.ultimo_health_check_at ? (
          <div className="flex items-start gap-1.5">
            {c.ultimo_health_check_ok ? (
              <CheckCircle2
                className="mt-0.5 size-3.5 shrink-0 text-success"
                aria-hidden
              />
            ) : (
              <CircleAlert
                className="mt-0.5 size-3.5 shrink-0 text-destructive"
                aria-hidden
              />
            )}
            <div>
              <div title={dataHora(c.ultimo_health_check_at)}>
                {quandoCurto(c.ultimo_health_check_at)}
              </div>
              {c.state_message && (
                <div className="max-w-48 text-xs text-muted-foreground">
                  {c.state_message}
                </div>
              )}
            </div>
          </div>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </TableCell>
      <TableCell className="whitespace-normal">
        {c.ultimo_inbound_em ? (
          <div className="space-y-0.5">
            <span
              title={dataHora(c.ultimo_inbound_em)}
              className={c.acima_do_normal ? "text-warning" : undefined}
            >
              {quandoCurto(c.ultimo_inbound_em)}
            </span>
            <div className="text-xs text-muted-foreground">
              {c.limite_normal_h === null
                ? "sem histórico para uma régua"
                : c.hora_ativa === false
                  ? "fora do horário em que recebe"
                  : `normal até ${horasCurtas(c.limite_normal_h)}`}
            </div>
          </div>
        ) : (
          <span className="text-muted-foreground">nunca</span>
        )}
      </TableCell>
      <TableCell className="whitespace-normal">
        {!c.eco.ativo ? (
          <span className="text-muted-foreground">—</span>
        ) : c.eco.pendente_desde ? (
          <span className="text-warning" title={dataHora(c.eco.pendente_desde)}>
            aguardando ({quandoCurto(c.eco.pendente_desde)})
          </span>
        ) : c.eco.falhas > 0 ? (
          <span className="text-destructive">
            não voltou {c.eco.falhas}×
          </span>
        ) : c.eco.ultimo_em ? (
          <span className="text-success" title={dataHora(c.eco.ultimo_em)}>
            ✓ {quandoCurto(c.eco.ultimo_em)}
          </span>
        ) : (
          <span className="text-muted-foreground">ainda não enviado</span>
        )}
      </TableCell>
      <TableCell>
        {c.ultimo_ack_em ? (
          <span className="text-success" title={dataHora(c.ultimo_ack_em)}>
            ✓ {quandoCurto(c.ultimo_ack_em)}
          </span>
        ) : (
          <span className="text-muted-foreground">—</span>
        )}
      </TableCell>
      <TableCell className="text-right tabular-nums">
        {c.recebidas_24h.toLocaleString("pt-BR")}
        <span className="text-muted-foreground">
          {" "}
          / ≈ {esperadas.toLocaleString("pt-BR")}
        </span>
      </TableCell>
      <TableCell className="whitespace-normal">
        {c.alertas.length === 0 ? (
          <span className="text-muted-foreground">—</span>
        ) : (
          <div className="max-w-64 space-y-1">
            {c.alertas.map((a) => (
              <div key={a.id} className="flex items-start gap-1.5">
                {a.tipo === "conexao_caida" ? (
                  <WifiOff
                    className="mt-0.5 size-3.5 shrink-0 text-destructive"
                    aria-hidden
                  />
                ) : (
                  <TriangleAlert
                    className="mt-0.5 size-3.5 shrink-0 text-warning"
                    aria-hidden
                  />
                )}
                <div>
                  <span
                    className={cn(
                      "font-medium",
                      a.tipo === "conexao_caida"
                        ? "text-destructive"
                        : "text-warning",
                    )}
                  >
                    {ALERTA_LABEL[a.tipo] ?? a.tipo}
                  </span>
                  <span className="text-muted-foreground">
                    {" "}
                    {quandoCurto(a.criado_em)}
                  </span>
                  <div className="text-xs text-muted-foreground">
                    {motivoAlerta(a)}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </TableCell>
    </TableRow>
  );
}
