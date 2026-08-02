# Matriz de paridade — Chatvolt × Chat Nexus

> Coleta: 2026-07-28. Critérios de status, esforço e impacto no [README](README.md).
> Evidência do lado Chat Nexus é sempre caminho de código deste repositório.

## Placar

| Status | Linhas |
|---|---:|
| ✅ Temos — paridade | 42 |
| ✅ Temos — **superamos** | 38 |
| 🟡 Parcial | 23 |
| ❌ Não temos | 36 |
| 🚫 Não queremos | 6 |
| **Total** | **145** |

Trinta e seis ausências parece muito até separar por natureza. **Catorze são
canal, widget ou integração de terceiro** — dependem de decisão de
posicionamento, não de capacidade de engenharia. As que realmente doem estão
concentradas em três lugares: **extensibilidade** (ferramenta HTTP, API pública,
webhook de entrada), **funil de vendas** e **mensagens interativas do WhatsApp**.
É o que o [backlog](backlog-gaps.md) prioriza.

Distribuição das ausências por domínio:

| Domínio | ❌ | Domínio | ❌ |
|---|---:|---|---:|
| Agentes | 6 | API e extensibilidade | 4 |
| Canais | 5 | RAG | 3 |
| CRM / funil | 4 | Multi-tenant | 3 |
| Integrações | 4 | Analytics | 1 |
| Widget/embed | 4 | Disparos · Compliance | 1 · 1 |

E o inverso, que a matriz também registra: em **38 linhas superamos** o
Chatvolt — RLS no Postgres, DLQ com retry, custo real de LLM, anti-ban de
disparo, opt-out, NPS completo, auditoria imutável, multi-conexão, departamentos,
turnos. Não estamos atrás em tudo; estamos atrás em coisas específicas.

---

## 1. Agentes

