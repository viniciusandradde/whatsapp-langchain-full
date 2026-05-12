"use client";

/**
 * ColetaEditor — editor visual de perguntas pra wizard de coleta por
 * menu_item. Adiciona/remove/reordena perguntas. Cada pergunta tem:
 *
 * - label (textarea com suporte a `{{cliente.nome}}`, `{{coleta.X}}`)
 * - save_as (slug pra usar em templates seguintes)
 * - validate_with (cpf/cnpj/data_br/telefone_br/email/uf/cep/min_len:N/max_len:N/regex:...)
 * - retry_message (texto exibido quando validação falha)
 * - obrigatorio (default true)
 *
 * Vars state local; pai (ItemForm) controla via prop `value` + `onChange`.
 */

import { ChevronDown, ChevronUp, GripVertical, Plus, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import type { ColetaPergunta } from "@/lib/api";

const inputCls =
  "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm focus:outline-none focus-visible:ring-1 focus-visible:ring-ring";
const textareaCls =
  "flex w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm focus:outline-none focus-visible:ring-1 focus-visible:ring-ring";
const selectCls =
  "flex h-9 w-full rounded-md border border-input bg-background text-foreground px-3 py-1 text-sm shadow-sm focus:outline-none focus-visible:ring-1 focus-visible:ring-ring [&>option]:bg-background [&>option]:text-foreground";
const labelCls = "text-xs font-medium";
const helpCls = "text-xs text-muted-foreground";

const VALIDATORS = [
  { v: "", l: "(sem validação)" },
  { v: "cpf", l: "CPF (11 dígitos)" },
  { v: "cnpj", l: "CNPJ (14 dígitos)" },
  { v: "cep", l: "CEP (00000-000)" },
  { v: "uf", l: "UF (sigla 2 letras)" },
  { v: "data_br", l: "Data dd/mm/aaaa" },
  { v: "telefone_br", l: "Telefone BR" },
  { v: "email", l: "E-mail" },
  { v: "min_len:3", l: "Mínimo 3 caracteres" },
  { v: "min_len:5", l: "Mínimo 5 caracteres" },
  { v: "min_len:10", l: "Mínimo 10 caracteres" },
  { v: "max_len:200", l: "Máximo 200 caracteres" },
];

interface Props {
  value: ColetaPergunta[];
  onChange: (next: ColetaPergunta[]) => void;
}

export function ColetaEditor({ value, onChange }: Props) {
  const perguntas = value || [];

  const adicionar = () => {
    onChange([
      ...perguntas,
      {
        label: "",
        save_as: `pergunta_${perguntas.length + 1}`,
        validate_with: "",
        retry_message: "",
        obrigatorio: true,
      },
    ]);
  };

  const remover = (idx: number) => {
    onChange(perguntas.filter((_, i) => i !== idx));
  };

  const atualizar = (idx: number, patch: Partial<ColetaPergunta>) => {
    onChange(perguntas.map((p, i) => (i === idx ? { ...p, ...patch } : p)));
  };

  const mover = (idx: number, delta: number) => {
    const j = idx + delta;
    if (j < 0 || j >= perguntas.length) return;
    const copia = [...perguntas];
    [copia[idx], copia[j]] = [copia[j], copia[idx]];
    onChange(copia);
  };

  return (
    <div className="space-y-3 rounded-md border bg-muted/20 p-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide">
            Coleta antes da ação (triagem)
          </p>
          <p className={helpCls}>
            Wizard de perguntas que roda quando cliente escolhe essa opção,
            ANTES de despachar a ação. Respostas vão pra{" "}
            <code className="rounded bg-muted px-1">coleta_resumo</code> e
            ficam visíveis no drawer pro atendente. Suporta templates{" "}
            <code className="rounded bg-muted px-1">{`{{cliente.nome}}`}</code>{" "}
            e{" "}
            <code className="rounded bg-muted px-1">{`{{coleta.save_as}}`}</code>
            .
          </p>
        </div>
        <Button type="button" size="sm" variant="outline" onClick={adicionar}>
          <Plus className="size-3" />
          Pergunta
        </Button>
      </div>

      {perguntas.length === 0 && (
        <p className={helpCls + " italic"}>
          Nenhuma pergunta. Clique &ldquo;Pergunta&rdquo; pra começar
          (ex: pedir CPF antes de transferir pro departamento).
        </p>
      )}

      <ol className="space-y-3">
        {perguntas.map((p, idx) => (
          <li
            key={idx}
            className="rounded-md border bg-background p-3 space-y-2"
          >
            <div className="flex items-center gap-2">
              <GripVertical className="size-4 text-muted-foreground" />
              <span className="text-xs font-semibold">Pergunta {idx + 1}</span>
              <div className="ml-auto flex items-center gap-1">
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => mover(idx, -1)}
                  disabled={idx === 0}
                  className="h-7 w-7 p-0"
                >
                  <ChevronUp className="size-3" />
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => mover(idx, 1)}
                  disabled={idx === perguntas.length - 1}
                  className="h-7 w-7 p-0"
                >
                  <ChevronDown className="size-3" />
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => remover(idx)}
                  className="h-7 w-7 p-0 text-destructive hover:text-destructive"
                >
                  <Trash2 className="size-3" />
                </Button>
              </div>
            </div>

            <div className="space-y-1">
              <label className={labelCls}>Pergunta (label)</label>
              <textarea
                value={p.label}
                onChange={(e) => atualizar(idx, { label: e.target.value })}
                rows={2}
                maxLength={2000}
                placeholder="Ex: Qual seu CPF?"
                className={textareaCls}
              />
            </div>

            <div className="grid gap-2 sm:grid-cols-2">
              <div className="space-y-1">
                <label className={labelCls}>
                  Variável (save_as){" "}
                  <span className="text-muted-foreground">— slug</span>
                </label>
                <input
                  value={p.save_as}
                  onChange={(e) =>
                    atualizar(idx, {
                      save_as: e.target.value
                        .toLowerCase()
                        .replace(/[^a-z0-9_]/g, "_"),
                    })
                  }
                  maxLength={64}
                  placeholder="ex: cpf_paciente"
                  className={inputCls}
                />
              </div>

              <div className="space-y-1">
                <label className={labelCls}>Validação</label>
                <select
                  value={p.validate_with || ""}
                  onChange={(e) =>
                    atualizar(idx, {
                      validate_with: e.target.value || null,
                    })
                  }
                  className={selectCls}
                >
                  {VALIDATORS.map((v) => (
                    <option key={v.v} value={v.v}>
                      {v.l}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            <div className="space-y-1">
              <label className={labelCls}>
                Mensagem de erro (quando validação falha)
              </label>
              <textarea
                value={p.retry_message || ""}
                onChange={(e) =>
                  atualizar(idx, { retry_message: e.target.value || null })
                }
                rows={1}
                maxLength={2000}
                placeholder="Default: msg padrão do validador"
                className={textareaCls}
              />
            </div>

            <label className="flex items-center gap-2 text-xs">
              <input
                type="checkbox"
                checked={p.obrigatorio ?? true}
                onChange={(e) => atualizar(idx, { obrigatorio: e.target.checked })}
                className="size-4"
              />
              Obrigatória (cliente não pode pular)
            </label>
          </li>
        ))}
      </ol>
    </div>
  );
}
