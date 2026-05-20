# Prompts de Agentes IA — Atendimento Saúde

Templates derivados de análise de **9.822 atendimentos reais** (dump
ZigChat 3 meses, 2026-02-08 a 2026-05-08) de um hospital. Os prompts
estão calibrados pro tom coloquial brasileiro respeitoso típico de
atendimento de saúde via WhatsApp.

## 📚 Metodologia e Template

- 📖 [**METODOLOGIA.md**](METODOLOGIA.md) — Técnicas de prompt engineering
  aplicadas (estrutura XML, few-shot, ReAct, constitutional AI / guardrails,
  RAG-aware)
- 📋 [**TEMPLATE_CANONICO.md**](TEMPLATE_CANONICO.md) — System prompt
  base no padrão Claude 4.6/4.7 — VSA Nexus AI. **Todo agente hospitalar
  novo segue esse template.**

**Regras obrigatórias em todos os prompts:**
- ✅ Tool `verify_patient_identity` obrigatória ANTES de qualquer dado sensível
- ✅ Tool `log_lgpd_event` chamada em TODO acesso a dado sensível
- ✅ Estrutura XML com `<role>`, `<core_principles>`, `<scope>`, `<identity_verification>`, `<tool_use_policy>`, `<examples>`, `<refusal_templates>`, `<persistent_identity_reminder>`
- ✅ Contexto dinâmico (`<context>`) vai na **primeira user message**, não no system prompt

## Os prompts

| Arquivo | Departamento de referência | Volume no dump | Slug sugerido |
|---|---|---|---|
| [`atendimento-cliente.md`](atendimento-cliente.md) v1.0 | **Recepção virtual (Menu 1)** — Mackenzie (XML + verify_identity + LGPD log) | — (novo) | `saude_atendimento_cliente` |
| [`exames.md`](exames.md) v1.0 | **Central de Exames (Menu 3)** — Mackenzie (XML + triagem financeira + LGPD log) | — (novo) | `saude_exames` |
| [`agendamentos.md`](agendamentos.md) | Dept 83 (37% volume) | 3.613 atend | `saude_agendamentos` |
| [`ouvidoria.md`](ouvidoria.md) | Dept 88 (15%) | 1.421 atend | `saude_ouvidoria` |
| [`suporte-exames.md`](suporte-exames.md) | Dept 87 (9%) | 920 atend | `saude_suporte_exames` |
| [`financeiro.md`](financeiro.md) | Dept 223 (4%) | 439 atend | `saude_financeiro` |
| [`nps-feedback.md`](nps-feedback.md) | Dept 82 (4%) | 387 atend | `saude_nps` |

> Os IDs de departamento são do **ZigChat origem** — quando aplicar no
> Nexus, mapeie pra IDs locais via `departamento.descricao` ou
> `agente_ia.departamento_default_id`.

## Como aplicar

### Opção 1 — Via UI (painel admin)

1. Abrir `/agents` → "Novo agente"
2. Copiar o conteúdo da seção `## Prompt` do arquivo
3. Colar em **Comportamento do agente**
4. Setar campos conforme seção `## Configuração` do arquivo
5. Salvar

### Opção 2 — Via script seeder (lote)

```bash
# Local (empresa de teste)
DATABASE_URL=postgresql://postgres:postgres@localhost:5434/whatsapp_langchain \
  uv run python scripts/seed_agentes_saude.py --empresa-id 1

# Produção (CUIDADO — preview antes)
DATABASE_URL=$PROD_DB_URL \
  uv run python scripts/seed_agentes_saude.py --empresa-id 1 --dry-run
```

Idempotente via `ON CONFLICT (empresa_id, slug) DO NOTHING`. Roda 2x
não duplica.

## Convenções aplicadas em todos os prompts

- **Língua**: pt-BR coloquial, jamais inglês
- **Tom**: respeitoso, paciente, evita jargão médico
- **Escalação**: depois de **3 tentativas sem resolver**, transfere pra
  humano via tool `transferir_para_humano`
- **LGPD**: nunca pede dados sensíveis sem necessidade. Quando precisa
  de CPF/data nascimento, justifica brevemente
- **Honestidade**: não inventa info. Se não souber, oferece transferir
- **Não-objetivos**: emoji só quando cliente usar primeiro (matching de
  registro); jamais diagnóstico médico
- **Mídia aceita**: imagens (foto exame, ID), áudios (mensagem de voz),
  documentos (PDF de pedido médico)
- **Janela memória**: 20 turnos (cliente costuma voltar dias depois)

## Métricas do dump que informaram esses prompts

- **Pico horário**: 13h-15h (tarde) + 18h-19h (final expediente)
- **Madrugada** (23h-8h): <3% volume → resposta automática "fora do horário"
- **Humano vs auto**: 62% humano / 38% bot. Indica que **menu/bot resolve
  ~38% sozinho** quando bem desenhado. Meta dos agentes IA: subir esse
  número pra ~60% mantendo CSAT
- **Mensagem inicial típica**: curta ("oi", "queria saber"), pede
  clareza desde o turn 2

## Não-objetivos (por enquanto)

- Sem agente "triagem geral" que classifica e roteia — isso é função
  do **menu chatbot** + `triagem.py` (já existem)
- Sem agente de pré-cadastro de paciente — depende de integração com
  prontuário (fora de escopo)
- Sem agente em inglês — base de cliente é 100% brasileira
