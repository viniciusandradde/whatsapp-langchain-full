import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

/**
 * Gate de UI (ADR-013 do plano de migração para shadcn/ui).
 *
 * Duas camadas, de propósito:
 *
 * 1. **Regra de lint** — só entra quando a contagem já está em zero. Ligar uma
 *    regra com 347 violações não é gate, é ruído: ninguém consegue rodar o
 *    lint e todo mundo aprende a ignorá-lo.
 * 2. **`scripts/ui_metrics.sh --check`** — segura o que ainda não é zero. Ele
 *    compara com a linha de base e falha se qualquer número SUBIR. É o que
 *    impede a dívida de crescer enquanto as ondas não chegam.
 *
 * Conforme cada onda zera uma categoria, a regra correspondente sai da lista
 * "ainda não" abaixo e vira erro de verdade.
 */
const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,

  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
  ]),

  {
    name: "chatnexus/gate-ui",
    files: ["src/**/*.{ts,tsx}"],
    rules: {
      "no-restricted-syntax": [
        "error",
        {
          // O design system em CSS (`vsa-components.css`) tem 46 classes e
          // ZERO uso. Some na Onda 0; esta regra existe pra não voltar.
          selector: "Literal[value=/\\bvsa-(btn|card|input|badge|modal|sidebar|status|spinner|tooltip|quick-action|session|text-gradient)/]",
          message:
            "Classe do design system morto (.vsa-*). Use os primitivos de @/components/ui.",
        },
      ],
      // O assistant-ui é Radix; os nossos primitivos são Base UI. Misturar as
      // duas árvores na mesma tela é o que ADR-012 evita — ele fica confinado
      // às superfícies de IA, onde o modelo de thread de assistente encaixa.
      "no-restricted-imports": [
        "error",
        {
          patterns: [
            {
              group: ["@assistant-ui/*"],
              message:
                "assistant-ui só nas rotas de IA (dashboard/rag, agents/db/[slug], comparação de modelos) — ver ADR-012.",
            },
          ],
        },
      ],
    },
  },

  {
    // As rotas de IA são a exceção do ADR-012.
    name: "chatnexus/gate-ui-excecao-assistant",
    files: [
      "src/app/dashboard/rag/**/*.tsx",
      "src/app/agents/db/**/*.tsx",
      "src/components/ia/**/*.tsx",
    ],
    rules: { "no-restricted-imports": "off" },
  },

  {
    /**
     * Dívida nomeada, não desligada.
     *
     * Estes 10 arquivos disparam `react-hooks/set-state-in-effect` — todos com
     * o mesmo padrão: `setLoading(true)` síncrono no corpo do efeito antes do
     * fetch, ou hidratação de estado a partir de localStorage/DOM depois do
     * mount (que existe justamente por causa dos bugs de FOUC que este repo já
     * teve). Corrigir os dez aqui seria mexer em dez telas num PR que é de
     * fundação visual.
     *
     * A regra segue **error** para todo o resto: código novo não entra assim.
     * Cada arquivo sai desta lista na onda que o migrar.
     */
    name: "chatnexus/divida-set-state-in-effect",
    files: [
      "src/lib/theme.ts",
      "src/components/sidebar-context.tsx",
      "src/app/atendimento/atendimento-shell.tsx",
      "src/app/atendimento/painel-cliente.tsx",
      "src/app/billing/billing-page-client.tsx",
      // `*` em vez de `[id]`: em glob, `[id]` é classe de caractere (um char
      // entre "i" e "d"), não o nome da pasta de rota dinâmica do Next.
      "src/app/companies/*/members/edit-permissions-modal.tsx",
      "src/app/companies/empresa-form.tsx",
      "src/app/dashboard/atendimento/cleanup-zumbis-card.tsx",
      "src/app/dashboard/atendimento/quota-card.tsx",
      "src/app/dashboard/qualidade/comentarios-list.tsx",
    ],
    rules: { "react-hooks/set-state-in-effect": "warn" },
  },
]);

export default eslintConfig;
