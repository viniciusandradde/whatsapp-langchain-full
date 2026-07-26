#!/usr/bin/env node
/**
 * Guarda de responsividade — o painel é instalado como PWA em Android/iPhone.
 * Alvo mínimo: 375px (iPhone SE 2/3, iPhone 13 mini).
 *
 * Por que existe: a página /whitelist cortava a coluna de ações em telas
 * estreitas porque o container da tabela usava `overflow-hidden` — que ESCONDE
 * o excedente em vez de deixar rolar. Na varredura, 13 de 22 arquivos com
 * tabela tinham o mesmo defeito.
 *
 * Por que estático e não browser: não há Playwright no projeto, e subir um
 * browser headless no CI é desproporcional pro que precisa ser pego aqui.
 * Este script roda em ~200ms sem dependência nenhuma.
 *
 * Exceção pontual: comentar `responsive-ok` na linha isenta ELA, não o
 * arquivo. Serve pra caso legítimo (ex.: grid de 2 colunas com texto de 11px,
 * que cabe em 375px). Escapatória estreita de propósito — guarda que a gente
 * desliga inteira quando incomoda deixa de ser guarda.
 *
 * Uso:
 *   node scripts/check-responsive.mjs          # falha o build se achar algo
 *   node scripts/check-responsive.mjs --list   # só lista, sai 0
 */

import { readdirSync, readFileSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(fileURLToPath(new URL(".", import.meta.url)), "..");
const SRC = join(ROOT, "src");
const VIEWPORT_MIN = 375;

function walk(dir) {
  const out = [];
  for (const nome of readdirSync(dir)) {
    const caminho = join(dir, nome);
    if (statSync(caminho).isDirectory()) out.push(...walk(caminho));
    else if (nome.endsWith(".tsx")) out.push(caminho);
  }
  return out;
}

const arquivos = walk(SRC);
const problemas = [];

/**
 * `responsive-ok` isenta a linha. Olha também as 3 linhas anteriores porque em
 * JSX o comentário quase nunca cabe na mesma linha do className — costuma
 * ficar logo acima do elemento.
 */
function isento(linhas, i) {
  return linhas
    .slice(Math.max(0, i - 3), i + 1)
    .some((l) => l.includes("responsive-ok"));
}

function reportar(arquivo, linha, regra, detalhe, correcao) {
  problemas.push({
    arquivo: relative(ROOT, arquivo),
    linha,
    regra,
    detalhe,
    correcao,
  });
}

for (const arquivo of arquivos) {
  const texto = readFileSync(arquivo, "utf8");
  const linhas = texto.split("\n");

  // ── Regra 1: tabela sem container rolável ────────────────────────────────
  // O <Table> de components/ui/table.tsx já embrulha em overflow-x-auto; quem
  // usa <table> cru precisa do próprio container.
  const usaComponenteTable = /from "@\/components\/ui\/table"/.test(texto);
  const temContainerRolavel = /overflow-x-auto/.test(texto);
  if (!usaComponenteTable && !temContainerRolavel) {
    const idx = linhas.findIndex((l) => /<table[\s>]/.test(l));
    if (idx !== -1) {
      reportar(
        arquivo,
        idx + 1,
        "tabela-sem-scroll",
        "<table> sem container overflow-x-auto",
        "envolva num <div className=\"overflow-x-auto\"> ou use <Table> de @/components/ui/table",
      );
    }
  }

  // ── Regra 2: largura fixa maior que a tela alvo ──────────────────────────
  // Duas isenções, ambas deliberadas:
  //
  // 1. `pointer-events-none` — decorativo, não é conteúdo, e o
  //    `overflow-x: clip` do globals.css já neutraliza o arrasto lateral.
  // 2. `min-w-[...]` num arquivo que TEM container rolável — esse é
  //    justamente o padrão correto: o min-width força a tabela a manter a
  //    largura útil e ROLAR dentro do container, em vez de espremer as
  //    colunas até ficarem ilegíveis. Sem essa isenção a guarda condenaria a
  //    própria correção que ela existe pra cobrar.
  //
  // `w-[...]` fixo (sem `min-`) segue proibido acima do alvo: esse não rola,
  // só estoura.
  linhas.forEach((linha, i) => {
    if (linha.includes("pointer-events-none")) return;
    if (isento(linhas, i)) return;
    for (const m of linha.matchAll(/\b(min-)?w-\[(\d+)px\]/g)) {
      const ehMinWidth = Boolean(m[1]);
      const px = Number(m[2]);
      if (px <= VIEWPORT_MIN) continue;
      if (ehMinWidth && temContainerRolavel) continue;
      reportar(
        arquivo,
        i + 1,
        "largura-fixa",
        `${m[0]} estoura a tela de ${VIEWPORT_MIN}px`,
        ehMinWidth
          ? "min-w só é seguro dentro de um container overflow-x-auto"
          : "use max-w-[...] com w-full, ou aplique a largura só a partir de sm:",
      );
    }
  });

  // ── Regra 3: grid multi-coluna sem breakpoint ────────────────────────────
  // grid-cols-3 em 375px dá ~110px por coluna — ilegível.
  linhas.forEach((linha, i) => {
    if (isento(linhas, i)) return;
    for (const m of linha.matchAll(/"([^"]*\bgrid-cols-[2-9]\b[^"]*)"/g)) {
      const cls = m[1];
      if (/(?:sm|md|lg|xl|2xl):grid-cols-/.test(cls)) continue;
      reportar(
        arquivo,
        i + 1,
        "grid-sem-breakpoint",
        `"${cls}" não muda de layout no mobile`,
        "use grid-cols-1 sm:grid-cols-N (ou grid-cols-2 sm:grid-cols-N)",
      );
    }
  });
}

// Auto-proteção: guarda que para de enxergar o código aprova tudo em silêncio,
// o que é pior que não ter guarda. Se o coletor quebrar, isto acusa.
if (arquivos.length < 50) {
  console.error(
    `[check-responsive] ERRO: só ${arquivos.length} arquivos .tsx encontrados ` +
      `em ${SRC}. O coletor provavelmente quebrou — abortando em vez de ` +
      `fingir que está tudo certo.`,
  );
  process.exit(2);
}

const listarApenas = process.argv.includes("--list");

if (problemas.length === 0) {
  console.log(
    `[check-responsive] OK — ${arquivos.length} arquivos, nenhum problema ` +
      `de responsividade em ${VIEWPORT_MIN}px.`,
  );
  process.exit(0);
}

const porRegra = problemas.reduce((acc, p) => {
  (acc[p.regra] ??= []).push(p);
  return acc;
}, {});

console.error(
  `\n[check-responsive] ${problemas.length} problema(s) em ${arquivos.length} arquivos:\n`,
);
for (const [regra, itens] of Object.entries(porRegra)) {
  console.error(`  ${regra} (${itens.length}):`);
  for (const p of itens) {
    console.error(`    ${p.arquivo}:${p.linha}  ${p.detalhe}`);
  }
  console.error(`    → ${itens[0].correcao}\n`);
}

process.exit(listarApenas ? 0 : 1);
