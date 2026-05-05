/**
 * Detecta componentes Angular/PrimeNG no DOM e sugere equivalentes
 * shadcn/ui pra acelerar port pra Nexus (Next + shadcn).
 *
 * Heurística baseada em tag name custom (PrimeNG usa `p-*` prefix:
 * p-table, p-dialog, p-dropdown, p-tabview…) + classes comuns.
 *
 * Retorna inventário com count por tipo + páginas onde aparece.
 * Output: components.md por run + um global mesclando tudo.
 */

import type { Page } from "playwright";

export interface ComponentMatch {
  primeNgTag: string;
  /** Equivalente shadcn sugerido (ou null se "criar custom"). */
  shadcnEquivalent: string | null;
  /** Arquivo shadcn (relativo a frontend/src/components/ui/). */
  shadcnFile?: string;
  notes?: string;
}

export interface ComponentInventoryRow {
  primeNgTag: string;
  shadcnEquivalent: string | null;
  count: number;
  pages: string[];
}

export interface ComponentInventory {
  generatedAt: string;
  totalUniqueTags: number;
  rows: ComponentInventoryRow[];
}

/**
 * Mapping curado PrimeNG → shadcn. Gerado manualmente baseado em
 * docs PrimeNG (https://primefaces.org/primeng/) e shadcn
 * (https://ui.shadcn.com/docs/components).
 */
