"use client";

import { useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Download, FileUp, Upload } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

const MAX_BYTES = 2 * 1024 * 1024;
const LINHAS_PREVIA = 20;
const MODELO = "nome;telefone;email;origem\nMaria Souza;(67) 99999-0000;maria@exemplo.com;Instagram\n";

type Resultado = {
  criados: number;
  ja_existiam: number;
  invalidos: { linha: number; motivo: string }[];
};

/** Prévia só para conferência visual — quem valida de verdade é o servidor. */
function previa(texto: string): string[][] {
  const linhas = texto.replace(/^\ufeff/, "").split(/\r?\n/).filter((l) => l.trim());
  const sep = (linhas[0]?.split(";").length ?? 0) >= (linhas[0]?.split(",").length ?? 0) ? ";" : ",";
  return linhas.slice(0, LINHAS_PREVIA + 1).map((l) => l.split(sep).map((c) => c.replace(/^"|"$/g, "").trim()));
}

function baixarModelo() {
  const url = URL.createObjectURL(new Blob(["\ufeff" + MODELO], { type: "text/csv;charset=utf-8" }));
  const a = document.createElement("a");
  a.href = url;
  a.download = "modelo-clientes.csv";
  a.click();
  URL.revokeObjectURL(url);
}

/** Botão + diálogo "Importar CSV" (mig 201). */
export function ImportarCsvDialog() {
  const router = useRouter();
  const [aberto, setAberto] = useState(false);
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [tabela, setTabela] = useState<string[][]>([]);
  const [arrastando, setArrastando] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [resultado, setResultado] = useState<Resultado | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  function limpar() {
    setArquivo(null);
    setTabela([]);
    setErro(null);
    setResultado(null);
    if (inputRef.current) inputRef.current.value = "";
  }

  async function escolher(f: File | null | undefined) {
    setErro(null);
    setResultado(null);
    if (!f) return;
    if (f.size > MAX_BYTES) {
      setErro("O arquivo passa de 2 MB. Divida em partes menores.");
      return;
    }
    setArquivo(f);
    setTabela(previa(await f.text()));
  }

  async function importar() {
    if (!arquivo) return;
    setEnviando(true);
    setErro(null);
    try {
      const fd = new FormData();
      fd.set("arquivo", arquivo, arquivo.name);
      const r = await fetch("/api/proxy/clientes-importar", { method: "POST", body: fd });
      const j = (await r.json().catch(() => null)) as (Resultado & { error?: string }) | null;
      if (!r.ok || !j) {
        setErro(j?.error ?? "Não foi possível importar o arquivo.");
        return;
      }
      setResultado(j);
      if (j.criados > 0) {
        toast.success(`${j.criados} ${j.criados === 1 ? "cliente cadastrado" : "clientes cadastrados"}`);
        router.refresh();
      }
    } catch {
      setErro("Não foi possível importar o arquivo.");
    } finally {
      setEnviando(false);
    }
  }

  const [cabecalho, ...corpo] = tabela;

  return (
    <>
      <Button type="button" variant="outline" onClick={() => setAberto(true)}>
        <FileUp className="size-4" />
        Importar CSV
      </Button>
      <Dialog
        open={aberto}
        onOpenChange={(v) => {
          setAberto(v);
          if (!v) limpar();
        }}
      >
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Importar clientes</DialogTitle>
            <DialogDescription>
              Planilha em CSV com as colunas nome, telefone, email e origem (só telefone é
              obrigatório). Telefone já cadastrado não é alterado.
            </DialogDescription>
          </DialogHeader>

          {!resultado && (
            <div
              onDragOver={(e) => {
                e.preventDefault();
                setArrastando(true);
              }}
              onDragLeave={() => setArrastando(false)}
              onDrop={(e) => {
                e.preventDefault();
                setArrastando(false);
                void escolher(e.dataTransfer.files?.[0]);
              }}
              className={cn(
                "flex flex-col items-center gap-2 rounded-lg border-2 border-dashed px-4 py-6 text-center text-sm transition-colors",
                arrastando ? "border-primary bg-primary/5" : "border-border"
              )}
            >
              <Upload className="size-6 text-muted-foreground" aria-hidden />
              <p>
                {arquivo ? (
                  <span className="font-medium wrap-anywhere">{arquivo.name}</span>
                ) : (
                  "Arraste o arquivo aqui ou"
                )}
              </p>
              <div className="flex flex-wrap justify-center gap-2">
                <Button type="button" size="sm" variant="secondary" onClick={() => inputRef.current?.click()}>
                  {arquivo ? "Trocar arquivo" : "Escolher arquivo"}
                </Button>
                <Button type="button" size="sm" variant="ghost" onClick={baixarModelo}>
                  <Download className="size-3.5" />
                  Baixar modelo
                </Button>
              </div>
              <input
                ref={inputRef}
                type="file"
                accept=".csv,text/csv"
                className="sr-only"
                onChange={(e) => void escolher(e.target.files?.[0])}
              />
              <p className="text-xs text-muted-foreground">
                Telefone com DDD, por exemplo (67) 99999-0000. Até 5.000 linhas.
              </p>
            </div>
          )}

          {!resultado && cabecalho && (
            <div className="space-y-1">
              <p className="text-xs text-muted-foreground">
                Prévia ({Math.min(corpo.length, LINHAS_PREVIA)} primeiras linhas)
              </p>
              <div className="max-h-56 w-0 min-w-full overflow-auto rounded-md border">
                <table className="w-full text-xs">
                  <thead className="bg-muted/60">
                    <tr>
                      {cabecalho.map((c, i) => (
                        <th key={i} className="px-2 py-1.5 text-left font-medium whitespace-nowrap">
                          {c}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {corpo.map((linha, i) => (
                      <tr key={i} className="border-t">
                        {cabecalho.map((_, j) => (
                          <td key={j} className="px-2 py-1 whitespace-nowrap">
                            {linha[j] ?? ""}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {resultado && (
            <div className="space-y-3 text-sm">
              <ul className="grid grid-cols-3 gap-2 text-center">
                <li className="rounded-md bg-success/10 p-2">
                  <span className="block text-lg font-semibold tabular-nums text-success">
                    {resultado.criados}
                  </span>
                  cadastrados
                </li>
                <li className="rounded-md bg-muted p-2">
                  <span className="block text-lg font-semibold tabular-nums">{resultado.ja_existiam}</span>
                  já existiam
                </li>
                <li className="rounded-md bg-destructive/10 p-2">
                  <span className="block text-lg font-semibold tabular-nums text-destructive">
                    {resultado.invalidos.length}
                  </span>
                  recusados
                </li>
              </ul>
              {resultado.invalidos.length > 0 && (
                <div className="max-h-48 overflow-auto rounded-md border">
                  <ul className="divide-y text-xs">
                    {resultado.invalidos.map((i) => (
                      <li key={i.linha} className="flex gap-3 px-3 py-1.5">
                        <span className="w-16 shrink-0 tabular-nums text-muted-foreground">
                          Linha {i.linha}
                        </span>
                        <span>{i.motivo}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {erro && (
            <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">
              {erro}
            </p>
          )}

          <DialogFooter>
            {resultado ? (
              <>
                <Button type="button" variant="ghost" onClick={limpar}>
                  Importar outro
                </Button>
                <Button type="button" onClick={() => setAberto(false)}>
                  Concluir
                </Button>
              </>
            ) : (
              <>
                <Button type="button" variant="ghost" onClick={() => setAberto(false)}>
                  Cancelar
                </Button>
                <Button type="button" onClick={importar} disabled={!arquivo || enviando}>
                  {enviando ? "Importando…" : "Importar"}
                </Button>
              </>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}
