/**
 * DSL declarativa de flows pro ZigChat scraper (F4.A).
 *
 * Filosofia: cada flow é um YAML que expressa "o que fazer" — não código
 * imperativo. Roteiro reproduzível, versionável, editável por
 * não-desenvolvedor (PM olhando o ZigChat sabe escrever).
 *
 * Steps suportados:
 *
 *   goto:           navega pra rota
 *   click:          clica em selector CSS
 *   fill:           preenche input por selector
 *   select:         escolhe option em <select> ou PrimeNG dropdown
 *   wait:           espera por timeout|networkidle|selector|ms
 *   wait_for:       atalho — wait por selector específico
 *   screenshot:     full-page com nome custom
 *   capture_payload: marca ponto onde queremos extrair payload da
 *                   próxima request GraphQL específica (operationName
 *                   match, salva em payloads/<op>.json)
 *   assert_route:   confere URL atual contém pattern
 *   assert_text:    confere texto visível no DOM
 *   press:          apertar tecla (Escape, Enter, Tab...)
 *   hover:          passar mouse pra ativar tooltip/menu
 *
 * Steps de safety (evita efeito colateral em produção):
 *
 *   safe_mode:      bool — quando true, bloqueia clicks em botões
 *                   "Salvar"/"Excluir"/"Confirmar" (regex configurável).
 *                   Default true. Permite explorar UI sem mutar dados.
 */

export type FlowStep =
  | { goto: string; wait?: WaitArg }
  | { click: string; safe_mode_bypass?: boolean; optional?: boolean; timeout_ms?: number }
  | { fill: string; with: string; optional?: boolean }
  | { select: string; option: string; optional?: boolean }
  | { wait: WaitArg }
  | { wait_for: string; timeout_ms?: number; optional?: boolean }
  | { screenshot: string }
  | { capture_payload: string; timeout_ms?: number }
  | { assert_route: string }
  | { assert_text: string; selector?: string }
  | { press: string; selector?: string }
  | { hover: string; optional?: boolean; timeout_ms?: number };

export type WaitArg =
  | { networkidle: true; timeout_ms?: number }
  | { selector: string; timeout_ms?: number }
  | { ms: number };

export interface FlowDefinition {
  name: string;
  description?: string;
  /** Tags pra filtrar quais flows rodar (`only_tags: [crud]`). */
  tags?: string[];
  /** Default true — bloqueia mutations destrutivas. */
  safe_mode?: boolean;
  /** Selectors regex que `safe_mode=true` deve bloquear (default lista padrão). */
  safe_mode_block?: string[];
  steps: FlowStep[];
}

export interface FlowResult {
  name: string;
  ok: boolean;
  durationMs: number;
  stepsRun: number;
  stepsTotal: number;
  payloadsCaptured: string[];
  screenshotsCaptured: string[];
  errorMessage?: string;
  errorAtStep?: number;
}