| Domínio | Funcionalidade | Como o Chatvolt resolve | Status | Evidência | Esf. | Imp. | Observação |
|---|---|---|---|---|---|---|---|
| Agentes | Criar agente | 13 campos; nome autogerado | ✅ Temos | `shared/agente_ia.py`, `/agents/db/[slug]` | — | — | Nosso editor tem mais campos (departamento, conexão, modelo, tools) |
| Agentes | Prompt de sistema | Texto único, sem versionamento | ✅ Temos | `agente_ia.prompt` | — | — | Temos variáveis `{{var.*}}` que eles não têm |
| Agentes | Escolha de modelo LLM | `modelName` string livre, "50+" | ✅ Temos | `shared/llm.py::CURATED_MODELS`, mig 138 | — | — | Catálogo curado via OpenRouter, editável em `/models` |
| Agentes | Temperatura | 0.0–1.0 | ✅ Temos | `agente_ia.temperatura` | — | — | |
| Agentes | Chave de LLM do cliente (BYOK) | Permissão "Llm Keys" por organização | ❌ Não temos | — | M | 2 | Nosso modelo é chave única OpenRouter. BYOK muda a economia do produto |
| Agentes | Horário de inatividade | `inactiveHours` **JSON por canal** | 🟡 Parcial | `shared/horario.py` | P | 3 | Temos por empresa, não por canal nem por agente |
| Agentes | Ferramenta HTTP genérica | `http` tool: chama qualquer API, com "Provided By User" e Raw Mode | ❌ **Não temos** | `agents/tools/registry.py` — slug `chamar_webhook` está em `BACKLOG_SLUGS` | M | 5 | **Maior gap funcional do agente.** Detalhe no backlog |
| Agentes | Ferramenta de busca na base | `datastore` tool | ✅ Temos | `agents/tools/knowledge.py` | — | — | |
| Agentes | Transferir para humano | `request_human` tool | ✅ Temos | `agents/tools/cliente_atendimento.py::transfer_to_human` | — | — | |
| Agentes | Marcar como resolvido | `mark_as_resolved` tool | ✅ Temos | `close_atendimento` | — | — | |
| Agentes | Respostas com atraso | `delayed_responses` tool | 🚫 Não queremos | — | — | — | Nosso debounce (`MESSAGE_BUFFER_SECONDS`) resolve o problema real; atraso artificial é teatro |
| Agentes | Follow-up automático | `follow_up_messages` tool | ❌ Não temos | — | M | 4 | Reengajamento de conversa parada. Pedido recorrente |
| Agentes | Tools além das 6 | — | ✅ **Superamos** | `registry.py`: 13 slugs | — | — | Tags, classificação, memória, perfil, anotações, calendário (8 tools) |
| Agentes | Ferramentas de calendário | Não tem | ✅ **Superamos** | `agents/tools/calendar.py`, `shared/calendar_integration.py` | — | — | 8 tools, espelho local em `agendamento`, hooks |
| Agentes | Memória semântica do cliente | Não tem | ✅ **Superamos** | `AsyncPostgresStore`, `cliente_memoria.py` | — | — | |
| Agentes | MCP (Model Context Protocol) | Não tem | ✅ **Superamos** | `/catalog/mcp`, `routes/catalogo.py` | — | — | |
| Agentes | Variáveis de prompt | 25 variáveis de contato/conversa/anúncio | 🟡 Parcial | `shared/variavel.py` (`empresa.*`, `cliente.*`, `var.*`) | P | 3 | Faltam as de conversa: status, prioridade, tags, resumo, frustração |
| Agentes | Variáveis de conversa (KV pelo agente) | Entidade própria, ≤20/≤100 chars, janela de 3 dias | ❌ Não temos | `shared/coleta.py` é só do menu | M | 4 | Estado estruturado por conversa manipulável pelo agente |
| Agentes | Handoff explícito (liga/desliga IA) | `isAiEnabled` booleano + API | 🟡 Parcial | `worker/processor.py` gate derivado | P | **5** | **Nosso estado derivado tem bug conhecido** — ver backlog G1 |
| Agentes | Fine-tuning por correção na Inbox | Botão "improve" → gera datasource Q&A | 🟡 Parcial | `shared/fewshot.py`, `rag_learner.py`, `/dashboard/rag` | P | 4 | Temos o motor; falta o gatilho na tela de quem atende |
| Agentes | Citação de fonte na resposta | Answer sources, desligável | 🟡 Parcial | `agents/tools/knowledge.py:170` cita doc+chunk no contexto | P | 2 | Vai pro contexto do LLM, não é UI clicável |
| Agentes | Sugestões de mensagem | Mensagens de exemplo clicáveis | 🚫 Não queremos | — | — | — | É recurso de widget; não temos widget |
| Agentes | Rate limit do usuário final | Só widget | ✅ Temos | `RATE_LIMIT_PER_HOUR`, `shared/rate_limit.py` | — | — | Nosso vale no WhatsApp, que é onde importa |
| Agentes | Upload de arquivo na conversa | 9 tipos + imagens com visão | ✅ Temos | `worker/media.py`, `shared/file_extractor.py`, `ocr.py` | — | — | Áudio, imagem, PDF, DOCX |
| Agentes | Resposta em áudio | ElevenLabs, espelha modalidade | ❌ Não temos | — | M | 3 | Transcrição de entrada temos; síntese de saída não |
| Agentes | Transcrição de áudio | Groq (BYOK) | ✅ Temos | `worker/media.py` via OpenRouter | — | — | |
| Agentes | Lista de bloqueio por número | `blacklist` por agente | ✅ Temos | `shared/whitelist.py`, mig 133 | — | — | ⚠️ Nome invertido: nossa "whitelist" é bloqueio |
| Agentes | Lista de permissão (allow-list) | `whitelist`: só fala com quem está na lista | ❌ Não temos | — | P | 2 | Útil para piloto controlado |
| Agentes | Modo manual (IA desligada por conexão) | Não tem | ✅ **Superamos** | mig 132, `conexao.tipo_atendimento` | — | — | |
| Agentes | Testar agente no painel | Não documentado | ✅ Temos | `routes/agente.py`, aba Testar | — | — | Compara até 4 modelos. ⚠️ Não injeta `atendimento_id` — tools de atendimento falham |
| Agentes | Múltiplos agentes por empresa | Sim, limitado por plano | ✅ Temos | `agente_ia` | — | — | |
| Agentes | Delegação entre agentes | Step do CRM troca o agente | ✅ Temos | `workflows/nodes.py::make_delegate_to_agent_node` | — | — | |

