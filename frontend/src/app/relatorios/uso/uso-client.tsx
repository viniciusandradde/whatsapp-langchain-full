"use client";

import { useEffect, useMemo, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  Download,
  Loader2,
  Send,
  TriangleAlert,
} from "lucide-react";

import { ConfirmDestrutivo } from "@/components/confirm-destrutivo";
import { Badge } from "@/components/ui/badge";
import { Button, buttonVariants } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import type { ClienteUso, ConfigUso, RelatorioUso } from "@/lib/api";

import {
  enviarAction,
  loadConfigAction,
  loadRelatorioAction,
  saveConfigAction,
} from "./actions";

const MESES = [
  "janeiro",
  "fevereiro",
  "março",
  "abril",
  "maio",
  "junho",
  "julho",
  "agosto",
  "setembro",
  "outubro",
  "novembro",
  "dezembro",
];

/** Últimas 12 competências, da mais recente para a mais antiga. */
function competenciasRecentes(): { valor: string; rotulo: string }[] {
  const hoje = new Date();
  const lista: { valor: string; rotulo: string }[] = [];
  for (let i = 0; i < 12; i++) {
    const d = new Date(hoje.getFullYear(), hoje.getMonth() - i, 1);
    const valor = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
    const emCurso = i === 0 ? " (em curso)" : "";
    lista.push({
      valor,
      rotulo: `${MESES[d.getMonth()]} de ${d.getFullYear()}${emCurso}`,
    });
  }
  return lista;
}

function num(v: number | null | undefined, casas = 0): string {
  if (v === null || v === undefined) return "—";
  return v.toLocaleString("pt-BR", {
    minimumFractionDigits: casas,
    maximumFractionDigits: casas,
  });
}

