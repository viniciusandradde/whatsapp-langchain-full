export const meta = {
  name: 'status-planejamento',
  description: 'Status do planejamento vs entregue: coleta roadmap + memória/vault, verifica % real de cada feature contra o código, enumera decisões pendentes e bloqueadores de go-live',
  phases: [
    { title: 'Coletar', detail: 'roadmap (README) + entregue (memória/vault)' },
    { title: 'Verificar', detail: '% real de conclusão por item contra código' },
    { title: 'Decisões', detail: 'decisões arquiteturais pendentes' },
  ],
}

const REPO = '/home/dev/projetos/whatsapp-langchain'
const MEM = '/home/opc/.claude/projects/-home-dev-projetos-whatsapp-langchain/memory'
const PLANS = '/home/opc/.claude/plans'

const ROADMAP = {
  type: 'object',
  properties: {
    itens: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          item: { type: 'string' },
          horizonte: { type: 'string' },
          status_alegado: { type: 'string' },
        },
        required: ['item', 'horizonte', 'status_alegado'],
      },
    },
  },
  required: ['itens'],
}

const ENTREGUE = {
  type: 'object',
  properties: {
    milestones_entregues: { type: 'array', items: { type: 'string' } },
    placeholders_producao: { type: 'array', items: { type: 'string' } },
    features_parciais: { type: 'array', items: { type: 'string' } },
  },
  required: ['milestones_entregues', 'placeholders_producao', 'features_parciais'],
}

const PLAN_ITEM = {
  type: 'object',
  properties: {
    item: { type: 'string' },
    status_alegado: { type: 'string' },
    status_real: { type: 'string', enum: ['Entregue', 'Parcial', 'Pendente', 'Bloqueado'] },
    percentual: { type: 'integer', minimum: 0, maximum: 100 },
    evidencia: { type: 'string' },
    bloqueia_go_live: { type: 'boolean' },
  },
  required: ['item', 'status_alegado', 'status_real', 'percentual', 'evidencia', 'bloqueia_go_live'],
}

const DECISOES = {
  type: 'object',
  properties: {
    decisoes: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          titulo: { type: 'string' },
          status: { type: 'string' },
          impacto_go_live: { type: 'string' },
          recomendacao: { type: 'string' },
        },
        required: ['titulo', 'status', 'impacto_go_live', 'recomendacao'],
      },
    },
  },
  required: ['decisoes'],
}

phase('Coletar')
const [roadmap, entregue] = await parallel([
  () =>
    agent(
      `Leia a seção "Roadmap — próximas sprints" de ${REPO}/README.md e extraia cada item planejado com seu horizonte (curto/médio/longo) e o status alegado pelo doc. Inclua os "🟡 pendentes" explícitos (Calendar v2 S3-S5, métricas Prometheus, LISTEN/NOTIFY, dashboard IA, etc.).`,
      { label: 'coletar:roadmap', phase: 'Coletar', schema: ROADMAP },
    ),
  () =>
    agent(
      `Leia ${MEM}/MEMORY.md e os checkpoints/roadmap_status/todo_workflow_placeholders em ${MEM}/, mais ${REPO}/docs/obsidian-vault/01-Projects e ${PLANS}/. Liste: milestones entregues (resumido), placeholders de produto ainda em produção (ex.: 4 URLs/emails Mackenzie), e features marcadas como ~80% / parciais.`,
      { label: 'coletar:entregue', phase: 'Coletar', schema: ENTREGUE },
    ),
])

phase('Verificar')
const itens = (roadmap?.itens || []).slice(0, 16)
const matriz = (
  await pipeline(itens, (it) =>
    agent(
      `Confira o PERCENTUAL REAL de conclusão do item de roadmap "${it.item}" (status alegado: "${it.status_alegado}") contra o código/migrations reais em ${REPO}. Procure a implementação (src/, frontend/src/, db/migrations/) e diga status_real (Entregue/Parcial/Pendente/Bloqueado), percentual 0-100 e evidencia (path). Marque bloqueia_go_live=true só se a ausência impede operar como SaaS pago.`,
      { label: `chk:${it.item.slice(0, 28)}`, phase: 'Verificar', schema: PLAN_ITEM },
    ),
  )
).filter(Boolean)

phase('Decisões')
const decisoes = await agent(
  `Enumere as DECISÕES ARQUITETURAIS PENDENTES do projeto Chat Nexus que ainda não foram resolvidas, lendo ${REPO}/docs/obsidian-vault/01-Projects (arquivos Convergencia-*, Integracao-ZigChat) e ${REPO}/CLAUDE.md. As 3 conhecidas: (1) menu chatbot legacy vs workflow LangGraph; (2) empresa_membro.role vs perfis RBAC; (3) integração ZigChat (runtime nunca conectado). Para cada: status, impacto no go-live SaaS, e recomendação.`,
  { label: 'decisoes', phase: 'Decisões', schema: DECISOES },
)

const bloqueadores = matriz.filter((m) => m.bloqueia_go_live)
log(`${matriz.length} itens verificados, ${bloqueadores.length} bloqueiam go-live, ${decisoes?.decisoes?.length || 0} decisões pendentes`)

return {
  matriz,
  decisoes_pendentes: decisoes?.decisoes || [],
  milestones_entregues: entregue?.milestones_entregues || [],
  placeholders_producao: entregue?.placeholders_producao || [],
  features_parciais: entregue?.features_parciais || [],
  bloqueadores_planejamento: bloqueadores,
}