## 2. Base de conhecimento (RAG)

| Domínio | Funcionalidade | Como o Chatvolt resolve | Status | Evidência | Esf. | Imp. | Observação |
|---|---|---|---|---|---|---|---|
| RAG | Container de fontes | Datastore → Datasource | 🟡 Parcial | `documento_conhecimento` direto na empresa; `shared/pasta.py` agrupa | P | 2 | Temos pastas; falta o vínculo agente↔subconjunto explícito |
| RAG | Upload de arquivo | DOC, CSV, XLS, PDF, JSON; 1–25MB por plano | ✅ Temos | `routes/base_conhecimento.py:201`, `file_extractor.py` | — | — | PDF, DOCX, MD, TXT. **MD vira 1 doc por seção** |
| RAG | Leitura de site (crawl) | 100–1.000 páginas por plano | ❌ Não temos | — | M | 4 | Ingestão mais pedida em onboarding |
| RAG | Google Drive com sync automático | OAuth do cliente, `autosync` | ❌ Não temos | — | G | 3 | |
| RAG | YouTube (transcrição) | Mesma credencial do Drive | ❌ Não temos | — | M | 1 | |
| RAG | Q&A manual | Gerado pelo fine-tuning | ✅ Temos | `shared/fewshot.py` | — | — | |
| RAG | Chunking | Não documentado nem configurável | ✅ **Superamos** | `shared/chunking.py`, `markdown_splitter.py`, mig 018 | — | — | Chunk explícito, com índice e citação |
| RAG | Busca híbrida (vetor + texto) | Não documentado | ✅ **Superamos** | mig 065 `rag_hybrid_search` | — | — | |
| RAG | Reindexação sob demanda | Não documentado | ✅ Temos | `routes/rag_stats.py` | — | — | |
| RAG | Métricas de qualidade do RAG | Não tem | ✅ **Superamos** | `/dashboard/rag`, `rag_stats.py` (19 endpoints), `rag_learner.py` | — | — | Top queries, by-outcome, sugestões, eval, sandbox |
| RAG | Limite de base por plano | Storage em "palavras" | ✅ Temos | `plano_limits.limite_documentos_kb` | — | — | |

## 3. Canais