const MAPPING: Record<string, ComponentMatch> = {
  // Tabela
  "p-table": {
    primeNgTag: "p-table",
    shadcnEquivalent: "Table",
    shadcnFile: "table.tsx",
    notes: "Filtros/sort/paginação no shadcn precisam impl manual ou usar tanstack-table",
  },
  "p-paginator": {
    primeNgTag: "p-paginator",
    shadcnEquivalent: "Pagination",
    shadcnFile: "pagination.tsx",
  },

  // Forms
  "p-inputtext": {
    primeNgTag: "p-inputtext",
    shadcnEquivalent: "Input",
    shadcnFile: "input.tsx",
  },
  "p-inputtextarea": {
    primeNgTag: "p-inputtextarea",
    shadcnEquivalent: "Textarea",
    shadcnFile: "textarea.tsx",
  },
  "p-inputnumber": {
    primeNgTag: "p-inputnumber",
    shadcnEquivalent: "Input type='number'",
    shadcnFile: "input.tsx",
    notes: "Spinner buttons fica como custom",
  },
  "p-password": {
    primeNgTag: "p-password",
    shadcnEquivalent: "Input type='password'",
    shadcnFile: "input.tsx",
  },
  "p-checkbox": {
    primeNgTag: "p-checkbox",
    shadcnEquivalent: "Checkbox",
    shadcnFile: "checkbox.tsx",
  },
  "p-radiobutton": {
    primeNgTag: "p-radiobutton",
    shadcnEquivalent: "RadioGroup",
    shadcnFile: "radio-group.tsx",
  },
  "p-dropdown": {
    primeNgTag: "p-dropdown",
    shadcnEquivalent: "Select",
    shadcnFile: "select.tsx",
  },
  "p-multiselect": {
    primeNgTag: "p-multiselect",
    shadcnEquivalent: "MultiSelect (custom usando Command + Popover)",
    notes: "shadcn não tem nativo; use cmdk + popover",
  },
  "p-calendar": {
    primeNgTag: "p-calendar",
    shadcnEquivalent: "DatePicker (Popover + Calendar)",
    shadcnFile: "calendar.tsx",
  },
  "p-button": {
    primeNgTag: "p-button",
    shadcnEquivalent: "Button",
    shadcnFile: "button.tsx",
  },
  "p-fileupload": {
    primeNgTag: "p-fileupload",
    shadcnEquivalent: "Input type='file' (custom wrapper)",
    notes: "Drag-drop fica custom; ver react-dropzone",
  },
  "p-autocomplete": {
    primeNgTag: "p-autocomplete",
    shadcnEquivalent: "Combobox (Command + Popover)",
    notes: "Usa cmdk lib",
  },
  "p-toggleButton": {
    primeNgTag: "p-toggleButton",
    shadcnEquivalent: "Toggle / Switch",
    shadcnFile: "switch.tsx",
  },
  "p-inputswitch": {
    primeNgTag: "p-inputswitch",
    shadcnEquivalent: "Switch",
    shadcnFile: "switch.tsx",
  },
  "p-slider": {
    primeNgTag: "p-slider",
    shadcnEquivalent: "Slider",
    shadcnFile: "slider.tsx",
  },

  // Layout
  "p-dialog": {
    primeNgTag: "p-dialog",
    shadcnEquivalent: "Dialog",
    shadcnFile: "dialog.tsx",
  },
  "p-sidebar": {
    primeNgTag: "p-sidebar",
    shadcnEquivalent: "Sheet",
    shadcnFile: "sheet.tsx",
  },
  "p-confirmdialog": {
    primeNgTag: "p-confirmdialog",
    shadcnEquivalent: "AlertDialog",
    shadcnFile: "alert-dialog.tsx",
  },
  "p-overlaypanel": {
    primeNgTag: "p-overlaypanel",
    shadcnEquivalent: "Popover",
    shadcnFile: "popover.tsx",
  },
  "p-card": {
    primeNgTag: "p-card",
    shadcnEquivalent: "Card",
    shadcnFile: "card.tsx",
  },
  "p-panel": {
    primeNgTag: "p-panel",
    shadcnEquivalent: "Card",
    shadcnFile: "card.tsx",
  },
  "p-accordion": {
    primeNgTag: "p-accordion",
    shadcnEquivalent: "Accordion",
    shadcnFile: "accordion.tsx",
  },
  "p-tabview": {
    primeNgTag: "p-tabview",
    shadcnEquivalent: "Tabs",
    shadcnFile: "tabs.tsx",
  },
  "p-tabpanel": {
    primeNgTag: "p-tabpanel",
    shadcnEquivalent: "TabsContent",
    shadcnFile: "tabs.tsx",
  },
  "p-divider": {
    primeNgTag: "p-divider",
    shadcnEquivalent: "Separator",
    shadcnFile: "separator.tsx",
  },
  "p-fieldset": {
    primeNgTag: "p-fieldset",
    shadcnEquivalent: "Card + Collapsible",
    shadcnFile: "card.tsx",
  },
  "p-scrollpanel": {
    primeNgTag: "p-scrollpanel",
    shadcnEquivalent: "ScrollArea",
    shadcnFile: "scroll-area.tsx",
  },

  // Menu
  "p-menubar": {
    primeNgTag: "p-menubar",
    shadcnEquivalent: "Menubar",
    shadcnFile: "menubar.tsx",
  },
  "p-menu": {
    primeNgTag: "p-menu",
    shadcnEquivalent: "DropdownMenu",
    shadcnFile: "dropdown-menu.tsx",
  },
  "p-contextmenu": {
    primeNgTag: "p-contextmenu",
    shadcnEquivalent: "ContextMenu",
    shadcnFile: "context-menu.tsx",
  },
  "p-breadcrumb": {
    primeNgTag: "p-breadcrumb",
    shadcnEquivalent: "Breadcrumb",
    shadcnFile: "breadcrumb.tsx",
  },
  "p-steps": {
    primeNgTag: "p-steps",
    shadcnEquivalent: "Custom (sem equiv direto)",
    notes: "Stepper UI; desenhar com Tailwind",
  },

  // Feedback
  "p-toast": {
    primeNgTag: "p-toast",
    shadcnEquivalent: "Toast (sonner)",
    shadcnFile: "sonner.tsx",
  },
  "p-progressbar": {
    primeNgTag: "p-progressbar",
    shadcnEquivalent: "Progress",
    shadcnFile: "progress.tsx",
  },
  "p-progressspinner": {
    primeNgTag: "p-progressspinner",
    shadcnEquivalent: "Loader (custom Tailwind animate-spin)",
  },
  "p-tag": {
    primeNgTag: "p-tag",
    shadcnEquivalent: "Badge",
    shadcnFile: "badge.tsx",
  },
  "p-chip": {
    primeNgTag: "p-chip",
    shadcnEquivalent: "Badge",
    shadcnFile: "badge.tsx",
  },
  "p-skeleton": {
    primeNgTag: "p-skeleton",
    shadcnEquivalent: "Skeleton",
    shadcnFile: "skeleton.tsx",
  },
  "p-tooltip": {
    primeNgTag: "p-tooltip",
    shadcnEquivalent: "Tooltip",
    shadcnFile: "tooltip.tsx",
  },
  "p-message": {
    primeNgTag: "p-message",
    shadcnEquivalent: "Alert",
    shadcnFile: "alert.tsx",
  },
  "p-messages": {
    primeNgTag: "p-messages",
    shadcnEquivalent: "Alert",
    shadcnFile: "alert.tsx",
  },

  // Data
  "p-tree": {
    primeNgTag: "p-tree",
    shadcnEquivalent: "Custom (sem equivalente — usar lib externa tipo headless-tree)",
  },
  "p-treetable": {
    primeNgTag: "p-treetable",
    shadcnEquivalent: "Custom (Table + indentação manual)",
  },
  "p-organizationchart": {
    primeNgTag: "p-organizationchart",
    shadcnEquivalent: "Custom (svg ou react-flow)",
  },
  "p-chart": {
    primeNgTag: "p-chart",
    shadcnEquivalent: "Recharts ou Chart.js",
  },
};

