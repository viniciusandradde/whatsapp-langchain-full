export const meta = {
  name: 'maturidade-saas',
  description: 'Scorecard de prontidão para produção SaaS: 8 dimensões pontuadas 0-5 + verificação adversarial de bloqueadores + veredito GO/NO-GO',
  phases: [
    { title: 'Avaliar', detail: '1 agente por dimensão de maturidade' },
    { title: 'Verificar', detail: '1 refutador adversarial por bloqueador' },
    { title: 'Síntese', detail: 'score ponderado + veredito go-live' },
  ],
}

const REPO = '/home/dev/projetos/whatsapp-langchain'

const DIMENSAO_SCORE = {
  type: 'object',
  properties: {
    dimensao: { type: 'string' },
    score: { type: 'integer', minimum: 0, maximum: 5 },
    resumo: { type: 'string' },
    evidencias: {
      type: 'array',
      items: {
        type: 'object',
        properties: { path: { type: 'string' }, nota: { type: 'string' } },
        required: ['path', 'nota'],
      },
    },
    gaps: { type: 'array', items: { type: 'string' } },
    bloqueador_producao: { type: 'boolean' },
    justificativa_score: { type: 'string' },
  },
  required: ['dimensao', 'score', 'resumo', 'evidencias', 'gaps', 'bloqueador_producao', 'justificativa_score'],
}

const VERDICT = {
  type: 'object',
  properties: {
    real: { type: 'boolean' },
    severidade_confirmada: { type: 'string' },
    refutacao: { type: 'string' },
  },
  required: ['real', 'refutacao'],
}

const SCORECARD = {
  type: 'object',
  properties: {
    nota_geral: { type: 'integer', minimum: 0, maximum: 100 },
    veredito: { type: 'string', enum: ['GO', 'GO-com-ressalvas', 'NO-GO'] },
    scorecard: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          dimensao: { type: 'string' },
          score: { type: 'integer' },
          bloqueador: { type: 'boolean' },
          resumo: { type: 'string' },
        },
        required: ['dimensao', 'score', 'bloqueador', 'resumo'],
      },
    },
    bloqueadores_confirmados: { type: 'array', items: { type: 'string' } },
    riscos: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          risco: { type: 'string' },
          severidade: { type: 'string' },
          mitigacao: { type: 'string' },
        },
        required: ['risco', 'severidade', 'mitigacao'],
      },
    },
  },
  required: ['nota_geral', 'veredito', 'scorecard', 'bloqueadores_confirmados', 'riscos'],
}

const base = (foco, paths) =>
  `Você audita a prontidão para PRODUÇÃO SAAS do projeto Chat Nexus em ${REPO} (plataforma WhatsApp+IA multi-tenant, FastAPI+Next.js+Postgres, já em produção). Leia ${REPO}/CLAUDE.md para o mapa do sistema. Seja eficiente: leia só os arquivos necessários (~10 no máx).\n\nDIMENSÃO: ${foco}\n\nPontos de partida (leia o relevante, não confie só neles):\n${paths.map((p) => `- ${p}`).join('\n')}\n\nAvalie com rigor de SaaS comercial. score 0-5 (0=ausente, 3=funcional com gaps, 5=production-grade maduro). Liste gaps CONCRETOS com path. Marque bloqueador_producao=true SOMENTE se o gap impede operar como SaaS pago com segurança/confiabilidade (ex.: vazamento cross-tenant, sem backup, sem gate de regressão em CI). Cite path:linha quando possível.\n\nAo final, chame a ferramenta StructuredOutput com o objeto preenchido.`