| Domínio | Funcionalidade | Como o Chatvolt resolve | Status | Evidência | Esf. | Imp. | Observação |
|---|---|---|---|---|---|---|---|
| Canais | WhatsApp Oficial (Cloud API) | Embedded Signup | ✅ Temos | `routes/webhook_waba.py`, `docs/WABA_SETUP.md` | — | — | Mesmo mecanismo |
| Canais | Manter app WhatsApp Business no celular | Destacado como vantagem | ✅ Temos | Propriedade do Embedded Signup | P | 4 | **Temos e não comunicamos.** Ganho de conversão sem código |
| Canais | WhatsApp não-oficial | Z-API e Zapper | ✅ Temos | `routes/evolution_webhook.py`, `docs/EVOLUTION.md` | — | — | Evolution API, com auto-provisionamento |
| Canais | Múltiplos números por empresa | Não limita explicitamente | ✅ **Superamos** | `conexao`, pool na campanha (mig 130) | — | — | Conexão é entidade de primeira classe |
| Canais | Twilio | SMS | 🟡 Parcial | `providers twilio_sandbox/twilio_prod` | — | — | Nosso Twilio é WhatsApp, marcado legado (mig 114). SMS não temos |
| Canais | Telegram | Bot via BotFather | ❌ Não temos | — | M | 2 | |
| Canais | Instagram (DM + comentários) | App Meta do cliente | ❌ Não temos | — | G | 3 | Comentário em post é aquisição, não atendimento |
| Canais | Slack | OAuth, DM + menção | 🚫 Não queremos | — | — | — | Canal interno; nosso ICP atende cliente final |
| Canais | Mercado Livre | Perguntas + pós-venda, por produto | ❌ Não temos | — | G | 3 | Único canal de e-commerce deles |
| Canais | Widget no site | Bubble, standard, iframe, standalone | ❌ Não temos | — | G | 3 | Ver domínio 7 |
| Canais | Mensagens interativas WhatsApp | 6 tipos: botões, listas, CTA, localização, contato | ❌ **Não temos** | `shared/outbound.py` só texto/mídia | M | **5** | Botão nativo reduz drasticamente erro de menu numérico |
| Canais | Templates HSM | Listar, **criar**, enviar | ✅ Temos | `routes/waba_templates.py` (7 endpoints, inclui criar e sync) | — | — | |
| Canais | Grupos de WhatsApp | Evento de grupo sem menção (Z-API) | 🟡 Parcial | `routes/captura_evolution.py` captura grupos | P | 2 | Capturamos para disparo; não atendemos dentro do grupo |
| Canais | Roteamento por conexão | Canal acoplado ao agente | ✅ **Superamos** | `conexao` separada, `is_default`, mig 108 | — | — | Modelo melhor para multi-número |
| Canais | Histórico sobrevive a remoção do número | Não documentado | ✅ **Superamos** | mig 129: FK SET NULL + snapshot do canal | — | — | |

## 4. CRM / funil

| Domínio | Funcionalidade | Como o Chatvolt resolve | Status | Evidência | Esf. | Imp. | Observação |
|---|---|---|---|---|---|---|---|
| CRM | Contatos | CRUD + paginação por cursor | ✅ Temos | `shared/cliente.py`, `/clientes` | — | — | |
| CRM | Variáveis por contato | KV persistente entre conversas | 🟡 Parcial | `cliente_memoria.py` (semântica) | P | 3 | Nossa memória é semântica, não KV consultável |
| CRM | Conversa com status | `RESOLVED`/`UNRESOLVED`/`HUMAN_REQUESTED` | ✅ Temos | `atendimento.status` | — | — | Nosso ciclo é mais rico (aberto→em_andamento→resolvido) |
| CRM | Prioridade da conversa | `LOW`/`MEDIUM`/`HIGH` | ✅ Temos | `classificar_atendimento` grava prioridade | — | — | |
| CRM | Atribuição a operador | `assign` com **409 + `force`** | 🟡 Parcial | `shared/atendimento.py::claim_atendimento` | P | 2 | Temos claim; falta o conflito explícito com `force` |
| CRM | ACL por conversa | `allowedUserIds` | 🟡 Parcial | RBAC `.own`/`.all` + departamento | — | — | Nosso é por perfil, o deles por linha |
| CRM | Notas internas | CRUD completo | ✅ Temos | `shared/nota_interna.py`, mig 085-089 | — | — | |
| CRM | Tags na conversa | Add/remove, inclusive automático por step | ✅ Temos | `shared/atendimento_tag.py`, tags multi-cor | — | — | |
| CRM | Resumo automático da conversa | `{summary}` | 🟡 Parcial | `CONTEXT_STRATEGY=summarize` resume contexto | M | 3 | Resumimos para o LLM; não persistimos resumo visível ao operador |
| CRM | Score de frustração (0–100) | `{frustration-level}` | ❌ Não temos | — | M | 3 | Priorização de fila por risco de perda |
| CRM | Funil kanban com drag-and-drop | Flux CRM: cenários + steps | ❌ **Não temos** | `workflows/` é fluxo conversacional, não funil de vendas | G | **5** | Ver backlog G3 — o gap estratégico |
| CRM | Condição de entrada em linguagem natural | Avaliada por LLM | 🟡 Parcial | `workflows/nodes.py::make_branch_node` — condição determinística | M | 3 | Diferença de filosofia, não só de recurso |
| CRM | Prompt extra por etapa | Anexado ao prompt do agente | ❌ Não temos | — | M | 4 | Agente muda de comportamento por fase sem trocar de agente |
| CRM | Avanço automático por tempo | Auto next step (min/h/dias) | ❌ Não temos | — | M | 4 | Base para follow-up e escalonamento |
| CRM | Padrões automáticos por etapa | Status, prioridade, IA, tags +/−, atribuição | 🟡 Parcial | `menu_item` aplica algumas ações | M | 3 | |
| CRM | Atribuição aleatória em pool | `random_among_selected` | ✅ Temos | `pick_best_atendente` + turnos (mig 112) | — | — | Nosso considera carga e jornada — melhor |
| CRM | Log de trajetória no funil | `/crm/conversationLog`, editável | ✅ Temos | `shared/audit.py`, `audit_governanca` (mig 083/084) | — | — | **Nosso é imutável**; o deles aceita PATCH/DELETE |
| CRM | Departamentos / times | Não existe no modelo | ✅ **Superamos** | `shared/departamento.py`, hierárquico | — | — | |
| CRM | Turnos e jornada | Não tem | ✅ **Superamos** | `shared/turno.py`, mig 112 | — | — | Gate de distribuição |
| CRM | Abas pessoais do operador | Não tem | ✅ **Superamos** | `shared/aba.py`, mig 085 | — | — | |
| CRM | Histórico com filtro e exportação | Não documentado | ✅ **Superamos** | `routes/historico.py`, export CSV/XLSX, mig 110 | — | — | |

