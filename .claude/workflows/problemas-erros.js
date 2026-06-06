export const meta = {
  name: 'problemas-erros',
  description: 'Caça a bugs/erros/dívida técnica que ameaçam produção: finders multi-modais + loop-until-dry + verificação adversarial (1 refutador nos P0/P1) + severidade P0-P3',
  phases: [
    { title: 'Caçar', detail: 'finders multi-modais em rodadas até secar' },
    { title: 'Verificar', detail: '1 refutador adversarial nos P0/P1' },
  ],
}

const REPO = '/home/dev/projetos/whatsapp-langchain'
const MEM = '/home/opc/.claude/projects/-home-dev-projetos-whatsapp-langchain/memory'

const FINDING = {
  type: 'object',
  properties: {
    titulo: { type: 'string' },
    categoria: { type: 'string' },
    severidade: { type: 'string', enum: ['P0', 'P1', 'P2', 'P3'] },
    path: { type: 'string' },
    linha: { type: 'string' },
    descricao: { type: 'string' },
    impacto_producao: { type: 'string' },
    correcao_sugerida: { type: 'string' },
  },
  required: ['titulo', 'categoria', 'severidade', 'path', 'linha', 'descricao', 'impacto_producao', 'correcao_sugerida'],
}

const FINDINGS_OUT = { type: 'object', properties: { findings: { type: 'array', items: FINDING } }, required: ['findings'] }

const VERDICT = {
  type: 'object',
  properties: {
    real: { type: 'boolean' },
    severidade_confirmada: { type: 'string', enum: ['P0', 'P1', 'P2', 'P3'] },
    refutacao: { type: 'string' },
  },
  required: ['real', 'severidade_confirmada', 'refutacao'],
}

const ctx = `Projeto Chat Nexus em ${REPO} — SaaS WhatsApp+IA multi-tenant (FastAPI+Next.js+Postgres), já em produção. Leia ${REPO}/CLAUDE.md para o mapa. Seja eficiente (leia só o necessário). Severidade: P0=bloqueia produção (vazamento de dados, perda de mensagem, falha de cobrança, RCE); P1=alto risco; P2=médio; P3=baixo/dívida. Reporte SOMENTE problemas reais com path:linha; não invente. Se nada relevante na sua lente, retorne findings:[]. Chame StructuredOutput ao final.`

const FINDERS = [
  { key: 'erro-handling', prompt: `${ctx}\n\nLENTE: tratamento de erro. ~157 except Exception genéricos em src/ que engolem falhas específicas (timeout/conexão/auth), mascaram erros do worker/outbound ou impedem retry. Foque nos que afetam entrega de mensagem, cobrança e webhook.` },
  { key: 'seguranca', prompt: `${ctx}\n\nLENTE: vulnerabilidades de segurança. Injeção SQL (f-string em query), secrets logados, authz ausente em rota /api/*, uso indevido de app.bypass_rls, CORS permissivo, validação de assinatura de webhook contornável.` },
  { key: 'rls-tenant', prompt: `${ctx}\n\nLENTE: vazamento cross-tenant. ~49 tabelas tenant via FK indireto (sem coluna empresa_id própria) — query sem JOIN que escape do RLS? endpoint que não seta app.empresa_id? worker/cron cross-empresa sem escopo? Veja shared/db.py, server/middlewares.py, worker/main.py.` },
  { key: 'placeholders', prompt: `${ctx}\n\nLENTE: placeholders/links de produto em produção. 4 placeholders Mackenzie conhecidos (URLs hospitalmackenzie.com.br, rh@... — ver ${MEM}/todo_workflow_placeholders.md). Varra URLs/emails/tokens hardcoded e TODO/FIXME/XXX/HACK em src/ e frontend/src/ que afetem o cliente.` },
  { key: 'async-db', prompt: `${ctx}\n\nLENTE: correção async/DB. Uso incorreto do pool psycopg, transações sem commit/rollback, advisory lock não liberado, await faltando, idempotência de webhook ausente (Asaas/WABA/Twilio reprocessando).` },
  { key: 'fila-entrega', prompt: `${ctx}\n\nLENTE: garantia de entrega da fila. Ordem mark_done APÓS outbound (at-least-once), lease/backoff, debounce/flush de mídia, NumMedia>1, DLQ de hooks. Algum caminho perde ou duplica mensagem?` },
]

const seen = new Set()
const frescos = []
let dry = 0
let rodada = 0
const MAX_RODADAS = 2

phase('Caçar')
while (rodada < MAX_RODADAS && dry < 1 && (!budget.total || budget.remaining() > 100_000)) {
  rodada++
  const jaVistos = [...seen].slice(0, 30).join(' | ') || '(nenhum ainda)'
  const found = (
    await parallel(
      FINDERS.map((f) => () =>
        agent(`${f.prompt}\n\n[Rodada ${rodada}] Priorize ângulos/arquivos ainda NÃO cobertos. NÃO repita: ${jaVistos}`, {
          label: `find:${f.key}#${rodada}`,
          phase: 'Caçar',
          schema: FINDINGS_OUT,
        }),
      ),
    )
  )
    .filter(Boolean)
    .flatMap((r) => r.findings || [])

  const novos = found.filter((x) => {
    const k = `${x.path}:${x.linha}:${x.titulo}`.toLowerCase()
    if (seen.has(k)) return false
    seen.add(k)
    return true
  })

  if (!novos.length) {
    dry++
    log(`Rodada ${rodada}: 0 achados novos`)
    continue
  }
  frescos.push(...novos)
  log(`Rodada ${rodada}: +${novos.length} novos (total ${frescos.length})`)
}

phase('Verificar')
const criticos = frescos.filter((f) => f.severidade === 'P0' || f.severidade === 'P1')
const naoCriticos = frescos.filter((f) => f.severidade === 'P2' || f.severidade === 'P3')

const verificados = await parallel(
  criticos.map((f) => () =>
    agent(
      `Verifique adversarialmente este achado, REFUTANDO por padrão (real=false se houver dúvida ou se já estiver mitigado).\n${JSON.stringify(f)}\n\nReabra ${f.path} em ${REPO}, confirme a linha citada e ajuste severidade_confirmada se exagerada. Chame StructuredOutput.`,
      { label: `verify:${f.path}`, phase: 'Verificar', schema: VERDICT },
    ).then((v) => ({ ...f, severidade: v && v.real ? v.severidade_confirmada : f.severidade, real: !!(v && v.real), verificado: true })),
  ),
)

const confirmadosCriticos = verificados.filter(Boolean).filter((f) => f.real)
const confirmados = [...confirmadosCriticos, ...naoCriticos.map((f) => ({ ...f, real: true, verificado: false }))]

const por_severidade = {}
for (const f of confirmados) por_severidade[f.severidade] = (por_severidade[f.severidade] || 0) + 1
log(`Confirmados ${confirmados.length} (P0/P1 verificados: ${confirmadosCriticos.length}/${criticos.length}) — ${JSON.stringify(por_severidade)}`)

return {
  confirmados,
  por_severidade,
  total_brutos: frescos.length,
  p0p1_descartados: criticos.length - confirmadosCriticos.length,
  rodadas: rodada,
}