export async function detectComponentsOnPage(
  page: Page,
): Promise<string[]> {
  return page.evaluate(() => {
    const tags = new Set<string>();
    const all = document.getElementsByTagName("*");
    for (let i = 0; i < all.length; i++) {
      const t = all[i]!.tagName.toLowerCase();
      if (t.startsWith("p-")) tags.add(t);
    }
    return [...tags];
  });
}

export function buildComponentInventory(
  perPage: Map<string, string[]>,
): ComponentInventory {
  const counts = new Map<string, { count: number; pages: Set<string> }>();
  for (const [page, tags] of perPage) {
    for (const tag of tags) {
      const entry = counts.get(tag) ?? { count: 0, pages: new Set() };
      entry.count += 1;
      entry.pages.add(page);
      counts.set(tag, entry);
    }
  }

  const rows: ComponentInventoryRow[] = [...counts.entries()]
    .map(([tag, info]) => {
      const m = MAPPING[tag];
      return {
        primeNgTag: tag,
        shadcnEquivalent: m?.shadcnEquivalent ?? null,
        count: info.count,
        pages: [...info.pages].sort(),
      };
    })
    .sort((a, b) => b.count - a.count);

  return {
    generatedAt: new Date().toISOString(),
    totalUniqueTags: rows.length,
    rows,
  };
}

export function renderComponentInventoryMd(
  inv: ComponentInventory,
): string {
  const lines: string[] = [];
  lines.push("# Component Inventory — PrimeNG → shadcn");
  lines.push("");
  lines.push(`> Gerado em ${inv.generatedAt}`);
  lines.push(
    `> ${inv.totalUniqueTags} tags PrimeNG únicas detectadas no ZigChat`,
  );
  lines.push("");
  lines.push("## Mapping recomendado");
  lines.push("");
  lines.push("| PrimeNG tag | # uso | shadcn equivalente | Notas |");
  lines.push("|---|---|---|---|");
  for (const r of inv.rows) {
    const eq = r.shadcnEquivalent ?? "—";
    const notes = MAPPING[r.primeNgTag]?.notes ?? "";
    lines.push(`| \`${r.primeNgTag}\` | ${r.count} | ${eq} | ${notes} |`);
  }
  lines.push("");
  lines.push("## Onde cada tag aparece");
  lines.push("");
  for (const r of inv.rows) {
    lines.push(`### \`${r.primeNgTag}\` (${r.count}× em ${r.pages.length} página(s))`);
    for (const p of r.pages) lines.push(`- ${p}`);
    lines.push("");
  }
  return lines.join("\n");
}