## 5. Disparos / campanhas

| Domínio | Funcionalidade | Como o Chatvolt resolve | Status | Evidência | Esf. | Imp. | Observação |
|---|---|---|---|---|---|---|---|
| Disparos | Envio em massa | Dispatches | ✅ Temos | `shared/campanha.py`, `shared/disparo.py` | — | — | |
| Disparos | Lista de contatos por CSV | Upload + mapeamento de coluna + revisão | 🟡 Parcial | `/disparador/contatos`, captura por extensão | P | 3 | Capturamos do WhatsApp; falta importar CSV com mapeamento |
| Disparos | Agendamento | Data/hora ou imediato | ✅ Temos | mig 124 `campanha_scheduled` | — | — | |
| Disparos | Template HSM na campanha | Sim | ✅ Temos | mig 113 | — | — | |
| Disparos | Mídia na campanha | Não documentado | ✅ Temos | mig 123 | — | — | |
| Disparos | **Disparo entrega no funil** | Escolhe cenário CRM + step inicial | ❌ **Não temos** | — | M | **5** | Depende do funil (G3). É o que transforma disparo em operação de vendas |
| Disparos | Opt-out / descadastro | **Não documentado** | ✅ **Superamos** | `shared/opt_out.py` — detecta palavra-chave e suprime | — | — | Risco legal deles, vantagem nossa |
| Disparos | Intervalo e jitter anti-ban | Não documentado | ✅ **Superamos** | mig 120 `campanha_jitter` | — | — | |
| Disparos | Teto diário e aquecimento | Não documentado | ✅ **Superamos** | mig 126, `shared/conexao_quota.py` | — | — | Reagenda ao bater o teto, não aborta |
| Disparos | Pausa periódica | Não documentado | ✅ **Superamos** | mig 127 | — | — | |
| Disparos | Pool de conexões na campanha | Não documentado | ✅ **Superamos** | mig 130 | — | — | Distribui risco entre números |
| Disparos | Captura de contatos e grupos | Não tem | ✅ **Superamos** | Extensão Chrome, migs 118-125 | — | — | |
| Disparos | Fila materializada | `populate-queue` | ✅ Temos | `message_queue` com lease | — | — | |

## 6. Integrações