export function UsoClient({ clientes }: { clientes: ClienteUso[] }) {
  const competencias = useMemo(() => competenciasRecentes(), []);
  // Default: o último mês FECHADO — o mês corrente é sempre parcial.
  const [competencia, setCompetencia] = useState(
    competencias[1]?.valor ?? competencias[0].valor
  );
  const [selecionado, setSelecionado] = useState<ClienteUso | null>(
    clientes[0] ?? null
  );

  if (clientes.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Nenhum cliente ativo para listar.
      </p>
    );
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[20rem_1fr]">
      <ListaClientes
        clientes={clientes}
        selecionado={selecionado}
        onSelecionar={setSelecionado}
      />

      <div className="space-y-6">
        <div className="flex flex-wrap items-end gap-3">
          <div className="w-56 space-y-1.5">
            <Label htmlFor="competencia">Competência</Label>
            <Select
              value={competencia}
              onValueChange={(v) => v && setCompetencia(v)}
            >
              <SelectTrigger id="competencia">
                {/* Sem o render, o gatilho mostra o VALOR (`2026-07`) em vez
                    do rótulo — o Base UI não casa o texto do item sozinho. */}
                <SelectValue>
                  {(v: string | null) =>
                    competencias.find((c) => c.valor === v)?.rotulo ?? v
                  }
                </SelectValue>
              </SelectTrigger>
              <SelectContent>
                {competencias.map((c) => (
                  <SelectItem key={c.valor} value={c.valor}>
                    {c.rotulo}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        {selecionado ? (
          <PainelCliente
            key={`${selecionado.empresa_id}-${competencia}`}
            cliente={selecionado}
            competencia={competencia}
          />
        ) : null}
      </div>
    </div>
  );
}

function ListaClientes({
  clientes,
  selecionado,
  onSelecionar,
}: {
  clientes: ClienteUso[];
  selecionado: ClienteUso | null;
  onSelecionar: (c: ClienteUso) => void;
}) {
  return (
    <div className="space-y-1.5">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Clientes
      </h2>
      <ul className="space-y-1">
        {clientes.map((c) => {
          const ativo = selecionado?.empresa_id === c.empresa_id;
          return (
            <li key={c.empresa_id}>
              <button
                type="button"
                onClick={() => onSelecionar(c)}
                className={`w-full rounded-md border px-3 py-2 text-left transition-colors ${
                  ativo
                    ? "border-brand-primary bg-brand-primary/10"
                    : "border-transparent hover:bg-muted/60"
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-medium">{c.nome}</span>
                  {c.envio_mensal_ativo ? (
                    <Badge variant="outline" className="text-[10px]">
                      mensal
                    </Badge>
                  ) : null}
                </div>
                {/* O motivo aparece na lista, não só ao tentar enviar: saber
                    que um cliente está sem conexão é informação por si. */}
                {c.motivo ? (
                  <p className="mt-0.5 flex items-center gap-1 text-[11px] text-muted-foreground">
                    <TriangleAlert className="size-3 shrink-0" />
                    {c.motivo}
                  </p>
                ) : (
                  <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">
                    {c.telefone}
                  </p>
                )}
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function PainelCliente({
  cliente,
  competencia,
}: {
  cliente: ClienteUso;
  competencia: string;
}) {
  const [dados, setDados] = useState<RelatorioUso | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [carregando, setCarregando] = useState(true);

  useEffect(() => {
    let vivo = true;
    void loadRelatorioAction(cliente.empresa_id, competencia).then((r) => {
      if (!vivo) return;
      setCarregando(false);
      if (r.ok) setDados(r.data);
      else setErro(r.error);
    });
    return () => {
      vivo = false;
    };
  }, [cliente.empresa_id, competencia]);

  if (carregando) {
    return (
      <p className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="size-4 animate-spin" />
        Montando o relatório…
      </p>
    );
  }
  if (erro) {
    return (
      <div className="rounded-md border border-destructive/50 bg-destructive/10 p-4 text-sm">
        {erro}
      </div>
    );
  }
  if (!dados) return null;

  return (
    <div className="space-y-6">
      <Previa dados={dados} />
      <Acoes cliente={cliente} competencia={competencia} />
      <Agendamento cliente={cliente} />
    </div>
  );
}

function Previa({ dados }: { dados: RelatorioUso }) {
  const t = dados.totais;
  const p = dados.desempenho;
  const cartoes: [string, string, string][] = [
    ["Mensagens", num(t.mensagens), `${num(t.mensagens_por_dia, 1)}/dia`],
    ["Atendimentos", num(t.atendimentos), `${num(t.contatos)} pessoas`],
    [
      "Arquivos lidos",
      num(t.arquivos_lidos),
      `de ${num(t.arquivos_recebidos)} recebidos`,
    ],
    [
      "Resposta média",
      p.seg_medio === null ? "—" : `${num(p.seg_medio, 1)}s`,
      p.taxa_sucesso === null ? "" : `${num(p.taxa_sucesso, 2)}% de sucesso`,
    ],
  ];

  return (
    <div className="space-y-3">
      {dados.parcial ? (
        <p className="flex items-center gap-1.5 text-xs text-warning">
          <AlertCircle className="size-3.5" />
          Mês em curso — os números vão até hoje e não representam o mês fechado.
        </p>
      ) : null}
      <div className="grid gap-px overflow-hidden rounded-md border bg-border sm:grid-cols-2 lg:grid-cols-4">
        {cartoes.map(([rotulo, valor, nota]) => (
          <div key={rotulo} className="bg-background p-3">
            <div className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              {rotulo}
            </div>
            <div className="font-mono text-2xl tabular-nums">{valor}</div>
            {nota ? (
              <div className="text-[11px] text-muted-foreground">{nota}</div>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}

function Acoes({
  cliente,
  competencia,
}: {
  cliente: ClienteUso;
  competencia: string;
}) {
  const [enviando, setEnviando] = useState(false);
  const [resultado, setResultado] = useState<
    { ok: boolean; texto: string } | null
  >(null);
  const [telefone, setTelefone] = useState("");
  const [confirmando, setConfirmando] = useState(false);

  // Route handler do próprio Next: ele é quem carrega o service token. Apontar
  // direto para a FastAPI daria 404 no host do painel.
  const urlPdf = `/api/relatorio-uso-pdf?empresa_id=${cliente.empresa_id}&competencia=${competencia}`;

  const destino = telefone.trim() || cliente.telefone;

  async function disparar() {
    setEnviando(true);
    setResultado(null);
    const r = await enviarAction(
      cliente.empresa_id,
      competencia,
      telefone.trim() || undefined
    );
    setEnviando(false);
    setResultado(
      r.ok
        ? { ok: true, texto: `Relatório de ${r.data.competencia} enviado.` }
        : { ok: false, texto: r.error }
    );
  }

  return (
    <div className="space-y-3 rounded-md border p-4">
      <div className="flex flex-wrap items-end gap-3">
        {/* O route handler do Next repassa o Bearer; abrir em aba nova
            deixa o operador conferir antes de disparar. */}
        <a
          href={urlPdf}
          target="_blank"
          rel="noopener noreferrer"
          className={buttonVariants({ variant: "outline" })}
        >
          <Download className="size-4" />
          Ver o PDF
        </a>

        <div className="w-60 space-y-1.5">
          <Label htmlFor="destino">Enviar para</Label>
          <Input
            id="destino"
            value={telefone}
            onChange={(e) => setTelefone(e.target.value)}
            placeholder={cliente.telefone ?? "+5567999068963"}
            className="font-mono"
          />
        </div>

        <Button
          onClick={() => setConfirmando(true)}
          disabled={enviando || (!cliente.pode_enviar && !telefone.trim())}
        >
          {enviando ? (
            <Loader2 className="size-4 animate-spin" />
          ) : (
            <Send className="size-4" />
          )}
          Enviar no WhatsApp
        </Button>
      </div>

      {!cliente.pode_enviar ? (
        <p className="flex items-center gap-1.5 text-xs text-warning">
          <TriangleAlert className="size-3.5" />
          {cliente.motivo}
        </p>
      ) : (
        <p className="text-xs text-muted-foreground">
          Em branco, vai para o número cadastrado no agendamento.
        </p>
      )}

      <ConfirmDestrutivo
        aberto={confirmando}
        onAbertoChange={setConfirmando}
        titulo="Enviar o relatório agora?"
        objeto={destino ?? undefined}
        descricao={`O cliente recebe o PDF de ${competencia} no WhatsApp, na hora.`}
        rotuloAcao="Enviar"
        tom="serio"
        onConfirmar={disparar}
      />

      {resultado ? (
        <p
          className={`flex items-center gap-1.5 text-sm ${
            resultado.ok ? "text-success" : "text-destructive"
          }`}
        >
          {resultado.ok ? (
            <CheckCircle2 className="size-4" />
          ) : (
            <AlertCircle className="size-4" />
          )}
          {resultado.texto}
        </p>
      ) : null}
    </div>
  );
}

function Agendamento({ cliente }: { cliente: ClienteUso }) {
  const [config, setConfig] = useState<ConfigUso | null>(null);
  const [salvando, setSalvando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [salvo, setSalvo] = useState(false);

  useEffect(() => {
    let vivo = true;
    void loadConfigAction(cliente.empresa_id).then((r) => {
      if (!vivo) return;
      if (r.ok) setConfig(r.data);
      else setErro(r.error);
    });
    return () => {
      vivo = false;
    };
  }, [cliente.empresa_id]);

  async function salvar() {
    if (!config) return;
    setSalvando(true);
    setErro(null);
    setSalvo(false);
    const r = await saveConfigAction(cliente.empresa_id, {
      ativo: config.ativo,
      telefone: config.telefone,
      dia: config.dia,
      horario: config.horario,
      tz: config.tz,
    });
    setSalvando(false);
    if (r.ok) {
      setConfig(r.data);
      setSalvo(true);
    } else {
      setErro(r.error);
    }
  }

  if (!config) return null;

  return (
    <div className="space-y-4 rounded-md border p-4">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-sm font-semibold">Envio automático</h3>
          <p className="text-xs text-muted-foreground">
            Todo mês, no dia marcado, com o mês anterior já fechado.
          </p>
        </div>
        <Switch
          checked={config.ativo}
          onCheckedChange={(v) => setConfig({ ...config, ativo: v })}
        />
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <div className="space-y-1.5">
          <Label htmlFor="tel">Telefone de destino</Label>
          <Input
            id="tel"
            value={config.telefone ?? ""}
            onChange={(e) => setConfig({ ...config, telefone: e.target.value })}
            placeholder="+5567999068963"
            className="font-mono"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="dia">Dia do mês</Label>
          <Input
            id="dia"
            type="number"
            min={1}
            max={28}
            value={config.dia}
            onChange={(e) =>
              setConfig({ ...config, dia: Number(e.target.value) || 1 })
            }
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="hora">Horário ({config.tz})</Label>
          <Input
            id="hora"
            type="time"
            value={config.horario}
            onChange={(e) => setConfig({ ...config, horario: e.target.value })}
          />
        </div>
      </div>

      {config.ultima_tentativa_em ? (
        <p className="text-xs text-muted-foreground">
          Última tentativa em{" "}
          {new Date(config.ultima_tentativa_em).toLocaleString("pt-BR")} —{" "}
          {config.ultimo_status === "ok" ? "enviado" : "falhou"}
          {config.ultimo_erro ? (
            <span className="text-destructive"> · {config.ultimo_erro}</span>
          ) : null}
        </p>
      ) : null}

      <div className="flex items-center gap-3">
        <Button onClick={() => void salvar()} disabled={salvando} variant="outline">
          {salvando ? <Loader2 className="size-4 animate-spin" /> : null}
          Salvar agendamento
        </Button>
        {salvo ? (
          <span className="text-xs text-success">
            Salvo.
          </span>
        ) : null}
        {erro ? <span className="text-xs text-destructive">{erro}</span> : null}
      </div>
    </div>
  );
}