const DIMENSOES = [
  { key: 'multi-tenancy', peso: 3, prompt: base('Multi-tenancy & isolamento (RLS Postgres)', ['docs/RLS_OPERATIONS.md', 'db/migrations/096*,100*-103*', 'src/whatsapp_langchain/shared/db.py', 'src/whatsapp_langchain/server/middlewares.py', 'tests/integration/test_rls_isolation.py', '49 tabelas tenant via FK indireto sem empresa_id próprio']) },
  { key: 'billing', peso: 3, prompt: base('Billing & monetização (Asaas)', ['src/whatsapp_langchain/server/routes/billing.py', 'src/whatsapp_langchain/server/routes/asaas_webhook.py', 'src/whatsapp_langchain/shared/asaas.py', 'src/whatsapp_langchain/server/dependencies_plano.py', 'db/migrations/059*,105*', 'enforcement de limites, trial, idempotência de webhook']) },
  { key: 'seguranca', peso: 3, prompt: base('Segurança', ['src/whatsapp_langchain/shared/config.py', 'frontend/src/lib/auth.ts', 'src/whatsapp_langchain/server/middlewares.py', 'secrets/rotação, validação de assinatura, CORS, authz']) },
  { key: 'observabilidade', peso: 2, prompt: base('Observabilidade & alerting', ['src/whatsapp_langchain/shared/langfuse_client.py', 'src/whatsapp_langchain/shared/metrics.py', 'src/whatsapp_langchain/server/routes/health.py', 'alerting/on-call, dashboards SLA, health de workers']) },
  { key: 'confiabilidade-ops', peso: 3, prompt: base('Confiabilidade & operação', ['src/whatsapp_langchain/shared/hook_dispatcher.py', 'src/whatsapp_langchain/worker/main.py', 'docs/DOKPLOY.md', 'docker-compose.dokploy.yml', 'CRÍTICO: backup/restore Postgres documentado? disaster recovery? rollback? autoscale?']) },
  { key: 'qualidade-ci', peso: 2, prompt: base('Qualidade, CI & testes', ['.github/workflows/', 'Makefile', 'pyproject.toml', 'frontend/package.json', 'CI roda lint+typecheck+unit ou só e2e? gate de cobertura, testes de frontend?']) },
  { key: 'onboarding', peso: 2, prompt: base('Onboarding & self-service', ['src/whatsapp_langchain/server/routes/empresa_admin.py', 'src/whatsapp_langchain/server/routes/conexao.py', 'criação de empresa, email verification, trial, provisionamento de conexão']) },
  { key: 'performance-escala', peso: 2, prompt: base('Performance & escalabilidade', ['src/whatsapp_langchain/shared/db.py', 'src/whatsapp_langchain/worker/processor.py', 'claim latency (polling vs LISTEN/NOTIFY), concorrência intra-worker, replicas, pool, throughput']) },
]

phase('Avaliar')
const avaliacoes = await pipeline(
  DIMENSOES,
  (d) => agent(d.prompt, { label: `aval:${d.key}`, phase: 'Avaliar', schema: DIMENSAO_SCORE }),
  (score, d) => {
    if (!score) return null
    if (!score.bloqueador_producao) return { d, score, voto: null }
    return agent(
      `Verifique adversarialmente, REFUTANDO por padrão (real=false se houver qualquer dúvida ou se já estiver mitigado).\nDimensão: ${d.key}\nBloqueador alegado: ${score.justificativa_score}\nGaps: ${JSON.stringify(score.gaps)}\nEvidências: ${JSON.stringify(score.evidencias)}\n\nReabra os arquivos citados em ${REPO} e confirme. Só real=true se for um bloqueador GENUÍNO de produção SaaS. Chame StructuredOutput ao final.`,
      { label: `verify:${d.key}`, phase: 'Verificar', schema: VERDICT },
    ).then((v) => ({ d, score, voto: v }))
  },
)

phase('Síntese')
const limpos = avaliacoes.filter(Boolean)
const confirmados = limpos.filter((a) => a.score.bloqueador_producao && a.voto && a.voto.real === true)
log(`${limpos.length} dimensões avaliadas, ${confirmados.length} bloqueadores confirmados`)

const payload = limpos.map((a) => ({
  dimensao: a.d.key,
  peso: a.d.peso,
  score: a.score.score,
  resumo: a.score.resumo,
  gaps: a.score.gaps,
  bloqueador_confirmado: confirmados.includes(a),
}))

const synth = await agent(
  `Sintetize o scorecard de prontidão para produção SaaS do Chat Nexus a partir destas avaliações (JSON). Cada dimensão tem score 0-5 e peso.\n\n${JSON.stringify(payload)}\n\nCalcule nota_geral 0-100 como média PONDERADA pelos pesos (score/5*100). Veredito: NO-GO se houver qualquer bloqueador_confirmado=true; GO-com-ressalvas se nota>=70 sem bloqueador confirmado mas com gaps relevantes; GO se nota>=85 sem gaps relevantes. Preencha scorecard (1 linha/dimensão), bloqueadores_confirmados (frases curtas) e riscos (top-5). pt-BR. Chame StructuredOutput.`,
  { label: 'sintese-maturidade', phase: 'Síntese', schema: SCORECARD },
)

return synth