| Domínio | Funcionalidade | Como o Chatvolt resolve | Status | Evidência | Esf. | Imp. | Observação |
|---|---|---|---|---|---|---|---|
| Integrações | Webhooks de saída | 9 eventos | ✅ **Superamos** | `shared/hook.py::EVENTOS_VALIDOS` — **12 eventos** | — | — | Atendimento, agendamento e menu |
| Integrações | Confiabilidade do webhook | Health check antes de salvar + auto-bloqueio | 🟡 Parcial | Retry exponencial + DLQ (mig 023) | P | 3 | **Abordagens complementares** — a deles previne, a nossa recupera |
| Integrações | Assinatura HMAC do webhook | Não tem (header estático) | 🟡 Parcial | Header estático | P | 3 | Nenhum dos dois assina. Oportunidade de diferenciação |
| Integrações | Webhook de entrada (enriquecer contato) | URL chamada para buscar dados externos | ❌ Não temos | — | M | 4 | Busca sob demanda evita sincronizar e reter dado de terceiro |
| Integrações | Make | App custom | ❌ Não temos | — | M | 3 | |
| Integrações | n8n / Zapier | **Nenhum dos dois** | ❌ Não temos | — | M | 3 | Empate em ausência; n8n é forte no Brasil |
| Integrações | Sandbox de código (JS) | VoltAPI, experimental | 🚫 Não queremos | — | — | — | Ver "Não replicar" no backlog |
| Integrações | E-commerce | Só Mercado Livre | ❌ Não temos | — | G | 3 | |
| Integrações | Crisp | `/integrations/crisp/{config,widget}` | 🚫 Não queremos | — | — | — | Não documentado. Crisp é concorrente de nicho web; fora do ICP |
| Integrações | Google Calendar | Não tem | ✅ **Superamos** | `shared/calendar_integration.py`, Calendar v2 | — | — | |
| Integrações | Billing (Asaas) | Stripe presumido | ✅ Temos | `shared/asaas.py`, mig 105 | — | — | Asaas é adequado ao mercado BR |
| Integrações | Wareline (ERP) | Não tem | ✅ Temos | `routes/integracoes_wareline.py` | — | — | Integração vertical nossa |

## 7. Widget / embed

| Domínio | Funcionalidade | Como o Chatvolt resolve | Status | Evidência | Esf. | Imp. | Observação |
|---|---|---|---|---|---|---|---|
| Widget | Balão flutuante no site | ESM de CDN, `initBubble({agentId})` | ❌ Não temos | — | G | 3 | Porta de entrada do plano gratuito deles |
| Widget | Modo inline / iframe / standalone | 3 modos | ❌ Não temos | — | G | 2 | |
| Widget | Customização visual | `interfaceConfig` no agente | ❌ Não temos | — | M | 2 | |
| Widget | Agente público sem autenticação | `visibility: public` | ❌ Não temos | — | M | 2 | Pré-requisito do widget anônimo |
| Widget | Remover marca (white-label) | Só no plano Pro | ✅ **Superamos** | mig 115: logo, nome e cores por empresa | — | — | Nosso white-label é do painel inteiro, não de um balão |

## 8. API e extensibilidade

| Domínio | Funcionalidade | Como o Chatvolt resolve | Status | Evidência | Esf. | Imp. | Observação |
|---|---|---|---|---|---|---|---|
| API | API pública para terceiros | 112 endpoints, portal Mintlify | ❌ **Não temos** | API key só cobre Disparador | M | **5** | Temos 330 endpoints internos e nenhum contrato externo. Ver backlog G2 |
| API | Autenticação por chave | Bearer, sem escopo, sem expiração | ✅ **Superamos** | `shared/api_key.py`: escopo, hash, prefixo, expiração | — | — | Nosso modelo é melhor e está subutilizado |
| API | Rate limit da API | Não documentado | ✅ **Superamos** | `shared/rate_limit.py` + middleware 60/min | — | — | |
| API | Documentação pública | Mintlify com OpenAPI | ❌ Não temos | Swagger interno | M | 4 | Sem portal, não há como terceiro integrar |
| API | Versionamento da API | Não tem (`/api/` e `/` misturados) | ❌ Não temos | — | P | 3 | Fazer certo desde o início custa pouco |
| API | Perguntar ao agente via API | `POST /agents/{id}/query` | 🟡 Parcial | `routes/agente.py` aba Testar | P | 4 | Existe internamente; falta expor com contrato |
| API | Registrar mensagem sem enviar | `message-register` | ❌ Não temos | — | P | 3 | Injeta contexto externo na timeline |
| API | Enviar mensagem por API | Sim | 🟡 Parcial | `shared/outbound.py::send_outbound_manual` (só UI) | P | 4 | |

