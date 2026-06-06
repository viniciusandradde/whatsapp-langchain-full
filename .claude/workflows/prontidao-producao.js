export const meta = {
  name: 'prontidao-producao',
  description: 'Orquestrador go-live SaaS: roda maturidade-saas + problemas-erros + status-planejamento e sintetiza um relatório executivo único (veredito GO/NO-GO, scorecard, risk register, roadmap de remediação, checklist de produção)',
  phases: [
    { title: 'Auditorias', detail: 'roda os 3 workflows de auditoria em paralelo' },
    { title: 'Síntese', detail: 'relatório executivo de go-live' },
  ],
}

const RELATORIO = {
  type: 'object',
  properties: {
    veredito: { type: 'string', enum: ['GO', 'GO-com-ressalvas', 'NO-GO'] },
    nota: { type: 'integer', minimum: 0, maximum: 100 },
    p0_count: { type: 'integer', minimum: 0 },
    resumo_executivo: { type: 'string' },
    markdown: { type: 'string' },
  },
  required: ['veredito', 'nota', 'p0_count', 'resumo_executivo', 'markdown'],
}

phase('Auditorias')
const [maturidade, problemas, planejamento] = await parallel([
  () => workflow('maturidade-saas'),
  () => workflow('problemas-erros'),
  () => workflow('status-planejamento'),
])

log('Auditorias concluídas — sintetizando relatório executivo')

phase('Síntese')
const relatorio = await agent(
  `Você é um arquiteto sênior avaliando a prontidão do SaaS "Chat Nexus" (plataforma WhatsApp+IA multi-tenant) para operação comercial em produção. A partir dos 3 resultados de auditoria abaixo (JSON), produza um RELATÓRIO EXECUTIVO em pt-BR no campo \`markdown\` (GitHub-flavored markdown, pronto para virar docs/PRONTIDAO_PRODUCAO.md).

=== MATURIDADE (scorecard 8 dimensões) ===
${JSON.stringify(maturidade)}

=== PROBLEMAS/ERROS (achados confirmados por verificação adversarial) ===
${JSON.stringify(problemas)}

=== PLANEJAMENTO (roadmap vs entregue + decisões pendentes) ===
${JSON.stringify(planejamento)}

O markdown DEVE conter, nesta ordem:
1. **Veredito de Go-Live** — GO / GO-com-ressalvas / NO-GO, com 2-3 frases justificando, e a nota de maturidade 0-100.
2. **Scorecard de Maturidade** — tabela das 8 dimensões (dimensão | score 0-5 | bloqueador? | resumo).
3. **Risk Register** — tabela consolidada de riscos/bloqueadores das 3 fontes, ordenada por severidade×probabilidade (risco | severidade P0-P3 | fonte | mitigação).
4. **Roadmap de Remediação** — priorizado: P0 (bloqueadores de go-live) → quick wins → médio prazo. Itens acionáveis com path quando houver.
5. **Status do Planejamento** — o que está Entregue/Parcial/Pendente/Bloqueado + as decisões arquiteturais pendentes.
6. **Checklist de Produção SaaS** — lista marcável ([x]/[ ]) cobrindo: backup/DR, alerting/on-call, CI gates (lint+typecheck+unit), email verification, observabilidade SLA, rotação de secrets, runbooks.

Regras: seja concreto e honesto; cite path:linha dos achados; não invente itens que não estejam nos JSONs; consolide duplicatas entre as 3 fontes. Defina veredito=NO-GO se houver qualquer bloqueador confirmado ou achado P0. Preencha também veredito, nota, p0_count e um resumo_executivo de 3-4 linhas.`,
  { label: 'sintese-executiva', phase: 'Síntese', schema: RELATORIO },
)

return relatorio