## 9. Analytics

| Domínio | Funcionalidade | Como o Chatvolt resolve | Status | Evidência | Esf. | Imp. | Observação |
|---|---|---|---|---|---|---|---|
| Analytics | Painel de métricas | Existe (`/analytics` + filtros); profundidade desconhecida | ✅ Temos | `/dashboard/atendimento`, `/dashboard/ia` | — | — | Confirmado no `_buildManifest.js`; falta captura para comparar |
| Analytics | Auditoria de consumo de crédito | `/analytics/CreditsAuditTab` | ✅ Temos | `/governanca/ia-budget`, `ia_execucao` | — | — | Nosso mede custo real em USD (mig 139); o deles expõe crédito ao cliente |
| Analytics | Dashboard customizável pelo cliente | `/custom-dashboard` | ❌ Não temos | — | G | 2 | Não documentado; profundidade desconhecida |
| Analytics | NPS / CSAT | Só evento `NPS_INTERACTION` de webhook | ✅ **Superamos** | `shared/avaliacao.py`, `/dashboard/qualidade`, migs 073/074, `docs/NPS.md` | — | — | Captura, follow-up, ranking, NPS clássico |
| Analytics | Relatórios por operador/departamento/canal | Não documentado | ✅ **Superamos** | `routes/historico.py` | — | — | |
| Analytics | Exportação | Não documentado | ✅ **Superamos** | CSV/XLSX (mig 110 + openpyxl) | — | — | |
| Analytics | Custo de IA | "Créditos", sem detalhe | ✅ **Superamos** | `ia_execucao`, custo real OpenRouter (mig 139), `/governanca/ia-budget` | — | — | `usage.cost` como fonte de verdade |
| Analytics | Observabilidade de LLM (traces) | Não tem | ✅ **Superamos** | Langfuse + LangSmith com switch na UI, mig 107/141 | — | — | |
| Analytics | Avaliação automática (LLM-as-judge) | Não tem | ✅ **Superamos** | `docs/LANGSMITH.md`, `/dashboard/rag` eval | — | — | |

## 10. Multi-tenant, permissões e billing

| Domínio | Funcionalidade | Como o Chatvolt resolve | Status | Evidência | Esf. | Imp. | Observação |
|---|---|---|---|---|---|---|---|
| Multi-tenant | Isolamento por organização | `organizationId` filtrado na aplicação | ✅ **Superamos** | **RLS no Postgres**: 4 roles, 58 tabelas FORCE, migs 096/100-103 | — | — | Isolamento no banco, não só no código |
| Multi-tenant | Papéis e permissões | Admin + módulos + **por agente** | 🟡 Parcial | 86 permissões, perfis, `.own`/`.all` (mig 083/084) | M | 3 | Nosso catálogo é maior; falta ACL por instância |
| Multi-tenant | ACL por instância de agente | View/Update/Delete por agente, com ação em massa | ❌ Não temos | — | M | 3 | |
| Multi-tenant | Limites por plano | Agentes, datastores, créditos, assentos, storage | ✅ Temos | `shared/plano_limits.py` | — | — | Cobramos por conexão, que eles não limitam |
| Multi-tenant | Billing | Assinatura, planos por degrau | ✅ Temos | `shared/asaas.py`, mig 105, `/billing` | — | — | |
| Multi-tenant | Créditos de mensagem | Unidade de cobrança | 🟡 Parcial | `limite_atendimentos_mes` + orçamento em USD | P | 3 | Crédito é mais legível ao cliente que dólar |
| Multi-tenant | White-label | Remover marca do widget (Pro) | ✅ **Superamos** | mig 115: logo, nome, cores por empresa | — | — | |
| Multi-tenant | Programa de parceiro / revenda | `/partner-set` no painel | ❌ Não temos | — | M | 4 | Temos a peça técnica (white-label); falta o programa comercial |
| Multi-tenant | Módulo "Forms" | `/forms`, `/forms/[id]/admin` | ❌ Não temos | — | M | 2 | Provável captação de lead por formulário; não documentado |
| Multi-tenant | Convite e status de usuário | Team no Settings | ✅ Temos | `routes/usuarios.py`, `auth.user.status`, mig 106 | — | — | |
| Multi-tenant | Histórico de login | Não documentado | ✅ **Superamos** | mig 026, `/settings/security/login-history` | — | — | |
| Multi-tenant | SSO Google | Não documentado | ✅ Temos | Better Auth `socialProviders.google` | — | — | |

## 11. Compliance

| Domínio | Funcionalidade | Como o Chatvolt resolve | Status | Evidência | Esf. | Imp. | Observação |
|---|---|---|---|---|---|---|---|
| Compliance | Política LGPD publicada | Páginas dedicadas BR + internacional | 🟡 Parcial | `routes/lgpd.py` é auditoria, não política pública | P | 4 | **Eles têm documento jurídico publicado; nós não.** Barato e bloqueia venda |
| Compliance | Log de auditoria | Doc *recomenda* manter — indica que não fornece | ✅ **Superamos** | `shared/audit.py`, `audit_governanca`, `/settings/security/audit` | — | — | |
| Compliance | Trilha imutável | `conversationLog` aceita PATCH e DELETE | ✅ **Superamos** | Nossa trilha é append-only | — | — | |
| Compliance | Registro de eventos LGPD | Não tem | ✅ **Superamos** | `routes/lgpd.py`, `shared/lgpd.py`, `cliente_pii.py` | — | — | |
| Compliance | Retenção configurável | Não documentado | ❌ Não temos | `atendimento_cleanup.py` existe mas não é política por empresa | M | 3 | Exigência de cliente maior |
| Compliance | Residência de dados | Não documentado | 🚫 Não queremos | — | — | — | Irrelevante no nosso ICP; ambos hospedam no exterior ou em nuvem única |
| Compliance | Exportação/exclusão do titular | Não documentado | 🟡 Parcial | `cliente_pii.py` + export do histórico | M | 3 | Falta fluxo único de "direito do titular" |

---

## Leitura da matriz

### Onde estamos claramente à frente

Infraestrutura e operação: **RLS no Postgres**, DLQ com retry, observabilidade de
custo real de LLM, anti-ban de disparo (jitter, teto diário, aquecimento, pool
de conexões), opt-out, NPS completo, auditoria imutável, multi-conexão de
verdade, departamentos e turnos.

Não é coincidência. São as coisas que aparecem quando se opera em produção com
cliente real — e a maior parte nasceu de incidente nosso, não de roadmap.

### Onde estamos claramente atrás

Três blocos, em ordem de custo:

1. **Extensibilidade** — HTTP tool, API pública, webhook de entrada. O cliente
   deles pode conectar a plataforma ao próprio sistema sem falar com o
   fornecedor. O nosso não pode.
2. **Funil de vendas** — Flux CRM + disparo que entrega no funil. Somos
   plataforma de *atendimento*; eles são de *atendimento e vendas*.
3. **Canais** — 9 contra 1. Discutido no backlog: **paridade aqui não é o
   objetivo certo**.

### O empate que mais importa

Ambos usam Embedded Signup, e **ambos permitem manter o app WhatsApp Business no
celular funcionando**. Eles transformaram isso em argumento de venda destacado na
documentação. Nós temos a mesma propriedade e não a mencionamos em lugar nenhum.

É a linha de maior retorno sobre esforço da matriz inteira: zero código.
